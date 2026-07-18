# Ableton tooling — what was attempted, 2026-07-18

Plain-English record of a session that set out to let Claude drive Ableton Live directly (build
tracks, load plugins, set routing) to support the studio workflow described in
`Production/eidetic-session-guide-method-a-v1_1.md`. Part of it worked and is now committed. Part
of it didn't, and was cleaned up rather than left half-installed. This file explains both halves.

## What was being attempted

Two separate, unrelated pieces of work:

1. **Live control** — get Claude talking to a running Ableton Live session, so it could build the
   "Eidetic Techno 140" template: the 5-track routing setup and the Return A "RUMBLE" FabFilter
   chain described in the session guide. This needed a third-party Ableton "Remote Script" (a
   plugin Live loads) plus an MCP server bridging that script to Claude.
2. **Read-only `.als` indexing** — a small Python package to inventory Ableton Live Set files
   (tempo, tracks, devices, sample references) without ever touching them. This was already fully
   designed in an earlier session (`docs/superpowers/specs/2026-06-26-ableton-als-introspection-design.md`)
   but never built.

## What worked — committed to `main`

**`ableton-tools/`** (Python package `abletontools`) — built exactly to the existing approved plan,
test-driven, all 10 tests passing. Two commands:

- `als-index` — walks a directory tree of `.als` files, writes a TSV summary (tempo, tracks, scene
  count, devices, mtime) for each one.
- `als-samples` — resolves every sample reference in every Set, reports which audio files are
  present vs. missing on disk.

It's read-only by design — it never writes or edits a `.als` file, only reads them.

Smoke-tested against the real project at `Production/OT_0.1 Project/OT_0.1.als`: correctly reported
tempo 120, 4 named tracks, and the `Reverb`/`Delay` devices on its two return tracks. That smoke
test also caught a real bug in the original plan's device-listing logic (it would have double-counted
every device on a return track) — fixed, with a regression test added.

Install: `/opt/homebrew/bin/python3.12 -m venv ~/.venvs/ableton-tools && ~/.venvs/ableton-tools/bin/pip install -e "ableton-tools[dev]"`.

## What didn't work — attempted, then cleaned up

The Live-control half never got working, and nothing from it is left installed.

**What was tried:** two different community tools were cloned into `external/` (gitignored, not
committed — see below):

- [`ahujasid/ableton-mcp`](https://github.com/ahujasid/ableton-mcp) — for creating tracks/clips and
  loading instruments and effects (including third-party plugins) from Live's browser by name.
- [`ideoforms/AbletonOSC`](https://github.com/ideoforms/AbletonOSC) plus
  [`Simon-Kansara/ableton-live-mcp-server`](https://github.com/Simon-Kansara/ableton-live-mcp-server)
  — for track routing, input/output, monitor state, arm, and device parameters, which the first tool
  doesn't cover.

Both needed installing as a "Remote Script" inside Ableton Live (Preferences → Link/Tempo/MIDI →
Control Surface), then a separate MCP server process bridging that script to Claude Code.

**Where it got stuck:** after installing both scripts correctly (verified: right folder, right
Ableton Live version path, correct `create_instance()` entry point present, no macOS quarantine
flag, full quit-and-relaunch of Live, tried both as symlinks and as real copied files) — **neither
script ever appeared in Live 12.4's Control Surface dropdown.** Live gives no visible error when
this happens; a script it can't load for any reason is just silently absent from the list.

**Best guess why:** both are unofficial, community-maintained scripts reverse-engineering Ableton's
undocumented Remote Script API. The most likely explanation is that something in Live 12.4
specifically doesn't match what these scripts expect, and Live is failing to import them silently.
This wasn't confirmed — it would need checking each project's GitHub issues for Live 12
compatibility reports, or digging into Live's debug-level logging (not attempted, to avoid
poking further at a working Live install without a clear next step).

**Cleanup done, so nothing is left half-configured:**
- Removed both scripts from `~/Library/Preferences/Ableton/Live 12.4/User Remote Scripts/` — that
  folder is back to exactly how it was before (just Ableton's own default files).
- Removed both MCP server registrations from Claude Code (`claude mcp remove ableton-mcp`,
  `claude mcp remove ableton-osc`) — they "connected" in the sense that the server processes ran,
  but could never actually reach Live, so leaving them registered would have looked configured
  while being silently useless.
- The three cloned repos remain at `eidetic-music-tools/external/` on disk, `.gitignore`d (not
  committed) — kept as a starting point if this is picked up again, not as active tooling.

## If this gets picked up again

Options, roughly cheapest-to-try first:

1. Check the GitHub issues on `ahujasid/ableton-mcp` and `ideoforms/AbletonOSC` for Live 12
   compatibility reports — someone else may have already hit and fixed this.
2. Try `uisato/ableton-mcp-extended`, a more recently active fork of `ableton-mcp`.
3. Try Max for Live instead of a Remote Script — Ableton Live 12 Suite is licensed here and Max
   9.1.4 is confirmed working, so a small M4L device bridging OSC would be first-party-supported
   rather than fighting an undocumented API.
4. Fall back to manual: use `als-index`/`als-samples` (now working) to verify state, and build the
   template track routing / Return A chain by hand in Live following
   `Production/eidetic-session-guide-method-a-v1_1.md` directly.

## Where things live

- `ableton-tools/` — the working, committed package.
- `external/` — the three vendored (gitignored) clones from the Live-control attempt.
- `docs/superpowers/specs/2026-06-26-ableton-als-introspection-design.md` and the paired plan in
  `docs/superpowers/plans/` — the original design this session implemented.
