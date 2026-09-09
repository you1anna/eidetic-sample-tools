"""Persist listening choices without approving curation or exporting audio."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from .locking import _file_lock
from .vibe_session import (
    VibeError, write_json, contained_path, validate_identifier, read_json,
    verify_source, load_session, source_ids,
)


def _decisions(session_dir: Path, state: dict) -> dict[str, str]:
    path = session_dir / 'shortlist.json'
    if path.is_symlink():
        raise VibeError('Shortlist evidence must not be a symlink')
    if not path.exists():
        return {}
    evidence = read_json(contained_path(session_dir, path))
    decisions = evidence.get('decisions')
    if evidence.get('schema_version') != 1 or not isinstance(decisions, dict):
        raise VibeError('Invalid shortlist evidence')
    known = set(source_ids(state))
    if any(source_id not in known or decision not in ('keep', 'skip', 'unreviewed')
           for source_id, decision in decisions.items()):
        raise VibeError('Invalid saved shortlist decision')
    return decisions


def _public_state(state: dict, saved: dict) -> dict:
    decisions = {source_id: saved.get(source_id, 'unreviewed') for source_id in source_ids(state)}
    return {'decisions': decisions, 'counts': {'total': len(decisions), **{
        decision: sum(value == decision for value in decisions.values())
        for decision in ('keep', 'skip', 'unreviewed')}}}


def shortlist_state(session_dir: Path) -> dict:
    session_dir = Path(session_dir)
    state = load_session(session_dir)
    return _public_state(state, _decisions(session_dir, state))


def save_shortlist_decision(session_dir: Path, source_id: str, decision: str) -> dict:
    session_dir = Path(session_dir)
    source_id = validate_identifier(source_id)
    if decision not in ('keep', 'skip', 'unreviewed'):
        raise VibeError('Decision must be keep, skip, or unreviewed')
    # Validate the session before creating its writer lock.
    load_session(session_dir)
    with _file_lock(session_dir / 'writer.lock', purpose='save audition shortlist'):
        state = load_session(session_dir)
        if source_id not in source_ids(state):
            raise VibeError('Source is not registered in this audition')
        saved = _decisions(session_dir, state)
        if decision == 'keep':
            verify_source(state, source_id)
        if decision == 'unreviewed':
            saved.pop(source_id, None)
        else:
            saved[source_id] = decision
        write_json(session_dir / 'shortlist.json', {'schema_version': 1,
            'decisions': saved, 'updated_at': datetime.now(timezone.utc).isoformat()})
        return _public_state(state, saved)


def _kept(session_dir: Path, state: dict) -> list[tuple[str, Path]]:
    saved = _decisions(session_dir, state)
    kept = [(source_id, Path(state['sources'][source_id]['path']))
            for source_id in source_ids(state) if saved.get(source_id) == 'keep']
    if not kept:
        raise VibeError('Keep at least one sample before saving a playlist or curation packet')
    return kept


def shortlist_playlist(session_dir: Path) -> str:
    """Return paths to verified originals, never browser previews or mixes."""
    session_dir = Path(session_dir)
    state = load_session(session_dir)
    paths = [str(verify_source(state, source_id)) for source_id, _ in _kept(session_dir, state)]
    if any('\n' in path or '\r' in path for path in paths):
        raise VibeError('Playlist paths cannot contain newline characters')
    return '#EXTM3U\n' + ''.join(path + '\n' for path in paths)


def _handoff_database(state: dict, database_path: Path | None):
    from .inventory import LibraryDatabase
    from .state import resolve_library_db
    root = Path(state['root']).resolve()
    path = resolve_library_db(root, database_path)
    if not path.is_file():
        raise VibeError('Library index is unavailable. Complete library onboarding and an inventory scan before creating a curation packet.')
    database = LibraryDatabase(path, readonly=True)
    database.bind_root(root, create=False)
    if database.latest_complete_scan() is None:
        raise VibeError('A complete library inventory scan is required before creating a curation packet.')
    return database


def handoff_status(session_dir: Path, database_path: Path | None = None) -> dict:
    """Cheap, read-only readiness hint; creation performs full source verification."""
    try:
        _handoff_database(load_session(Path(session_dir)), database_path)
        return {'available': True, 'reason': 'Library index is ready. Packet creation will verify the kept originals.'}
    except (ValueError, OSError, sqlite3.Error) as exc:
        return {'available': False, 'reason': str(exc)}


def create_shortlist_packet(session_dir: Path, output_dir: Path,
                            database_path: Path | None = None) -> int:
    """Create canonical keep rows; later favourite/role/descriptor approval is separate."""
    from .curate import prepare_packet
    session_dir = Path(session_dir).resolve()
    state = load_session(session_dir)
    output_dir = Path(output_dir).absolute()
    resolved = output_dir.resolve()
    if resolved.is_relative_to(Path(state['root']).resolve()):
        raise VibeError('Curation packet output must be outside the source library')
    if session_dir.is_relative_to(resolved) or (resolved.is_relative_to(session_dir)
            and (not resolved.is_relative_to(session_dir / 'curation-packets')
                 or resolved == session_dir / 'curation-packets')):
        raise VibeError('Curation packet output must use a new curation-packets subdirectory or a directory outside the audition')
    with _file_lock(session_dir / 'writer.lock', purpose='prepare audition shortlist packet'):
        state = load_session(session_dir)
        candidates = _kept(session_dir, state)
        database = _handoff_database(state, database_path)
        # prepare_packet verifies current inventory membership, original bytes and paths.
        return prepare_packet(Path(state['root']).resolve(), database, output_dir,
                              explicit_candidates=candidates)
