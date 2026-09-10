"""Versioned inspection, comparison and expectations; incomplete is never green."""
from datetime import datetime, timezone
from .client import LiveError


def inspect_live(client, detail=False):
    report = {'schema': 'eidetic-live.snapshot', 'schema_version': 1, 'complete': False,
              'generated_at': datetime.now(timezone.utc).isoformat(), 'atomic': False,
              'identity': None, 'transport': {}, 'tracks': [], 'errors': []}
    try:
        with client.exclusive():
            report['identity'] = client.runtime()
            report['transport'] = {'playing': bool(client.get('live_set', 'is_playing')),
                                   'tempo': client.get('live_set', 'tempo'),
                                   'recording': bool(client.get('live_set', 'record_mode'))}
            tracks = client.children('live_set', 'tracks')
            for row in tracks:
                track = dict(row)
                report['tracks'].append(track)
                path = row['path']
                for prop in ('name', 'has_audio_input', 'has_midi_input', 'can_be_armed', 'mute', 'solo',
                             'input_routing_type', 'input_routing_channel', 'output_routing_type', 'output_routing_channel'):
                    track[prop] = client.get(path, prop)
                if track['can_be_armed']:
                    track['arm'] = client.get(path, 'arm')
                    track['current_monitoring_state'] = client.get(path, 'current_monitoring_state')
                track['mixer'] = client.request('/api/mixer_status', [path])['mixer']
                _require_readable_payload(track['mixer'])
                parameters = track['mixer'].get('parameters', {})
                if not all(isinstance(parameters.get(key), dict) and isinstance(parameters[key].get('value'), (int, float)) for key in ('volume', 'panning', 'track_activator')) or not isinstance(track['mixer'].get('sends'), list):
                    raise LiveError('Incomplete mixer parameters/sends')
                track['devices'] = client.children(path, 'devices')
                if detail:
                    for device in track['devices']:
                        device['class_name'] = client.get(device['path'], 'class_name')
                        device['parameters'] = client.request('/api/device_parameters', [device['path']])['parameters']
                        _require_readable_payload(device['parameters'])
                track['clip_slots'] = client.children(path, 'clip_slots')
                for slot in track['clip_slots']:
                    slot['has_clip'] = bool(client.get(slot['path'], 'has_clip'))
                    if slot['has_clip']:
                        clip_path = slot['path'] + ' clip'
                        slot['clip'] = {'path': clip_path, 'id': client.get(clip_path, 'id'), 'name': client.get(clip_path, 'name')}
                        if detail:
                            for prop in ('length', 'is_audio_clip', 'looping', 'loop_start', 'loop_end'):
                                slot['clip'][prop] = client.get(clip_path, prop)
                if detail:
                    track['arrangement_clips'] = client.children(path, 'arrangement_clips')
                    for clip in track['arrangement_clips']:
                        for prop in ('name', 'start_time', 'end_time'):
                            clip[prop] = client.get(clip['path'], prop)
            if client.runtime() != report['identity'] or [r['id'] for r in client.children('live_set', 'tracks')] != [r['id'] for r in tracks]:
                raise LiveError('Set or track roster changed during inspection')
            report['complete'] = True
    except (LiveError, KeyError, TypeError, ValueError) as exc:
        report['errors'].append(str(exc) if isinstance(exc, LiveError) else 'Malformed/incomplete inspection')
    return report


def diff_snapshots(before, after):
    changes = []
    def walk(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                if key not in ('generated_at',):
                    walk(a.get(key), b.get(key), path + '/' + key)
        elif a != b:
            changes.append({'path': path, 'before': a, 'after': b})
    walk(before, after, '')
    return {'schema': 'eidetic-live.diff', 'schema_version': 1,
            'complete': before.get('complete') is True and after.get('complete') is True,
            'changes': changes}


def check_snapshot(snapshot, profile):
    if snapshot.get('schema') != 'eidetic-live.snapshot' or snapshot.get('schema_version') != 1 or not isinstance(snapshot.get('complete'), bool) or not isinstance(snapshot.get('tracks'), list) or not isinstance(snapshot.get('identity'), dict) or not isinstance(snapshot.get('transport'), dict):
        raise LiveError('Unsupported or malformed snapshot')
    if profile.get('schema_version') != 1:
        raise LiveError('Unsupported expectation profile schema')
    if not any(profile.get(key) for key in ('tracks', 'forbid_monitoring', 'manual_checks')):
        raise LiveError('Expectation profile is empty')
    for key in ('tracks', 'forbid_monitoring', 'manual_checks'):
        if not isinstance(profile.get(key, []), list):
            raise LiveError('Expectation profile lists are malformed')
    allowed = {'name', 'input_routing_type', 'input_routing_channel', 'output_routing_type', 'output_routing_channel', 'current_monitoring_state', 'arm', 'mute', 'solo'}
    for row in profile.get('tracks', []):
        if not isinstance(row, dict) or not isinstance(row.get('name'), str) or not row['name'] or set(row) - allowed:
            raise LiveError('Malformed track expectation')
    findings = []
    tracks = snapshot.get('tracks', [])
    for expected in profile.get('tracks', []):
        matches = [row for row in tracks if row.get('name') == expected.get('name')]
        if len(matches) != 1:
            findings.append({'track': expected.get('name'), 'error': 'Track missing or ambiguous'})
            continue
        for key, value in expected.items():
            actual = matches[0].get(key)
            if isinstance(actual, dict) and isinstance(value, str):
                actual = actual.get('display_name')
            if actual != value:
                findings.append({'track': expected['name'], 'property': key, 'expected': value, 'actual': actual})
    for name in profile.get('forbid_monitoring', []):
        matches = [track for track in tracks if track.get('name') == name]
        if len(matches) != 1:
            findings.append({'track': name, 'error': 'Track missing or ambiguous'})
        elif matches[0].get('current_monitoring_state') != 2:
            findings.append({'track': name, 'error': 'Monitoring must be Off (2)'})
    manual = profile.get('manual_checks', [])
    complete = snapshot.get('complete') is True and not snapshot.get('errors')
    if complete and (not all(key in snapshot['identity'] for key in ('build_id', 'instance_id', 'set_id', 'set_path', 'set_name')) or not all(key in snapshot['transport'] for key in ('playing', 'tempo'))):
        raise LiveError('Complete snapshot lacks identity or transport evidence')
    status = 'fail' if findings else ('pass' if complete and not manual else 'unverified')
    return {'schema': 'eidetic-live.check', 'schema_version': 1, 'status': status,
            'complete': complete, 'findings': findings, 'manual_checks': manual,
            'inspection_errors': snapshot.get('errors', [])}


def doctor(client):
    report = {'schema': 'eidetic-live.doctor', 'schema_version': 1, 'complete': False,
              'checks': {}, 'hardware_verified': False}
    try:
        report['checks']['runtime'] = client.runtime()
        report['checks']['transport'] = client.request('/api/ping', [])
        report['complete'] = True
    except LiveError as exc:
        report['error'] = str(exc)
    report['manual_checks'] = ['Audio interface, sample rate, buffer and physical clock',
                               'Max device loaded once, token configured, saved Set identity matches']
    return report


def _require_readable_payload(value):
    if isinstance(value, dict):
        if value.get('error') or value.get('errors') or 'id' in value and not value['id']:
            raise LiveError('Incomplete nested API payload')
        for child in value.values():
            _require_readable_payload(child)
    elif isinstance(value, list):
        for child in value:
            _require_readable_payload(child)
