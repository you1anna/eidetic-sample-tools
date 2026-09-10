# 2026-09-10 — Audition interface reworked onto a shared token layer

Project: eidetic-sample-tools

## Decision

The browser audition screen (`sample-vibe serve`) is rebuilt as a two-pane
workstation, and both browser pages now draw from a single shared stylesheet,
`library-tools/src/librarytools/resources/tokens.css`, loaded in `@layer base`
before each page's own file.

Robin's assessment was that the screen "looks AI generated and weak". It is the
image embedded in the root README, so it is the repository's first impression.
Five causes were identified in the code: a marketing-page skeleton (hero headline,
subtitle, centred column) on a screen used repeatedly; one accent colour serving as
button fill, status text, active filter, checkbox accent and focus ring at once;
native controls beside hand-built ones; no waveform despite peaks already being
computed; and no spacing scale, with list rows nesting duration inside the filename
so nothing aligned. Underneath, `audition.css` and `vibe.css` were two separate
design vocabularies for one application.

Green now means one thing: a listening decision or the current selection. Focus
rings use a cool neutral, status text plain ink, and Loop is an `aria-pressed`
toggle rather than a native checkbox. The waveform comes from peaks that
preparation already computed and `source_state` was stripping; adding the field
back costs no new computation and about 2.8 KB per source.

## Rationale

Scope was Robin's call on 10 September: both pages, waveform from the server
payload, disclaimers behind an information affordance, two-pane layout. Doing one
page would have left the sibling page carrying the same defects and a second
palette. A token file that did not also delete the duplicated primitives would
have changed nothing, so the acceptance test was mechanical: no colour literal
remains in either page stylesheet.

Full design record: [the design spec](../docs/superpowers/specs/2026-09-10-audition-ui-rework-design.md).

## Consequences

- Page stylesheets hold composition only. New colours or measurements belong in
  `tokens.css`; a literal in a page file is a regression.
- Three contrast failures found during verification were corrected in the tokens:
  small metadata text (4.20 and 3.87 against a 4.5 requirement) and control borders
  and the waveform (1.81 against 3.0). They now measure 4.95, 4.56 and 3.23.
- `docs/images/audition.png` is recaptured from a synthetic percussive session at a
  960-pixel viewport; `docs/images/README.md` now records the Chrome headless flags
  so the recipe is repeatable.
- **Deliberate exception:** the vocal lab keeps its two native `<audio controls>`
  elements. They are wired to the start-and-end-at-playhead controls, and replacing
  them means rewriting behaviour this pass did not otherwise touch.
- **Verified only by reading:** the vocal lab's amber rendering notice. Its rule and
  `--vocal-*` tokens are intact and were untouched by the contrast fix, but no live
  render was driven to observe it.
- **Open items awaiting Robin:** whether `STATUS.md` gains a line naming the shared
  token layer; whether the native audio players are replaced in a later pass; and
  whether the decision buttons keep the "& next" wording.
