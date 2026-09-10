"""Read-only defaults; edits require an explicit saved plan and --apply."""
import argparse
import json
import os
from pathlib import Path
import sys

from . import LiveClient, LiveError
from .edits import plan_edits, apply_plan, reconcile, retain_bounce, restore_parameters, _write
from .reports import diff_snapshots, check_snapshot, doctor
from .staging import stage


def _read(path):
    return json.loads(Path(path).read_text())


def main(argv=None):
    parser = argparse.ArgumentParser(prog='eidetic-live')
    parser.add_argument('--summary', action='store_true', help='Print a concise human summary; output files remain JSON')
    parser.add_argument('--config', help='Local JSON transport configuration; token comes from environment')
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect', help='Read the loaded Set')
    inspect.add_argument('--detail', action='store_true')
    inspect.add_argument('--output')
    diff = commands.add_parser('diff', help='Compare two saved snapshots without contacting Live')
    diff.add_argument('before')
    diff.add_argument('after')
    diff.add_argument('--output')
    check = commands.add_parser('check', help='Check explicit routing/monitor expectations')
    check.add_argument('--profile', required=True)
    check.add_argument('--snapshot')
    check.add_argument('--output')
    commands.add_parser('doctor', help='Check runtime identity and protocol; no edits')
    staging = commands.add_parser('stage-device', help='Stage isolated source files; does not install a device')
    staging.add_argument('destination')
    staging.add_argument('--port', type=int, default=9000)
    staging.add_argument('--ack-port', type=int, default=9001)
    plan = commands.add_parser('plan', help='Preview allowlisted operations into a saved plan')
    plan.add_argument('operations', help='JSON array of operations')
    plan.add_argument('--checkpoint')
    plan.add_argument('--output', required=True)
    apply = commands.add_parser('apply', help='Apply a reviewed plan once')
    apply.add_argument('plan')
    apply.add_argument('--apply', action='store_true', required=True)
    apply.add_argument('--receipt', required=True)
    restore = commands.add_parser('restore-parameters', help='Plan a guarded restore of verified parameter values')
    restore.add_argument('receipt')
    restore.add_argument('--output', required=True)
    recovery = commands.add_parser('reconcile', help='Read-only outcome reconciliation; never retries writes')
    recovery.add_argument('receipt')
    recovery.add_argument('--output')
    bounce = commands.add_parser('retain-bounce', help='Link a manually exported WAV to an edit receipt')
    bounce.add_argument('--receipt', required=True)
    bounce.add_argument('--audio', required=True)
    bounce.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        if args.config:
            os.environ['EIDETIC_LIVE_CONFIG'] = str(Path(args.config).expanduser())
        if args.command == 'stage-device':
            result = stage(args.destination, args.port, args.ack_port)
        elif args.command == 'diff':
            result = diff_snapshots(_read(args.before), _read(args.after))
        elif args.command == 'retain-bounce':
            result = retain_bounce(args.receipt, args.audio, args.output)
        elif args.command == 'check' and args.snapshot:
            result = check_snapshot(_read(args.snapshot), _read(args.profile))
        else:
            client = LiveClient()
            if args.command == 'inspect':
                result = client.inspect(args.detail)
            elif args.command == 'doctor':
                result = doctor(client)
            elif args.command == 'check':
                result = check_snapshot(client.inspect(), _read(args.profile))
            elif args.command == 'plan':
                result = plan_edits(client, _read(args.operations), args.checkpoint)
            elif args.command == 'restore-parameters':
                result = restore_parameters(client, _read(args.receipt))
            elif args.command == 'apply':
                result = apply_plan(client, _read(args.plan), args.receipt)
            else:
                result = reconcile(client, _read(args.receipt))
        if getattr(args, 'output', None) and args.command != 'retain-bounce':
            _write(args.output, result, exclusive=True)
        print(_summary(result) if args.summary else json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 2 if result.get('complete') is False or result.get('status') in ('fail', 'unverified', 'partial') else 0
    except (LiveError, OSError, ValueError, KeyError, TypeError) as exc:
        # Never include raw protocol arguments or the authentication environment.
        print(json.dumps({'schema': 'eidetic-live.error', 'schema_version': 1, 'complete': False,
                          'error': str(exc) if isinstance(exc, LiveError) else type(exc).__name__}), file=sys.stderr)
        return 2


def _summary(result):
    kind = result.get('schema', 'eidetic-live.result').removeprefix('eidetic-live.')
    state = result.get('status', 'complete' if result.get('complete') is True else 'incomplete' if result.get('complete') is False else 'recorded')
    lines = [f'{kind}: {state}']
    identity = result.get('identity') or result.get('checks', {}).get('runtime')
    if identity:
        lines.append(f"Set: {identity.get('set_name', '')} ({identity.get('set_path', '')})")
        lines.append(f"Runtime: {identity.get('build_id', '')}; instance {identity.get('instance_id', '')}")
    transport = result.get('transport')
    if transport:
        lines.append(f"Transport: {'playing' if transport.get('playing') else 'stopped'}; tempo {transport.get('tempo')}")
    if 'tracks' in result:
        lines.append(f"Tracks: {len(result['tracks'])}")
        for track in result['tracks']:
            lines.append(f"  {track.get('index', '?')}: {track.get('name', '(unread)')} — {len(track.get('devices', []))} devices; monitor {track.get('current_monitoring_state', 'unavailable')}")
    if 'changes' in result:
        lines.append(f"Changed fields: {len(result['changes'])}")
        lines.extend('  ' + row['path'] for row in result['changes'][:20])
        if len(result['changes']) > 20:
            lines.append('  More changes are available in JSON output.')
    for finding in result.get('findings', []):
        lines.append(f"  {finding.get('track', '')}: {finding.get('error') or str(finding.get('property')) + ' differs'}")
    for manual in result.get('manual_checks', []):
        lines.append('Unverified: ' + str(manual))
    for error in result.get('errors', []) + result.get('inspection_errors', []):
        lines.append('Error: ' + str(error))
    if result.get('error'):
        lines.append('Error: ' + str(result['error']))
    return '\n'.join(lines)


if __name__ == '__main__':
    raise SystemExit(main())
