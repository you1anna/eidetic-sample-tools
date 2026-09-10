"""Guarded, allowlisted plans. Journal before each send; reconcile without replay."""
from __future__ import annotations
from contextlib import nullcontext
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import uuid

from .client import LiveError, json_value

TRACK = r'live_set tracks \d+'
SLOT = TRACK + r' clip_slots \d+'
CLIP = SLOT + r' clip'
PARAMETER = TRACK + r'(?: devices \d+(?: chains \d+ devices \d+)*) parameters \d+'
NATIVE_EFFECTS = frozenset(('EQ Eight', 'Auto Filter', 'Utility', 'Compressor', 'Glue Compressor', 'Saturator', 'Reverb', 'Delay', 'Echo', 'Limiter'))
OPS = {
    'set_parameter': {'op', 'path', 'value'},
    'insert_device': {'op', 'path', 'device', 'index'},
    'duplicate_template': {'op', 'path', 'name'},
    'create_clip': {'op', 'path', 'length', 'file_path', 'name'},
    'name_clip': {'op', 'path', 'name'},
    'place_clip': {'op', 'path', 'clip_path', 'start'},
}


def _hash(path):
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise LiveError('Expected a regular file')
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'path': str(source), 'sha256': digest.hexdigest(), 'bytes': source.stat().st_size}


def _verify_file(record):
    if _hash(record['path']) != record:
        raise LiveError('File bytes changed since planning')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _write(path, value, *, exclusive=False):
    target = Path(path).expanduser().absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        with target.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        return
    descriptor, name = tempfile.mkstemp(prefix='.' + target.name, dir=target.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _number(value, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise LiveError('Expected a finite number in range')
    return value


def _validate(op):
    if not isinstance(op, dict) or op.get('op') not in OPS or set(op) - OPS[op['op']]:
        raise LiveError('Unsupported operation or field')
    kind, path = op['op'], op.get('path', '')
    pattern = PARAMETER if kind == 'set_parameter' else SLOT if kind == 'create_clip' else CLIP if kind == 'name_clip' else TRACK
    if not isinstance(path, str) or not re.fullmatch(pattern, path):
        raise LiveError('Operation target must be an explicit canonical Live path')
    if kind in ('name_clip', 'duplicate_template', 'create_clip'):
        if not isinstance(op.get('name'), str) or not op['name'].strip() or len(op['name']) > 256:
            raise LiveError('Explicit non-empty name required (maximum 256 characters)')
    if kind == 'set_parameter':
        _number(op.get('value'), -float('inf'))
    if kind == 'insert_device':
        if op.get('device') not in NATIVE_EFFECTS:
            raise LiveError('Device is outside the native audio-effect allowlist')
        if type(op.get('index')) is not int or op['index'] < 0:
            raise LiveError('Explicit insertion index required')
    if kind == 'create_clip':
        if bool(op.get('file_path')) == ('length' in op):
            raise LiveError('Supply exactly one of MIDI length or audio file_path')
        if 'length' in op and _number(op['length']) <= 0:
            raise LiveError('Clip length must be positive')
        if 'file_path' in op and not Path(op['file_path']).is_absolute():
            raise LiveError('Audio source path must be absolute')
    if kind == 'place_clip':
        if not re.fullmatch(CLIP, op.get('clip_path', '')) or not op['clip_path'].startswith(path + ' clip_slots '):
            raise LiveError('Source must be a Session clip on the explicit destination track')
        if _number(op.get('start')) > 1576800:
            raise LiveError('Arrangement start exceeds Live range')


def _roster(client, path, child):
    return [{key: row[key] for key in ('id', 'index', 'path')} for row in client.children(path, child)]


def _observe(client, op):
    kind, path = op['op'], op['path']
    state = {'id': client.get(path, 'id')}
    if kind == 'set_parameter':
        for prop in ('name', 'value', 'min', 'max', 'is_enabled', 'is_quantized'):
            state[prop] = client.get(path, prop)
    elif kind == 'name_clip':
        state['name'] = client.get(path, 'name')
    elif kind == 'insert_device':
        state['devices'] = _roster(client, path, 'devices')
    elif kind == 'duplicate_template':
        state['tracks'] = _roster(client, 'live_set', 'tracks')
        state['name'] = client.get(path, 'name')
        state['devices'] = _roster(client, path, 'devices')
        state['clip_slots'] = _roster(client, path, 'clip_slots')
        # Template fingerprint includes exposed values and existing clips, not merely IDs.
        state['parameters'] = []
        for device in state['devices']:
            for parameter in client.children(device['path'], 'parameters'):
                state['parameters'].append({'id': parameter['id'], 'value': client.get(parameter['path'], 'value')})
        state['clips'] = []
        for slot in state['clip_slots']:
            has_clip = bool(client.get(slot['path'], 'has_clip'))
            state['clips'].append({'id': client.get(slot['path'] + ' clip', 'id') if has_clip else None})
    elif kind == 'create_clip':
        state['has_clip'] = bool(client.get(path, 'has_clip'))
        track_path = path.rsplit(' clip_slots ', 1)[0]
        state['has_audio_input'] = client.get(track_path, 'has_audio_input')
        state['has_midi_input'] = client.get(track_path, 'has_midi_input')
    elif kind == 'place_clip':
        source = op['clip_path']
        state['source'] = {'id': client.get(source, 'id'), 'name': client.get(source, 'name'), 'length': client.get(source, 'length')}
        state['clips'] = _roster(client, path, 'arrangement_clips')
        for clip in state['clips']:
            clip['start'] = client.get(clip['path'], 'start_time')
            clip['end'] = client.get(clip['path'], 'end_time')
    return state


def _preflight(op, before):
    kind = op['op']
    if kind == 'set_parameter':
        if not before['is_enabled'] or not before['min'] <= op['value'] <= before['max']:
            raise LiveError('Parameter disabled or outside its exposed range')
        if before['is_quantized'] and int(op['value']) != op['value']:
            raise LiveError('Quantised parameter requires an integer value')
    if kind == 'create_clip':
        if before['has_clip']:
            raise LiveError('Clip slot is occupied; replacement is not allowed')
        if not before['has_audio_input' if 'file_path' in op else 'has_midi_input']:
            raise LiveError('Clip type does not match track')
    if kind == 'insert_device' and op['index'] > len(before['devices']):
        raise LiveError('Insertion index exceeds device chain')
    if kind == 'place_clip':
        length = _number(before['source']['length'])
        end = op['start'] + length
        if length <= 0 or end > 1576800:
            raise LiveError('Invalid arrangement interval')
        if any(op['start'] < clip['end'] and end > clip['start'] for clip in before['clips']):
            raise LiveError('Arrangement destination overlaps an existing clip')


def _stopped(client):
    if client.get('live_set', 'is_playing') or client.get('live_set', 'record_mode') or client.get('live_set', 'session_record'):
        raise LiveError('Stop transport and recording before structural edits')


def _identity(client):
    identity = client.runtime()
    if not identity['set_path'] or not Path(identity['set_path']).is_absolute():
        raise LiveError('Save the intended Live Set before planning edits')
    return identity


def plan_edits(client, operations, checkpoint=None):
    if not isinstance(operations, list) or not operations or len(operations) > 32:
        raise LiveError('Plan must contain between 1 and 32 explicit operations')
    for op in operations:
        _validate(op)
    # Structural index changes invalidate later path assumptions. Use a fresh plan afterwards.
    if len(operations) > 1 and any(op['op'] != 'set_parameter' for op in operations):
        raise LiveError('Structural/name plans contain one operation; inspect and replan between them')
    if len({op['path'] for op in operations}) != len(operations):
        raise LiveError('Duplicate targets in one plan are not supported')
    with client.exclusive():
        identity = _identity(client)
        structural = any(op['op'] != 'set_parameter' for op in operations)
        source_set = _hash(identity['set_path'])
        saved_checkpoint = None
        if structural:
            _stopped(client)
            if not checkpoint:
                raise LiveError('Structural edits require an explicit saved .als checkpoint copy')
            saved_checkpoint = _hash(checkpoint)
            if not saved_checkpoint['path'].endswith('.als') or saved_checkpoint['path'] == source_set['path'] or saved_checkpoint['sha256'] != source_set['sha256']:
                raise LiveError('Checkpoint must be a separate .als copy matching the saved Set bytes')
        entries = []
        for operation in operations:
            op = copy.deepcopy(operation)
            before = _observe(client, op)
            _preflight(op, before)
            item = {'operation': op, 'before': before}
            if 'file_path' in op:
                item['source_file'] = _hash(op['file_path'])
            entries.append(item)
        if client.runtime() != identity:
            raise LiveError('Runtime identity changed during planning')
        plan = {'schema': 'eidetic-live.edit-plan', 'schema_version': 1, 'plan_id': uuid.uuid4().hex,
                'identity': identity, 'saved_set': source_set, 'checkpoint': saved_checkpoint,
                'structural': structural, 'operations': entries,
                'checkpoint_note': 'Checkpoint covers saved bytes. Save Live manually before copying; unsaved edits are not captured.'}
        plan['digest'] = _digest(plan)
        return plan


def _validate_plan(plan):
    payload = {k: v for k, v in plan.items() if k != 'digest'}
    if plan.get('schema') != 'eidetic-live.edit-plan' or plan.get('schema_version') != 1 or plan.get('digest') != _digest(payload):
        raise LiveError('Invalid or changed edit plan')
    operations = plan.get('operations', [])
    if not 1 <= len(operations) <= 32:
        raise LiveError('Invalid operation count')
    for entry in operations:
        _validate(entry['operation'])
    structural = any(e['operation']['op'] != 'set_parameter' for e in operations)
    if structural != plan['structural'] or structural and (len(operations) != 1 or not plan.get('checkpoint')):
        raise LiveError('Invalid structural plan gate')


def _execute(client, op, before, identity):
    kind, path = op['op'], op['path']
    if kind == 'set_parameter':
        client.request('/api/parameter_set', [path, json_value(op['value'])], write=True)
    elif kind == 'name_clip':
        client.set(path, 'name', op['name'])
    elif kind == 'insert_device':
        client.request('/api/insert_device', [path, op['device'], str(op['index'])], write=True)
    elif kind == 'duplicate_template':
        index = int(path.rsplit(' ', 1)[1])
        client.call('live_set', 'duplicate_track', [index])
        tracks = _roster(client, 'live_set', 'tracks')
        previous = {row['id'] for row in before['tracks']}
        added = [row for row in tracks if row['id'] not in previous]
        if len(added) != 1 or added[0]['index'] != index + 1:
            raise LiveError('Track duplication readback mismatch')
        if client.runtime() != identity or client.get(added[0]['path'], 'id') != added[0]['id']:
            raise LiveError('Runtime or duplicated track identity changed before naming')
        _stopped(client)
        client.set(added[0]['path'], 'name', op['name'])
    elif kind == 'create_clip':
        client.call(path, 'create_audio_clip' if 'file_path' in op else 'create_clip',
                    [op['file_path']] if 'file_path' in op else [op['length']])
        created_id = client.get(path + ' clip', 'id')
        if client.runtime() != identity or client.get(path, 'id') != before['id'] or client.get(path + ' clip', 'id') != created_id:
            raise LiveError('Runtime or created clip identity changed before naming')
        _stopped(client)
        client.set(path + ' clip', 'name', op['name'])
    elif kind == 'place_clip':
        client.call(path, 'duplicate_clip_to_arrangement', ['id ' + str(before['source']['id']), op['start']])


def _same_number(actual, expected):
    return isinstance(actual, (float, int)) and math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-6)


def _readback(client, entry):
    op, before = entry['operation'], entry['before']
    kind, path = op['op'], op['path']
    if client.get(path, 'id') != before['id']:
        raise LiveError('Target identity changed')
    if kind == 'set_parameter':
        actual = client.get(path, 'value')
        if not _same_number(actual, op['value']):
            raise LiveError('Parameter readback differs from requested value')
        return {'id': before['id'], 'value': actual}
    if kind == 'name_clip':
        actual = client.get(path, 'name')
        if actual != op['name']:
            raise LiveError('Clip name readback mismatch')
        return {'id': before['id'], 'name': actual}
    if kind == 'create_clip':
        if not client.get(path, 'has_clip'):
            raise LiveError('Created clip is absent')
        clip_path = path + ' clip'
        actual = {'id': client.get(clip_path, 'id'), 'name': client.get(clip_path, 'name')}
        if actual['name'] != op['name']:
            raise LiveError('Created clip name differs')
        if 'file_path' in op:
            actual['file_path'] = client.get(clip_path, 'file_path')
            if str(Path(actual['file_path']).resolve()) != entry['source_file']['path']:
                raise LiveError('Created audio source differs')
        else:
            actual['length'] = client.get(clip_path, 'length')
            if not _same_number(actual['length'], op['length']):
                raise LiveError('Created MIDI length differs')
        return actual
    child = 'devices' if kind == 'insert_device' else 'tracks' if kind == 'duplicate_template' else 'arrangement_clips'
    parent = 'live_set' if kind == 'duplicate_template' else path
    old = before['devices' if kind == 'insert_device' else 'tracks' if kind == 'duplicate_template' else 'clips']
    rows = _roster(client, parent, child)
    old_ids = {row['id'] for row in old}
    new = [row for row in rows if row['id'] not in old_ids]
    if len(rows) != len(old) + 1 or len(new) != 1 or not old_ids <= {r['id'] for r in rows}:
        raise LiveError('Structural readback count/identity mismatch')
    added = new[0]
    added['name'] = client.get(added['path'], 'name')
    if kind == 'insert_device':
        if added['index'] != op['index'] or added['name'] != op['device']:
            raise LiveError('Inserted device location/name differs')
    elif kind == 'duplicate_template':
        if added['index'] != int(path.rsplit(' ', 1)[1]) + 1 or added['name'] != op['name']:
            raise LiveError('Duplicated track location/name differs')
        if len(client.children(added['path'], 'devices')) != len(before['devices']):
            raise LiveError('Duplicated template device count differs')
    else:
        added['start'] = client.get(added['path'], 'start_time')
        added['end'] = client.get(added['path'], 'end_time')
        if not _same_number(added['start'], op['start']) or not _same_number(added['end'] - added['start'], before['source']['length']):
            raise LiveError('Arrangement placement readback differs')
    return added


def apply_plan(client, plan, receipt_path=None):
    """Apply an explicitly reviewed plan once, returning complete or partial receipt."""
    _validate_plan(plan)
    if receipt_path is None:
        raise LiveError('A fresh receipt_path is required before any mutation')
    receipt = {'schema': 'eidetic-live.edit-receipt', 'schema_version': 1,
               'receipt_id': uuid.uuid4().hex, 'plan': copy.deepcopy(plan), 'status': 'prepared',
               'complete': False, 'operations': []}
    with client.exclusive():
        if _identity(client) != plan['identity']:
            raise LiveError('Set/build/instance identity changed; replan')
        _verify_file(plan['saved_set'])
        if plan['structural']:
            _stopped(client)
            _verify_file(plan['checkpoint'])
        for entry in plan['operations']:
            if _observe(client, entry['operation']) != entry['before']:
                raise LiveError('Expected before-state changed; replan')
            _preflight(entry['operation'], entry['before'])
            if 'source_file' in entry:
                _verify_file(entry['source_file'])
        _write(receipt_path, receipt, exclusive=True)
        for entry in plan['operations']:
            result = {'status': 'in_flight', 'operation': entry['operation']}
            receipt['operations'].append(result)
            receipt['status'] = 'applying'
            _write(receipt_path, receipt)
            try:
                if client.runtime() != plan['identity'] or _observe(client, entry['operation']) != entry['before']:
                    raise LiveError('Identity or before-state changed immediately before edit')
                if plan['structural']:
                    _stopped(client)
                if 'source_file' in entry:
                    _verify_file(entry['source_file'])
                _execute(client, entry['operation'], entry['before'], plan['identity'])
                result['after'] = _readback(client, entry)
                result['status'] = 'verified'
            except (LiveError, OSError, ValueError, KeyError, TypeError) as exc:
                result['status'] = 'unknown'
                result['error'] = str(exc) if isinstance(exc, LiveError) else 'Execution/readback failed'
                receipt['status'] = 'partial'
                _write(receipt_path, receipt)
                return receipt
            _write(receipt_path, receipt)
        receipt['status'], receipt['complete'] = 'verified', True
        receipt['persistence'] = 'Live memory readback verified; save the Set manually and inspect after reload.'
        _write(receipt_path, receipt)
    return receipt


def reconcile(client, receipt):
    """Read-only recovery. Never repeat an uncertain write."""
    if receipt.get('schema') != 'eidetic-live.edit-receipt' or receipt.get('schema_version') != 1:
        raise LiveError('Unsupported receipt')
    plan = receipt['plan']
    _validate_plan(plan)
    result = {'schema': 'eidetic-live.reconciliation', 'schema_version': 1,
              'receipt_id': receipt['receipt_id'], 'complete': False, 'operations': []}
    with client.exclusive():
        if client.runtime() != plan['identity']:
            result['error'] = 'Runtime identity changed; reconcile manually'
            return result
        for index, entry in enumerate(plan['operations']):
            if index >= len(receipt['operations']):
                result['operations'].append({'status': 'not_attempted'})
                continue
            try:
                after = _readback(client, entry)
                result['operations'].append({'status': 'verified_present', 'after': after})
            except LiveError:
                try:
                    unchanged = _observe(client, entry['operation']) == entry['before']
                except LiveError:
                    unchanged = False
                result['operations'].append({'status': 'before_state_present' if unchanged else 'unknown_or_partial'})
        result['complete'] = all(row['status'] == 'verified_present' for row in result['operations'])
    return result


def retain_bounce(receipt_path, audio_path, output_path):
    """Bind an explicitly exported WAV to its receipt; does not render audio."""
    import wave
    receipt = json.loads(Path(receipt_path).read_text())
    if receipt.get('schema') != 'eidetic-live.edit-receipt':
        raise LiveError('Expected an edit receipt')
    source = _hash(audio_path)
    if Path(audio_path).suffix.lower() != '.wav':
        raise LiveError('Bounce lineage currently accepts WAV exports')
    reader = wave.open
    try:
        with reader(str(audio_path), 'rb') as audio:
            metadata = {'channels': audio.getnchannels(), 'sample_rate': audio.getframerate(),
                        'sample_width': audio.getsampwidth(), 'frames': audio.getnframes()}
    except (OSError, EOFError, wave.Error):
        raise LiveError('Bounce must be a readable WAV') from None
    result = {'schema': 'eidetic-live.bounce-lineage', 'schema_version': 1, 'receipt': _hash(receipt_path),
              'receipt_id': receipt['receipt_id'], 'receipt_status': receipt.get('status'),
              'audio': {**source, **metadata}, 'render_verified': False,
              'note': 'User-supplied export linked by explicit command; this does not prove its render source.'}
    _write(output_path, result, exclusive=True)
    return result


def restore_parameters(client, receipt):
    """Build a fresh restore plan only when the applied parameter values remain."""
    if receipt.get('schema') != 'eidetic-live.edit-receipt' or receipt.get('schema_version') != 1 or receipt.get('complete') is not True:
        raise LiveError('Restoration requires a complete verified edit receipt')
    plan = receipt['plan']
    _validate_plan(plan)
    if any(entry['operation']['op'] != 'set_parameter' for entry in plan['operations']):
        raise LiveError('Only exposed parameter edits support restoration plans')
    with client.exclusive():
        if client.runtime() != plan['identity']:
            raise LiveError('Runtime identity changed; restoration requires a fresh manual review')
        operations = []
        for entry in plan['operations']:
            _readback(client, entry)
            operations.append({'op': 'set_parameter', 'path': entry['operation']['path'], 'value': entry['before']['value']})
        return plan_edits(client, operations)
