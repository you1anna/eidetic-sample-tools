"""CLI for showing and validating portable studio profiles."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .profiles import ProfileError, resolve_profile, validate_source_kb


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sample-profile")
    parser.add_argument("command", choices=("show", "validate"))
    parser.add_argument("--profile")
    parser.add_argument("--source-kb", type=Path)
    args = parser.parse_args(argv)
    try:
        profile = resolve_profile(args.profile)
        print(f"{profile.id}: {profile.display_name}")
        print(f"session: {profile.session_rate} Hz; clock: {profile.clock_master}")
        for device in profile.devices:
            state = "probationary" if device.probationary else "active"
            print(f"  {device.id}: {device.role}; {device.sample_rate} Hz; {state}")
        if args.command == "validate" and args.source_kb:
            warnings = validate_source_kb(profile, args.source_kb)
            if warnings:
                for warning in warnings:
                    print(f"warning: {warning}", file=sys.stderr)
                return 1
            print("Studio KB header matches profile provenance")
        return 0
    except ProfileError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
