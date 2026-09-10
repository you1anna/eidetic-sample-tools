import json
from pathlib import Path
import socket
import threading
from contextlib import nullcontext

import pytest

from eideticlive import LiveClient, LiveError
from eideticlive._vendor import bridge
from eideticlive.edits import plan_edits, apply_plan, reconcile
from eideticlive.reports import check_snapshot
from eideticlive.staging import stage, build_id


def port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@pytest.mark.parametrize('reply', ['valid', 'wrong_request', 'wrong_path', 'malformed', 'error', 'silent'])
def test_correlated_ack_and_no_write_retries(tmp_path, monkeypatch, reply):
    monkeypatch.setenv('EIDETIC_LIVE_TOKEN', 'synthetic-test-token-123')
    received = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(('127.0.0.1', 0))
        server.settimeout(0.25)
        ack_port = port()
        client = LiveClient({'port': server.getsockname()[1], 'ack_port': ack_port, 'timeout': 0.12,
                             'lock_path': str(tmp_path / 'ack.lock')})
        def respond():
            try:
                data, _ = server.recvfrom(65507)
                address, values = bridge.decode_osc_message(data)
                received.append((address, values))
                request = values[-1]
                if reply == 'wrong_request':
                    request = 'not-this-request'
                arguments = ['api_set', 'live_set' if reply != 'wrong_path' else 'live_set tracks 1', 'tempo', '{"ok":true}', request]
                if reply == 'malformed':
                    arguments[3] = '{"ok":false}'
                if reply == 'error':
                    arguments = ['error', 'denied', '__request_id__', 'req:' + request]
                if reply != 'silent':
                    server.sendto(bridge.encode_osc_message('/ack', arguments), ('127.0.0.1', ack_port))
                # Count any mutation resend after timeout/error.
                while True:
                    data, _ = server.recvfrom(65507)
                    received.append(bridge.decode_osc_message(data))
            except socket.timeout:
                pass
        thread = threading.Thread(target=respond)
        thread.start()
        if reply == 'valid':
            assert client.set('live_set', 'tempo', 120) == {'ok': True}
        else:
            with pytest.raises(LiveError) as error:
                client.set('live_set', 'tempo', 120)
            assert 'synthetic-test-token' not in str(error.value)
        thread.join()
        assert len(received) == 1


class FakeLive:
    def __init__(self, tmp_path):
        self.set_file = tmp_path / 'session.als'
        self.set_file.write_bytes(b'synthetic saved set')
        self.identity = {'build_id': build_id(), 'instance_id': 'load-1', 'set_id': 1,
                         'set_path': str(self.set_file), 'set_name': 'Session'}
        self.value = 0.25
        self.writes = 0
        self.lose_ack = False
    def exclusive(self):
        return nullcontext()
    def runtime(self):
        return dict(self.identity)
    def get(self, path, property):
        return {'id': 10, 'name': 'Gain', 'value': self.value, 'min': 0, 'max': 1,
                'is_enabled': 1, 'is_quantized': 0, 'is_playing': 0, 'record_mode': 0,
                'session_record': 0}[property]
    def request(self, address, args, write=False):
        self.writes += 1
        self.value = json.loads(args[1])
        if self.lose_ack:
            raise LiveError('Synthetic ACK loss')
        return {'parameter': {'value': self.value}}


def operation(value=0.5):
    return {'op': 'set_parameter', 'path': 'live_set tracks 0 devices 0 parameters 0', 'value': value}


@pytest.mark.parametrize('change', ['instance', 'set_path', 'build', 'before', 'file', 'plan'])
def test_apply_rejects_stale_plan_before_any_send(tmp_path, change):
    client = FakeLive(tmp_path)
    plan = plan_edits(client, [operation()])
    if change in ('instance', 'build', 'set_path'):
        key = {'instance': 'instance_id', 'build': 'build_id', 'set_path': 'set_path'}[change]
        client.identity[key] = 'changed'
    elif change == 'before':
        client.value = 0.75
    elif change == 'file':
        client.set_file.write_bytes(b'changed')
    else:
        plan['operations'][0]['operation']['value'] = 0.9
    with pytest.raises(LiveError):
        apply_plan(client, plan, tmp_path / 'receipt.json')
    assert client.writes == 0


def test_ack_loss_journal_reconcile_does_not_retry(tmp_path):
    client = FakeLive(tmp_path)
    client.lose_ack = True
    plan = plan_edits(client, [operation()])
    destination = tmp_path / 'receipt.json'
    receipt = apply_plan(client, plan, destination)
    assert receipt['status'] == 'partial'
    assert json.loads(destination.read_text())['operations'][0]['status'] == 'unknown'
    assert reconcile(client, receipt)['complete'] is True
    assert client.writes == 1
    with pytest.raises(FileExistsError):
        # Restore before-state solely to reach the existing receipt guard.
        client.value = 0.25
        apply_plan(client, plan, destination)
    assert client.writes == 1


@pytest.mark.parametrize('op', [operation(2), operation(float('nan')),
    {'op': 'delete_track', 'path': 'live_set tracks 0'},
    {'op': 'insert_device', 'path': 'live_set tracks 0', 'device': 'Unreviewed Plug-in', 'index': 0},
    {'op': 'set_parameter', 'path': 'live_set', 'value': 0.5}])
def test_invalid_operations_never_write(tmp_path, op):
    client = FakeLive(tmp_path)
    with pytest.raises(LiveError):
        plan_edits(client, [op])
    assert client.writes == 0


def test_stage_is_isolated_and_includes_identity(tmp_path):
    result = stage(tmp_path / 'runtime', port=9010, ack_port=9011)
    root = Path(result['directory'])
    assert result['build_id'] == build_id()
    assert 'eidetic_runtime' in (root / 'eidetic_runtime.js').read_text()
    assert 'const COMMAND_PORT = 9010;' in (root / 'eidetic_receiver.js').read_text()
    assert 'udpsend 127.0.0.1 9011' in (root / 'eidetic_live.maxpat').read_text()
    assert 'MIT License' in (root / 'LICENSE.upstream').read_text()
    with pytest.raises(LiveError):
        stage(root)


@pytest.mark.parametrize('complete,manual,expected', [(True, [], 'pass'), (False, [], 'unverified'), (True, ['clock'], 'unverified')])
def test_incomplete_and_manual_checks_never_pass(complete, manual, expected):
    snapshot = {'schema': 'eidetic-live.snapshot', 'schema_version': 1, 'complete': complete,
                'identity': {'build_id': 'b', 'instance_id': 'i', 'set_id': 1, 'set_path': '/tmp/demo.als', 'set_name': 'Demo'},
                'transport': {'playing': False, 'tempo': 120}, 'tracks': [{'name': 'Audio', 'arm': 0}]}
    result = check_snapshot(snapshot, {'schema_version': 1, 'tracks': [{'name': 'Audio', 'arm': 0}], 'manual_checks': manual})
    assert result['status'] == expected


def test_cross_process_lock_prevents_send(tmp_path):
    import subprocess
    import sys
    lock = tmp_path / 'shared.lock'
    script = 'import fcntl,sys,time; f=open(sys.argv[1],"w"); fcntl.flock(f,fcntl.LOCK_EX); print("locked",flush=True); time.sleep(2)'
    holder = subprocess.Popen([sys.executable, '-c', script, str(lock)], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == 'locked'
        client = LiveClient({'lock_path': str(lock), 'timeout': 0.08})
        with pytest.raises(LiveError, match='lock timeout'):
            client.request('/api/ping', [])
    finally:
        holder.terminate()
        holder.wait(timeout=2)


def test_restore_only_when_applied_value_remains(tmp_path):
    from eideticlive.edits import restore_parameters
    client = FakeLive(tmp_path)
    receipt = apply_plan(client, plan_edits(client, [operation()]), tmp_path / 'receipt.json')
    restore = restore_parameters(client, receipt)
    assert restore['operations'][0]['operation']['value'] == 0.25
    assert client.writes == 1
    client.value = 0.8
    with pytest.raises(LiveError):
        restore_parameters(client, receipt)
    assert client.writes == 1


@pytest.mark.parametrize('snapshot,profile', [
    ({'complete': True, 'tracks': []}, {'schema_version': 1, 'tracks': [{'name': 'Audio'}]}),
    ({'schema': 'eidetic-live.snapshot', 'schema_version': 1, 'complete': True, 'tracks': [], 'identity': {}, 'transport': {}}, {'schema_version': 1}),
])
def test_malformed_snapshot_or_empty_profile_cannot_pass(snapshot, profile):
    with pytest.raises(LiveError):
        check_snapshot(snapshot, profile)


def test_nested_mixer_errors_refuse_complete():
    from eideticlive.reports import _require_readable_payload
    with pytest.raises(LiveError):
        _require_readable_payload({'parameters': {'volume': {'id': 3, 'errors': {'value': 'unavailable'}}}})


def test_composite_edit_stops_before_naming_if_runtime_changed(tmp_path):
    from eideticlive.edits import _execute
    class ChangedRuntime(FakeLive):
        def call(self, path, method, args):
            self.writes += 1
            self.identity['instance_id'] = 'new-load'
        def set(self, path, property, value):
            self.writes += 1
    client = ChangedRuntime(tmp_path)
    identity = client.runtime()
    with pytest.raises(LiveError, match='identity changed'):
        _execute(client, {'op': 'create_clip', 'path': 'live_set tracks 0 clip_slots 0', 'length': 4, 'name': 'Demo'}, {'id': 10}, identity)
    assert client.writes == 1


def test_runtime_extension_identity_and_dictionary_resolution():
    import shutil
    import subprocess
    from importlib.resources import files
    node = shutil.which('node')
    if not node:
        pytest.skip('Node runtime needed to exercise Max JS with a mocked Live API')
    subprocess.run([node, str(Path(__file__).with_name('runtime_extension_check.js')),
                    str(files('eideticlive').joinpath('resources', 'eidetic_extension.js'))], check=True)


@pytest.mark.parametrize('complete,exit_code', [(True, 0), (False, 2)])
def test_human_diff_preserves_incomplete_exit(tmp_path, capsys, complete, exit_code):
    from eideticlive.cli import main
    before = tmp_path / 'before.json'
    after = tmp_path / 'after.json'
    before.write_text(json.dumps({'complete': complete, 'tracks': []}))
    after.write_text(json.dumps({'complete': True, 'tracks': [{'name': 'Changed'}]}))
    assert main(['--summary', 'diff', str(before), str(after)]) == exit_code
    assert 'Changed fields:' in capsys.readouterr().out


def test_forbidden_monitor_track_must_exist(tmp_path):
    client = FakeLive(tmp_path)
    snapshot = {'schema': 'eidetic-live.snapshot', 'schema_version': 1, 'complete': True,
                'identity': client.identity, 'transport': {'playing': False, 'tempo': 120}, 'tracks': []}
    assert check_snapshot(snapshot, {'schema_version': 1, 'forbid_monitoring': ['Missing']})['status'] == 'fail'


def test_describe_normalises_quoted_liveapi_path_from_ack(tmp_path, monkeypatch):
    client = LiveClient({'lock_path': str(tmp_path / 'ack.lock')})
    request_id = 'quoted-path-request'
    command = bridge.OscCommand('/api/describe', ('id 42', request_id))
    packet = bridge.encode_osc_message('/ack', ['api_describe', '"live_set tracks 0"',
        json.dumps({'id': 42, 'path': '  "live_set tracks 0"  ', 'name': 'Candidate'}), request_id])
    address, args = bridge.decode_osc_message(packet)
    payload = bridge.validate_command_acks(command, [(address, args)]).payload
    monkeypatch.setattr(client, 'request', lambda *args, **kwargs: payload)
    description = client.describe('id 42')
    assert description['id'] == 42
    assert description['path'] + ' clip_slots 0' == 'live_set tracks 0 clip_slots 0'
