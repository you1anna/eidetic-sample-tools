"""Loopback-only source chooser with an optional, separately loaded vocal lab."""
from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import secrets
import shlex
import sqlite3
import uuid
import webbrowser

from .vibe_session import VibeError, load_session, source_state, source_audio
from .locking import LibraryBusyError
from .vibe_shortlist import (shortlist_state, save_shortlist_decision,
                            shortlist_playlist, handoff_status, create_shortlist_packet)


def validate_bind_host(host: str) -> str:
    if host != '127.0.0.1':
        raise VibeError('Audition server must bind to 127.0.0.1')
    return host


def create_vibe_app(session_dir: Path, *, write_token: str | None = None, live_client=None):
    from flask import Flask, abort, jsonify, render_template_string, request, send_file, Response
    session_dir = Path(session_dir).resolve()
    load_session(session_dir)
    token = write_token or secrets.token_urlsafe(32)
    app = Flask(__name__, static_folder=None)
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024
    app.config['TRUSTED_HOSTS'] = ['127.0.0.1', 'localhost']

    @app.after_request
    def response_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"
        return response

    @app.errorhandler(sqlite3.Error)
    @app.errorhandler(ValueError)
    def invalid_request(exc):
        return jsonify(error=str(exc)), 409 if request.method == 'GET' else 400

    @app.errorhandler(LibraryBusyError)
    def busy(exc):
        return jsonify(error='Another audition write is running. Try again when it finishes.'), 409

    @app.errorhandler(OSError)
    def unavailable(exc):
        return jsonify(error=f'Audition files are unavailable: {exc.strerror or str(exc)}'), 409

    @app.get('/')
    def page():
        resource = files('librarytools').joinpath('resources/audition.html')
        return render_template_string(resource.read_text(encoding='utf-8'), token=token)

    @app.get('/vocal-lab')
    def vocal_lab():
        if load_session(session_dir)['schema_version'] != 1:
            raise VibeError('The vocal lab requires a legacy anchor/vocal session')
        resource = files('librarytools').joinpath('resources/vibe.html')
        return render_template_string(resource.read_text(encoding='utf-8'), token=token)

    @app.get('/static/<name>')
    def asset(name):
        types = {'vibe.js': 'text/javascript', 'vibe.css': 'text/css',
                 'audition.js': 'text/javascript', 'audition.css': 'text/css',
                 'tokens.css': 'text/css'}
        if name not in types:
            abort(404)
        return Response(files('librarytools').joinpath(f'resources/{name}').read_text(encoding='utf-8'), mimetype=types[name])

    @app.get('/favicon.ico')
    def favicon():
        return Response(status=204)

    @app.get('/api/state')
    def state():
        if load_session(session_dir)['schema_version'] != 1:
            return jsonify(source_state(session_dir))
        from .vibe import session_state
        return jsonify(session_state(session_dir))

    @app.get('/api/sources')
    def sources():
        return jsonify(source_state(session_dir))

    def body():
        provided = request.headers.get('X-Vibe-Token', '')
        if not provided or not provided.isascii() or not secrets.compare_digest(provided, token):
            abort(403)
        raw = request.get_json(silent=True)
        if not isinstance(raw, dict):
            raise VibeError('A JSON object is required')
        return raw

    @app.post('/api/batch')
    def batch():
        raw = body()
        if set(raw) != {'batch_index'} or load_session(session_dir)['schema_version'] != 2:
            raise VibeError('Batch navigation requires a collection session and batch_index')
        from .vibe_collection import batch_state
        return jsonify(batch_state(session_dir, raw['batch_index']))

    live = None

    def live_operation(method, **kwargs):
        nonlocal live
        try:
            from eideticlive.audition import LiveAudition
            if live is None:
                live = LiveAudition(session_dir, client=live_client)
            return getattr(live, method)(**kwargs)
        except ImportError as exc:
            raise VibeError('Live playback is unavailable. Install library-tools[live] explicitly in this environment') from exc
        except (RuntimeError, OSError) as exc:
            raise VibeError(f'Live unavailable or operation refused: {exc}. Browser playback remains disabled in Live mode.') from exc

    @app.get('/api/live/status')
    def live_status():
        return jsonify(live_operation('status'))

    @app.get('/api/live/reconcile')
    def live_reconcile():
        return jsonify(live_operation('reconcile'))

    @app.post('/api/live/attach-preview')
    def live_attach():
        raw = body()
        if set(raw) != {'saved_set'} or not isinstance(raw['saved_set'], str):
            raise VibeError('Supply the open saved .als Set path')
        return jsonify(live_operation('preview_attachment', saved_set=raw['saved_set']))

    @app.post('/api/live/load-preview')
    def live_load():
        raw = body()
        if set(raw) != {'source_id', 'role'} or raw['role'] not in ('reference', 'candidate'):
            raise VibeError('Choose a source and reference or candidate role')
        state = load_session(session_dir)
        path = source_audio(session_dir, raw['source_id'])
        return jsonify(live_operation('preview_load', role=raw['role'], sample_id=raw['source_id'],
                       path=str(path), sha256=state['sources'][raw['source_id']]['preview_hash']))

    @app.post('/api/live/confirm')
    def live_confirm():
        raw = body()
        if set(raw) != {'preview_id'} or not isinstance(raw['preview_id'], str):
            raise VibeError('Supply the explicit preview identifier')
        return jsonify(live_operation('confirm', preview_id=raw['preview_id']))

    @app.post('/api/live/control')
    def live_control():
        raw = body()
        if 'action' not in raw or set(raw) - {'action', 'with_reference', 'gain', 'loop', 'warping', 'warp_mode'}:
            raise VibeError('Unexpected Live control fields')
        return jsonify(live_operation('control', **raw))

    @app.get('/api/shortlist')
    def shortlist():
        return jsonify(shortlist_state(session_dir))

    @app.post('/api/shortlist')
    def choose():
        raw = body()
        if set(raw) != {'source_id', 'decision'}:
            raise VibeError('Choose a source and Keep, Skip or reset')
        return jsonify(save_shortlist_decision(session_dir, raw['source_id'], raw['decision']))

    @app.get('/api/shortlist/status')
    def export_status():
        return jsonify(handoff_status(session_dir))

    @app.get('/api/shortlist/playlist')
    def playlist():
        return Response(shortlist_playlist(session_dir), mimetype='audio/x-mpegurl',
                        headers={'Content-Disposition': 'attachment; filename="eidetic-shortlist.m3u8"'})

    @app.post('/api/shortlist/packet')
    def packet():
        if body():
            raise VibeError('Curation sheet preparation takes no fields')
        directory = session_dir / 'curation-packets' / uuid.uuid4().hex
        count = create_shortlist_packet(session_dir, directory)
        labels = directory / 'labels.tsv'
        root = load_session(session_dir)['root']
        return jsonify(count=count, message=f'Saved: {labels}', next_step=(
            'Review labels.tsv: change only the samples you approve to favourite, and fill '
            'in each true_role and descriptor. Kept samples are not export approvals.\n\n'
            f'sample-curate --root {shlex.quote(root)} validate --labels {shlex.quote(str(labels))}\n\n'
            'Then use the existing promote → views → sample-export preview workflow. '
            'For views, pass --quotas with a TOML file containing your approved role counts; '
            'the default quotas target a much larger collection.'
        ))

    @app.post('/api/render')
    def render():
        from .vibe import render_preview
        return jsonify(render_preview(session_dir, body()))

    @app.post('/api/feedback')
    def feedback():
        from .vibe import save_feedback
        raw = body()
        if set(raw) - {'render_id', 'decision', 'note'}:
            raise VibeError('Unexpected feedback fields')
        return jsonify(save_feedback(session_dir, raw.get('render_id'), raw.get('decision'), raw.get('note', '')))

    @app.get('/source/<source_id>')
    def source(source_id):
        state = load_session(session_dir)
        if source_id not in state['sources']:
            abort(404)
        return send_file(source_audio(session_dir, source_id), mimetype='audio/wav', conditional=True)

    @app.get('/audio/<render_id>/<part>')
    def audio(render_id, part):
        if part not in ('anchor', 'vocal', 'mix') or len(render_id) != 64 or any(c not in '0123456789abcdef' for c in render_id):
            abort(404)
        from .vibe import rendered_audio
        return send_file(rendered_audio(session_dir, render_id, part), mimetype='audio/wav', conditional=True)

    return app


def serve_vibe(session_dir: Path, *, host: str = '127.0.0.1', port: int = 0, open_browser: bool = False):
    from werkzeug.serving import make_server
    validate_bind_host(host)
    server = make_server(host, port, create_vibe_app(session_dir), threaded=True)
    url = f'http://{host}:{server.server_port}/'
    print(f'Audition on this Mac: {url}', flush=True)
    print('Localhost is on the Mac, not your remote phone. Ctrl-C stops this session.', flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
