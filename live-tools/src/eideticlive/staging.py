"""Explicit staging of an isolated Max runtime. Never installs on import."""
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import shutil
from .client import LiveError

UPSTREAM_COMMIT = '6b9ed94dd471d2b33c3218792e644a4f85fb32e3'


def build_id():
    digest = hashlib.sha256(UPSTREAM_COMMIT.encode())
    for name in ('live_udp_bridge.js', 'osc_loopback_receiver.js', 'live_udp_bridge.maxpat', 'eidetic_extension.js'):
        digest.update(files('eideticlive').joinpath('resources', name).read_bytes())
    return digest.hexdigest()[:24]


def stage(destination, port=9000, ack_port=9001):
    """Create a new staging directory; the user builds/reloads the .amxd in Max."""
    if not all(isinstance(p, int) and 1024 <= p <= 65535 for p in (port, ack_port)) or port == ack_port:
        raise LiveError('Use distinct unprivileged ports')
    target = Path(destination).expanduser().absolute()
    if target.exists():
        raise LiveError('Staging destination already exists; use a fresh directory')
    resource = files('eideticlive').joinpath('resources')
    extension = resource.joinpath('eidetic_extension.js').read_text().replace('__EIDETIC_BUILD_ID__', build_id())
    runtime = resource.joinpath('live_udp_bridge.js').read_text() + '\n' + extension
    receiver = resource.joinpath('osc_loopback_receiver.js').read_text().replace('const COMMAND_PORT = 9000;', f'const COMMAND_PORT = {port};')
    patch = resource.joinpath('live_udp_bridge.maxpat').read_text().replace('live_udp_bridge.js', 'eidetic_runtime.js').replace('osc_loopback_receiver.js', 'eidetic_receiver.js').replace('udpsend 127.0.0.1 9001', f'udpsend 127.0.0.1 {ack_port}')
    target.mkdir(parents=True, mode=0o700)
    try:
        for name, content in (('eidetic_runtime.js', runtime), ('eidetic_receiver.js', receiver), ('eidetic_live.maxpat', patch)):
            (target / name).write_text(content)
        (target / 'LICENSE.upstream').write_text(files('eideticlive').joinpath('_vendor', 'LICENSE').read_text())
        manifest = {'schema': 'eidetic-live.runtime-build', 'schema_version': 1,
                    'build_id': build_id(), 'upstream_commit': UPSTREAM_COMMIT, 'port': port, 'ack_port': ack_port,
                    'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file()},
                    'hardware_verified': False}
        (target / 'build.json').write_text(json.dumps(manifest, indent=2) + '\n')
        return {**manifest, 'directory': str(target), 'next': 'Follow live-tools/REFERENCE.md to build and reload the Max device; staging alone does not install it.'}
    except Exception:
        shutil.rmtree(target)
        raise
