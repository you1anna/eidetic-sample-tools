"""Immutable, unreviewed collection plans; no audio or indexed metadata mutation."""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil

from .collection_history import load_history, validate_history_snapshot
from .collection_snapshot import capture, identity, integer, text, validate_snapshot
from .find import Query
from .locking import library_lock
from .state import library_identity

DEVICES = {'octatrack', 'digitakt', 'tr8s'}
FRESHNESS = {'exclude', 'prefer-new', 'allow'}
METHOD = 'metadata-filter-seeded-v1'
MAX_PLAN_BYTES = 128 * 1024 * 1024


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _policy(device, count, freshness, brief, seed):
    if not isinstance(device, str) or device not in DEVICES:
        raise ValueError('device must be octatrack, digitakt or tr8s')
    if not isinstance(freshness, str) or freshness not in FRESHNESS:
        raise ValueError('freshness must be exclude, prefer-new or allow')
    return {'device': device, 'count': integer(count, 'count', 1), 'freshness': freshness,
            'brief': text(brief, 'brief', empty=True), 'seed': integer(seed, 'seed'),
            'method': METHOD, 'brief_interpretation': 'recorded_context_only'}


def _assemble(snapshot, history, policy, pins=(), parent_plan_id=None, created_at=None):
    prior = set(history['sample_ids'])
    if policy['freshness'] != 'allow' and history['coverage'] == 'unknown':
        raise ValueError('this freshness mode requires supplied history; use allow to plan with unknown history')
    candidates = snapshot['candidates']
    eligible = {r['sample_id']: r for r in candidates
                if policy['freshness'] != 'exclude' or r['sample_id'] not in prior}
    pin_set = set(pins)
    pins = sorted(pin_set)
    if not pin_set <= eligible.keys():
        raise ValueError('a pin is absent from the eligible population or excluded by freshness')
    if len(pins) > policy['count']:
        raise ValueError('requested count is smaller than the number of retained pins')

    def rank(sid):
        return (policy['freshness'] == 'prefer-new' and sid in prior,
                hashlib.sha256(f"{policy['seed']}:{sid}".encode()).hexdigest(), sid)

    order = pins + sorted((sid for sid in eligible if sid not in pin_set), key=rank)
    chosen = order[:policy['count']]
    selected = []
    for sid in chosen:
        status = ('unknown' if history['coverage'] == 'unknown' else
                  'recorded_export' if sid in prior else 'not_in_supplied_history')
        selected.append({'sample_id': sid, 'decision': 'unreviewed', 'history_status': status,
                         'pinned': sid in pin_set,
                         'reason': 'Retained pin; not listening approval.' if sid in pin_set else
                         'Matches metadata filters; chosen by reproducible seeded ordering.'})
    fixed = {k: v for k, v in policy.items() if k not in {'count', 'seed'}}
    plan = {'format': 'eidetic-collection-plan', 'version': 1,
            'collection_id': _digest({'snapshot': snapshot, 'history': history, 'policy': fixed}),
            'parent_plan_id': parent_plan_id, 'created_at': created_at or datetime.now(timezone.utc).isoformat(),
            'snapshot': snapshot, 'history': history, 'policy': policy, 'pins': pins, 'selected': selected,
            'summary': {'matching_identities': len(candidates), 'eligible_identities': len(eligible),
                        'excluded_previous': len(candidates) - len(eligible), 'requested': policy['count'],
                        'selected': len(selected), 'shortage': policy['count'] - len(selected),
                        'known_repeats': sum(sid in prior for sid in chosen),
                        'unknown_history': len(selected) if history['coverage'] == 'unknown' else 0}}
    plan['plan_id'] = _digest({k: v for k, v in plan.items() if k != 'created_at'})
    return plan


def create_plan(root: Path, *, device: str, count: int, freshness: str, query: Query,
                brief: str, seed: int, history_paths=(), library_db: Path | None = None) -> dict:
    policy = _policy(device, count, freshness, brief, seed)
    snapshot = capture(root, query, library_db)
    history = load_history(history_paths, library_id=snapshot['library_id'], device=device)
    return _assemble(snapshot, history, policy)


def validate_plan(plan):
    keys = {'format', 'version', 'collection_id', 'parent_plan_id', 'created_at', 'snapshot',
            'history', 'policy', 'pins', 'selected', 'summary', 'plan_id'}
    if not isinstance(plan, dict) or set(plan) != keys:
        raise ValueError('invalid collection plan structure')
    if plan['format'] != 'eidetic-collection-plan' or type(plan['version']) is not int or plan['version'] != 1:
        raise ValueError('unsupported collection plan format or version')
    identity(plan['plan_id'])
    if plan['plan_id'] != _digest({k: v for k, v in plan.items() if k not in {'plan_id', 'created_at'}}):
        raise ValueError('collection plan content digest changed')
    identity(plan['collection_id'])
    if plan['parent_plan_id'] is not None:
        identity(plan['parent_plan_id'])
    try:
        timestamp = datetime.fromisoformat(plan['created_at'])
        if timestamp.tzinfo is None:
            raise ValueError('timestamp needs timezone')
    except (TypeError, ValueError) as exc:
        raise ValueError('invalid plan creation timestamp') from exc
    snapshot = validate_snapshot(plan['snapshot'])
    raw = plan['policy']
    if not isinstance(raw, dict) or set(raw) != {'device', 'count', 'freshness', 'brief', 'seed', 'method', 'brief_interpretation'}:
        raise ValueError('invalid collection policy')
    policy = _policy(raw['device'], raw['count'], raw['freshness'], raw['brief'], raw['seed'])
    if raw != policy:
        raise ValueError('unsupported collection selection method')
    history = validate_history_snapshot(plan['history'], library_id=snapshot['library_id'], device=policy['device'])
    pins = plan['pins']
    if not isinstance(pins, list):
        raise ValueError('invalid pins')
    for pin in pins:
        identity(pin)
    if pins != sorted(set(pins)):
        raise ValueError('duplicate or noncanonical pins')
    expected = _assemble(snapshot, history, policy, pins, plan['parent_plan_id'], plan['created_at'])
    if plan != expected:
        raise ValueError('collection plan content or digest changed; create a new plan instead of editing it')
    return plan


def regenerate_plan(parent, *, seed: int, count: int | None = None, pins=()) -> dict:
    validate_plan(parent)
    integer(seed, 'seed')
    pins = list(pins)
    for pin in pins:
        identity(pin)
    if not set(pins) <= {row['sample_id'] for row in parent['selected']}:
        raise ValueError('additional pins must be selected in the parent plan')
    policy = dict(parent['policy'], seed=seed)
    if count is not None:
        policy['count'] = integer(count, 'count', 1)
    return _assemble(deepcopy(parent['snapshot']), deepcopy(parent['history']), policy,
                     set(parent['pins']) | set(pins), parent['plan_id'])


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key in collection plan')
        result[key] = value
    return result


def read_plan(path: Path) -> dict:
    path = Path(path)
    if path.is_symlink():
        raise ValueError('collection plan must not be a symlink')
    if path.is_dir():
        path = path / 'plan.json'
    if path.is_symlink() or not path.is_file():
        raise ValueError('collection plan file is missing or a symlink')
    if path.stat().st_size > MAX_PLAN_BYTES:
        raise ValueError('collection plan exceeds the supported file size')
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_PLAN_BYTES + 1)
        if len(raw) > MAX_PLAN_BYTES:
            raise ValueError('collection plan exceeds the supported file size')
        plan = json.loads(raw.decode('utf-8'), object_pairs_hook=_json_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite plan value')))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('invalid collection plan JSON') from exc
    return validate_plan(plan)


def review_markdown(plan):
    validate_plan(plan)
    summary, policy = plan['summary'], plan['policy']
    def safe(value):
        return re.sub(r'([\\`*{}\[\]()!_#>|~])', r'\\\1', html.escape(str(value)))
    rows = ['# Candidate collection', '',
            f"{summary['selected']} of {summary['requested']} requested candidates for {policy['device']}.",
            f"Known repeats: {summary['known_repeats']}. Shortage: {summary['shortage']}. Pins: {len(plan['pins'])}.", '',
            f"Brief (recorded context): {safe(policy['brief']) or 'None supplied'}", '',
            'Selection uses explicit metadata filters and seeded ordering. The brief is not interpreted by AI.',
            'All candidates are unreviewed. This plan is not an approved collection or an export crate.', '',
            'History covers only the supplied export records. Absence is not proof a sound was never used;',
            'export records do not establish current device presence. Device capacity has not been checked.', '',
            f"Freshness: {policy['freshness']}; seed: {policy['seed']}; history: {plan['history']['coverage']}.",
            f"Indexed identities: {plan['snapshot']['indexed_identities']}; matching: {summary['matching_identities']}; eligible: {summary['eligible_identities']}.", '',
            '| Sample ID | Candidate | Known history | Pin |', '|---|---|---|---|']
    candidates = {row['sample_id']: row for row in plan['snapshot']['candidates']}
    for row in plan['selected']:
        rows.append(f"| {row['sample_id']} | {safe(candidates[row['sample_id']]['path'])} | {row['history_status']} | {'yes' if row['pinned'] else ''} |")
    return '\n'.join(rows) + '\n'


@contextmanager
def _publication_lock(output: Path, library_id: str):
    state = next((parent for parent in output.parents if parent.name == '.eidetic'), None)
    if state is None:
        yield
        return
    root = state.parent
    if library_identity(root) != library_id:
        raise ValueError('output library identity must match the saved collection')
    with library_lock(root, purpose='save collection plan'):
        if library_identity(root) != library_id:
            raise ValueError('output library identity changed before publication')
        yield


def write_plan(plan, output_dir: Path, *, parent_dir: Path | None = None) -> Path:
    validate_plan(plan)
    output = Path(output_dir).absolute()
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError('collection output path must not contain symlinks')
    if parent_dir is not None and output.resolve().is_relative_to(Path(parent_dir).resolve()):
        raise ValueError('new output must be outside the parent plan directory')
    if output.exists():
        raise ValueError('collection output already exists; choose a new directory')
    payload = json.dumps(plan, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False) + '\n'
    if len(payload.encode()) > MAX_PLAN_BYTES:
        raise ValueError('collection plan exceeds the supported file size')
    review = review_markdown(plan)
    with _publication_lock(output, plan['snapshot']['library_id']):
        output.mkdir(parents=True, exist_ok=False)
        try:
            for name, contents in [('REVIEW.md', review), ('plan.json', payload)]:
                with (output / name).open('x', encoding='utf-8') as stream:
                    stream.write(contents)
                    stream.flush()
                    os.fsync(stream.fileno())
        except BaseException:
            shutil.rmtree(output)
            raise
    return output / 'plan.json'
