"""Audition explicit candidates and save a shortlist for human curation."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import sqlite3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='sample-vibe', description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare', help='Prepare explicit, unranked audio candidates')
    prepare.add_argument('--root', type=Path, required=True)
    prepare.add_argument('--anchor', type=Path, action='append')
    prepare.add_argument('--vocal', type=Path, action='append')
    prepare.add_argument('--plan', type=Path, help='Validated collection plan.json or plan directory')
    prepare.add_argument('--ableton-curated', type=Path, help='Validated ableton-curated.tsv view')
    prepare.add_argument('--output-dir', type=Path, required=True)
    prepare.add_argument('--bpm', type=float, default=140)
    serve = commands.add_parser('serve', help='Open a prepared audition on this Mac')
    serve.add_argument('--session-dir', type=Path, required=True)
    serve.add_argument('--port', type=int, default=0)
    serve.add_argument('--open', action='store_true')
    packet = commands.add_parser('packet', help='Hand kept originals to the existing curation workflow')
    packet.add_argument('--session-dir', type=Path, required=True)
    packet.add_argument('--output-dir', type=Path, required=True)
    packet.add_argument('--library-db', type=Path)
    playlist = commands.add_parser('playlist', help='Print an M3U8 playlist of kept original samples')
    playlist.add_argument('--session-dir', type=Path, required=True)
    relocate = commands.add_parser('rebind-root', help='Resume a v2 session after its portable library mount moves')
    relocate.add_argument('--session-dir', type=Path, required=True)
    relocate.add_argument('--root', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            if args.plan or args.ableton_curated:
                if args.anchor or args.vocal:
                    raise ValueError('Do not combine collection input with legacy anchor/vocal input')
                from .vibe_collection import prepare_collection
                state = prepare_collection(args.root, args.output_dir, plan=args.plan, curated=args.ableton_curated)
                print(f"Prepared {len(state['candidate_ids'])} candidates in lazy batches of 12: {args.output_dir}")
            else:
                if not args.anchor or not args.vocal:
                    raise ValueError('Supply --plan, --ableton-curated, or both --anchor and --vocal')
                from .vibe import prepare_session
                state = prepare_session(args.root, args.output_dir, args.anchor, args.vocal, args.bpm)
                print(f"Prepared {len(state['anchors'])} anchors and {len(state['vocals'])} vocals: {args.output_dir}")
            print('Unranked audition candidates. Musical fit and tempo interpretation require listening.')
        elif args.command == 'rebind-root':
            from .vibe_collection import rebind_root
            result = rebind_root(args.session_dir, args.root)
            print(f"Library root: {result['root']}\n{result['message']}")
        elif args.command == 'packet':
            from .vibe_shortlist import create_shortlist_packet
            count = create_shortlist_packet(args.session_dir, args.output_dir, args.library_db)
            print(f'Prepared {count} kept original samples: {args.output_dir}')
            print('Review labels.tsv: favourites need an explicit true_role and descriptor before promotion. No audio exported.')
        elif args.command == 'playlist':
            from .vibe_shortlist import shortlist_playlist
            print(shortlist_playlist(args.session_dir), end='')
        else:
            from .vibe_server import serve_vibe
            if not 0 <= args.port <= 65535:
                raise ValueError('Port must be between 0 and 65535')
            serve_vibe(args.session_dir, port=args.port, open_browser=args.open)
        return 0
    except ImportError as exc:
        print(f'error: install library-tools[review-ui] in the package venv: {exc}', file=sys.stderr)
        return 2
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
