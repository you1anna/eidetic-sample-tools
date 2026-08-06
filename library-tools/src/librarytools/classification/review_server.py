"""Secure localhost-only browser UI for exception and sentinel review."""

from __future__ import annotations

import hashlib
import csv
import json
import re
import secrets
import webbrowser
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Sequence

from .domain import CandidateClassification, ClassificationError
from .review import ReviewQueue, ReviewSession, finalise_review
from .packets import classification_digest, read_classification_audit


_SAMPLE_ID = re.compile(r"[0-9a-f]{64}")


def validate_bind_host(host: str) -> str:
    if host != "127.0.0.1":
        raise ClassificationError("review server must bind to the 127.0.0.1 loopback address")
    return host


def load_review_packet(
    labels_path: Path,
) -> tuple[Path, ReviewSession, list[CandidateClassification]]:
    packet_dir = labels_path.parent
    metadata_path = packet_dir / "packet-meta.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClassificationError(f"invalid packet metadata: {exc}") from exc
    root_raw = metadata.get("root")
    digest = metadata.get("classification_digest")
    context = metadata.get("classification_context")
    if metadata.get("schema_version", 0) < 3:
        raise ClassificationError("packet must be classified with ensemble-v2 before review")
    if not isinstance(root_raw, str) or not isinstance(digest, str) or not isinstance(context, dict):
        raise ClassificationError("packet classification digest metadata is incomplete")
    root = Path(root_raw).resolve()
    if not root.is_dir():
        raise ClassificationError(f"sample root is unavailable: {root}")
    candidates = read_classification_audit(packet_dir / "classification-audit.jsonl")
    if classification_digest(candidates, context) != digest:
        raise ClassificationError("classification audit digest does not match packet metadata")
    try:
        with labels_path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh, delimiter="\t"))
    except OSError as exc:
        raise ClassificationError(f"cannot read packet labels: {exc}") from exc
    labelled = {(str(row.get("sample_id", "")), str(row.get("current_path", ""))) for row in rows}
    audited = {(candidate.sample_id, candidate.current_path.as_posix()) for candidate in candidates}
    if labelled != audited or len(rows) != len(candidates):
        raise ClassificationError("classification audit does not match labels.tsv membership")
    session = ReviewSession.open(packet_dir / "review-state.json", candidates, digest)
    return root, session, candidates


def create_review_app(
    root: Path,
    session: ReviewSession,
    candidates: Sequence[CandidateClassification],
    *,
    write_token: str | None = None,
    on_complete: Callable[[ReviewQueue], object] | None = None,
):
    try:
        from flask import Flask, abort, jsonify, render_template_string, request, send_file
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ClassificationError(
            "browser review requires the review-ui installation extra (Flask)"
        ) from exc

    root = root.resolve()
    by_id = {candidate.sample_id: candidate for candidate in candidates}
    if len(by_id) != len(candidates):
        raise ClassificationError("review candidates contain duplicate sample IDs")
    for candidate in candidates:
        source = (root / candidate.current_path).resolve()
        if not source.is_relative_to(root):
            raise ClassificationError(f"review audio path escapes root: {candidate.current_path}")

    token = write_token or secrets.token_urlsafe(32)
    complete = on_complete or (lambda queue: finalise_review(session.path.parent, queue))
    verified_stats: dict[str, tuple[int, int]] = {}
    app = Flask(__name__)
    app.config.update(REVIEW_WRITE_TOKEN=token)

    @app.after_request
    def secure_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; media-src 'self'; connect-src 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return render_template_string(_PAGE, token=token)

    @app.get("/api/state")
    def state():
        return jsonify(_state_payload(session.queue, by_id))

    @app.get("/audio/<sample_id>")
    def audio(sample_id: str):
        if not _SAMPLE_ID.fullmatch(sample_id):
            abort(404)
        candidate = by_id.get(sample_id)
        if candidate is None:
            abort(404)
        source = (root / candidate.current_path).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            abort(404)
        stat = source.stat()
        signature = (stat.st_size, stat.st_mtime_ns)
        if verified_stats.get(sample_id) != signature:
            if _sha256(source) != sample_id:
                return jsonify({"error": "audio bytes changed after classification"}), 409
            verified_stats[sample_id] = signature
        return send_file(source, conditional=True)

    @app.post("/api/decision")
    def decision():
        if not _authorised(request.headers.get("X-Review-Token", ""), token):
            abort(403)
        raw = request.get_json(silent=True)
        if not isinstance(raw, dict):
            return jsonify({"error": "JSON object required"}), 400
        try:
            session.apply_decision(
                str(raw.get("sample_id", "")),
                str(raw.get("form", "")),
                str(raw.get("content", "")),
                str(raw.get("notes", "")),
            )
            if session.queue.gate().passed:
                complete(session.queue)
        except ClassificationError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(_state_payload(session.queue, by_id))

    @app.post("/api/undo")
    def undo():
        if not _authorised(request.headers.get("X-Review-Token", ""), token):
            abort(403)
        try:
            session.undo()
        except ClassificationError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(_state_payload(session.queue, by_id))

    return app


def serve_review(
    root: Path,
    session: ReviewSession,
    candidates: Sequence[CandidateClassification],
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = False,
) -> str:
    from werkzeug.serving import make_server

    host = validate_bind_host(host)
    app = create_review_app(root, session, candidates)
    server = make_server(host, port, app, threaded=True)
    url = f"http://{host}:{server.server_port}/"
    print(f"review UI: {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - interactive shutdown
        pass
    finally:
        server.server_close()
    return url


def _state_payload(
    queue: ReviewQueue,
    candidates: dict[str, CandidateClassification],
) -> dict[str, object]:
    pending = queue.pending()
    total = len(queue.items)
    payload: dict[str, object] = {
        "complete": not pending,
        "progress": {"done": total - len(pending), "total": total},
        "failed_sentinel_groups": list(queue.failed_sentinel_groups()),
    }
    if not pending:
        payload["current"] = None
        return payload
    item = pending[0]
    candidate = candidates[item.sample_id]
    current: dict[str, object] = {
        "sample_id": item.sample_id,
        "kind": "check" if item.kind == "sentinel" else item.kind,
        "audio_url": f"/audio/{item.sample_id}",
    }
    if item.kind != "sentinel":
        current.update({
            "predicted_form": item.predicted_form,
            "predicted_content": item.predicted_content,
            "audition_group": item.audition_group,
            "review_reasons": list(item.review_reasons),
            "evidence": {
                "acoustic": asdict(candidate.evidence),
                "models": [
                    {
                        "model_id": vote.model_id,
                        "top_label": vote.top_label,
                        "top_score": vote.top_score,
                        "margin": vote.margin,
                    }
                    for vote in candidate.votes
                ],
            },
        })
    payload["current"] = current
    return payload


def _authorised(provided: str, expected: str) -> bool:
    return bool(provided) and secrets.compare_digest(provided, expected)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Sample packet review</title>
<style>
:root{color-scheme:dark;background:#111;color:#f5f2ea;font:16px/1.45 system-ui,sans-serif}
body{max-width:920px;margin:0 auto;padding:32px 20px} h1{font-size:1.5rem} .muted{color:#aaa}
.panel{border:1px solid #363636;border-radius:14px;padding:20px;margin:16px 0;background:#191919}
.choices{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin:10px 0 18px}
button{border:1px solid #555;background:#242424;color:inherit;border-radius:9px;padding:11px;cursor:pointer}
button.selected{border-color:#c8ff64;background:#33421f} button.primary{background:#c8ff64;color:#111;font-weight:700}
audio{width:100%;margin:12px 0} textarea{width:100%;box-sizing:border-box;background:#111;color:inherit;border:1px solid #555;border-radius:8px;padding:10px}
pre{white-space:pre-wrap;font-size:.8rem;color:#bbb}.row{display:flex;gap:8px;align-items:center;justify-content:space-between}
</style></head><body>
<div class="row"><h1>Sample packet review</h1><span id="progress" class="muted"></span></div>
<main id="app" class="panel">Loading…</main>
<script>
const TOKEN={{ token|tojson }}; const FORMS=['ONE_SHOT','LOOP','PHRASE','LONG_FORM'];
const CONTENTS=['RIM','TOM','PERCUSSION','FULL_DRUMS','VOCAL','OUT_OF_BRIEF'];
let state=null, form='', content='';
async function refresh(data){state=data||await (await fetch('/api/state')).json(); render()}
function buttons(values,axis){return `<div class="choices">${values.map(v=>`<button data-axis="${axis}" data-value="${v}">${v.replaceAll('_',' ')}</button>`).join('')}</div>`}
function render(){const p=state.progress;document.querySelector('#progress').textContent=`${p.done} / ${p.total}`;
 const el=document.querySelector('#app'); if(state.complete){el.innerHTML='<h2>Review complete</h2><p>The guarded benchmark and classification snapshot are ready.</p><button id="undo">Undo last</button>';bind();return}
 const c=state.current;form=c.predicted_form||'';content=c.predicted_content||'';
 el.innerHTML=`<div class="muted">${c.kind==='check'?'Blind category check':c.kind.replaceAll('_',' ')}</div><audio id="audio" controls src="${c.audio_url}"></audio>
 ${c.review_reasons?`<p>${c.review_reasons.join(' · ')}</p><pre>${JSON.stringify(c.evidence,null,2)}</pre>`:''}
 <h3>Form</h3>${buttons(FORMS,'form')}<h3>Content</h3>${buttons(CONTENTS,'content')}
 <textarea id="notes" rows="2" placeholder="Optional note"></textarea><div class="row"><button id="undo">Undo</button><button class="primary" id="submit">Save and continue</button></div>`;bind();mark()}
function bind(){document.querySelectorAll('[data-axis]').forEach(b=>b.onclick=()=>{window[b.dataset.axis]=b.dataset.value;if(b.dataset.axis==='form')form=b.dataset.value;else content=b.dataset.value;mark()});
 const u=document.querySelector('#undo');if(u)u.onclick=undo;const s=document.querySelector('#submit');if(s)s.onclick=submit}
function mark(){document.querySelectorAll('[data-axis]').forEach(b=>b.classList.toggle('selected',(b.dataset.axis==='form'?form:content)===b.dataset.value))}
async function submit(){if(!form||!content)return alert('Choose both form and content');const body={sample_id:state.current.sample_id,form,content,notes:document.querySelector('#notes').value};
 const r=await fetch('/api/decision',{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':TOKEN},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)return alert(d.error);refresh(d)}
async function undo(){const r=await fetch('/api/undo',{method:'POST',headers:{'X-Review-Token':TOKEN}});const d=await r.json();if(!r.ok)return alert(d.error);refresh(d)}
document.addEventListener('keydown',e=>{if(e.target.tagName==='TEXTAREA')return;if(e.code==='Space'){e.preventDefault();const a=document.querySelector('#audio');a.paused?a.play():a.pause()}if(e.key==='Enter')submit();if(e.key.toLowerCase()==='u')undo()});refresh();
</script></body></html>"""
