"""Loopback RPC boundary; mutations are sent once, never retried."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import threading
import time
import uuid

from ._vendor import bridge


class LiveError(RuntimeError):
    """A failed or unverified Live request. A mutation may already have happened."""


_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
IDENTITY_KEYS = ('build_id', 'instance_id', 'set_id', 'set_path', 'set_name')


def normalise(value):
    return value[0] if isinstance(value, list) and len(value) == 1 else value


def json_value(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


class LiveClient:
    def __init__(self, config=None):
        config_path = Path(os.environ.get('EIDETIC_LIVE_CONFIG', '~/.config/eidetic-live/config.json')).expanduser()
        values = json.loads(config_path.read_text()) if config_path.is_file() else {}
        values.update(config or {})
        self.host = values.get('host', '127.0.0.1')
        if not ipaddress.ip_address(self.host).is_loopback or ':' in self.host:
            raise LiveError('Only IPv4 loopback is supported')
        self.port = int(values.get('port', 9000))
        self.ack_port = int(values.get('ack_port', 9001))
        if not all(1024 <= p <= 65535 for p in (self.port, self.ack_port)) or self.port == self.ack_port:
            raise LiveError('Use distinct unprivileged command and ACK ports')
        self.timeout = float(values.get('timeout', 3.0))
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 60:
            raise LiveError('Timeout must be finite and between 0 and 60 seconds')
        # Tokens are accepted from the environment only, never serialised in config/reports.
        self._token = os.environ.get('EIDETIC_LIVE_TOKEN')
        self.lock_path = Path(values.get('lock_path', f'~/.cache/eidetic-live/ack-{self.ack_port}.lock')).expanduser().absolute()
        with _LOCKS_GUARD:
            self._thread_lock = _LOCKS.setdefault(str(self.lock_path), threading.RLock())
        self._depth = 0

    @contextmanager
    def exclusive(self):
        """Serialise the ACK socket across cooperating processes and threads."""
        deadline = time.monotonic() + self.timeout
        if not self._thread_lock.acquire(timeout=self.timeout):
            raise LiveError('ACK lock timeout; another client is active')
        descriptor = None
        try:
            if self._depth == 0:
                self.lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
                while True:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise LiveError('ACK lock timeout; another process is active')
                        time.sleep(min(0.02, max(0, deadline - time.monotonic())))
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
        except OSError as exc:
            raise LiveError(f'ACK lock/socket unavailable ({type(exc).__name__})') from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            self._thread_lock.release()

    def request(self, address, args=(), write=False):
        """Return the validated ACK payload. No fragment endpoint is exposed here."""
        if address not in bridge._ACK_REQUEST_ARGUMENT_COUNTS or 'inspect' in address:
            raise LiveError('Unsupported RPC endpoint; use bounded inspection APIs')
        protected = address in bridge.PROTECTED_OSC_ADDRESSES
        if protected != bool(write):
            raise LiveError('Mutation endpoint requires write=True')
        request_id = uuid.uuid4().hex
        values = list(args)
        if write:
            token = self._token
            if not isinstance(token, str) or token == bridge.AUTH_TOKEN_PLACEHOLDER or not 16 <= len(token.encode()) <= 256:
                raise LiveError('EIDETIC_LIVE_TOKEN must contain 16–256 UTF-8 bytes')
            values.insert(0, token)
        expected_count = bridge._ACK_REQUEST_ARGUMENT_COUNTS[address]
        if len(values) != expected_count:
            raise LiveError('Wrong RPC argument count')
        values.append(request_id)
        command = bridge.OscCommand(address, tuple(values))
        try:
            packet = bridge.encode_osc_message(address, values)
        except (ValueError, TypeError, OverflowError):
            raise LiveError('Invalid OSC argument') from None
        if len(packet) > 65507:
            raise LiveError('Request exceeds UDP payload limit')
        with self.exclusive():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as ack, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                try:
                    ack.bind(('127.0.0.1', self.ack_port))
                    deadline = time.monotonic() + self.timeout
                    sender.sendto(packet, (self.host, self.port))
                    packets = 0
                    while packets < 256:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        ack.settimeout(remaining)
                        try:
                            data, peer = ack.recvfrom(65508)
                        except socket.timeout:
                            break
                        packets += 1
                        if not ipaddress.ip_address(peer[0]).is_loopback:
                            continue
                        try:
                            response, arguments = bridge.decode_osc_message(data)
                            event = bridge.parse_ack_event(response, arguments)
                        except (ValueError, TypeError, IndexError):
                            continue
                        if event.request_id != request_id:
                            continue
                        try:
                            validated = bridge.validate_command_acks(command, [(response, arguments)])
                        except bridge.BridgeAcknowledgementError:
                            raise LiveError('Bridge rejected request or returned an incomplete ACK; reconcile before retrying a mutation') from None
                        return validated.payload
                except OSError as exc:
                    raise LiveError(f'UDP request failed ({type(exc).__name__}); mutation outcome may be unknown') from None
        raise LiveError('ACK timeout or packet limit; mutation outcome unknown; reconcile before retrying')

    def get(self, path, property):
        if property == 'id':
            return self.describe(path)['id']
        value = self.request('/api/get', [path, property])['value']
        if isinstance(value, list) and len(value) >= 2 and value[0] == property:
            value = value[1:]
        return normalise(value)

    def set(self, path, property, value):
        return self.request('/api/set', [path, property, json_value(value)], write=True)['result']

    def call(self, path, method, args=()):
        return normalise(self.request('/api/call', [path, method, json_value(args)], write=True)['result'])

    def describe(self, path):
        value = self.request('/api/describe', [path])['description']
        if type(value.get('id')) is not int or value['id'] <= 0:
            raise LiveError('Unresolved Live object')
        resolved = value.get('path')
        if not isinstance(resolved, str):
            raise LiveError('Missing resolved Live object path')
        resolved = resolved.strip()
        if len(resolved) >= 2 and resolved[0] in ('\"', "'") and resolved[-1] == resolved[0]:
            resolved = resolved[1:-1]
        resolved = ' '.join(resolved.split())
        if not re.fullmatch(r'(?:live_set|live_app)(?: (?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+))*', resolved):
            raise LiveError('Invalid canonical resolved Live object path')
        return {**value, 'path': resolved}

    def children(self, path, child):
        values = self.request('/api/children', [path, child])['children']
        if any(not isinstance(row.get('id'), int) or row['id'] <= 0 or row.get('error') for row in values):
            raise LiveError('Incomplete child inventory')
        if [row.get('index') for row in values] != list(range(len(values))):
            raise LiveError('Non-contiguous child inventory')
        return values

    def runtime(self):
        identity = self.get('live_set', 'eidetic_runtime')
        if not isinstance(identity, dict) or set(identity) != set(IDENTITY_KEYS):
            raise LiveError('Missing Eidetic runtime identity; stage and reload the device')
        if not all(isinstance(identity[k], str) and identity[k] for k in ('build_id', 'instance_id')) or not isinstance(identity['set_id'], int) or identity['set_id'] <= 0:
            raise LiveError('Invalid runtime identity')
        if not all(isinstance(identity[k], str) for k in ('set_path', 'set_name')):
            raise LiveError('Invalid Set identity')
        from .staging import build_id
        if identity['build_id'] != build_id():
            raise LiveError('Loaded runtime build differs from this package; stage and reload')
        return identity

    def inspect(self, detail=False):
        from .reports import inspect_live
        return inspect_live(self, detail)
