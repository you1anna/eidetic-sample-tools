# Audition interface rework

The browser audition screen is the repository's front image: `docs/images/audition.png`
is embedded in the root README and is the first thing a musician sees. Robin's
assessment on 10 September 2026 was that it looks generated and weak rather than
professional. This document records the agreed rework of both browser pages.

The complaint has five identifiable causes in the current code. The audition page is
built as a marketing landing page — a centred single column, a `clamp(30px, 5vw, 42px)`
headline with a full stop, a subtitle sentence and a rounded card — which spends about
190 pixels of viewport before the first control on a screen used repeatedly. One accent
colour, `#c8e995`, serves as primary fill, status text, active filter, checkbox accent
and focus ring simultaneously, so no visual hierarchy is possible. The native Loop
checkbox and range input are the only unstyled controls on screen, sitting beside
hand-built buttons. The page shows no waveform even though the peaks already exist.
Spacing uses seventeen unrelated pixel values with no scale, and list rows nest duration
inside the name block, so no column aligns and nothing scans. Beneath all five,
`audition.css` and `vibe.css` are two separate design vocabularies for one application:
greens `#c8e995` against `#c1e6a0`, radii 14px against 7px, control heights 44px
against 43px.

Robin chose the scope on 10 September 2026: both pages in this pass, the waveform
supplied by extending the server payload, the standing disclaimers moved into an
information affordance, and a two-pane workstation layout for the audition page.

## Deliverable

Add `library-tools/src/librarytools/resources/tokens.css`, wrapped in `@layer base`
and linked first by both pages. It holds custom properties — surfaces, text, accents,
status colours, a 4/8/12/16/24/32/48 spacing scale, 4/8/12 radii, an 11/12/13/15/19/24
type scale, 40px and 32px control heights and one motion duration — together with
element primitives for buttons, inputs, selects, focus rings, panels, notices, hints,
keyboard chips and screen-reader text, and it carries the `prefers-reduced-motion` guard
that currently sits at the bottom of `vibe.css` so both pages inherit a single copy.
Both page stylesheets remain unlayered so page composition wins without specificity
contests. The packaging glob at `library-tools/pyproject.toml:46`
already covers `resources/*.css`; only the asset allowlist in `vibe_server.py` needs the
new entry. A token file that leaves the duplicates in place changes nothing, so the
existing primitives and colour literals are removed from both page stylesheets as part
of this work.

Govern the accent with one rule: green means the listener's decision or current
selection, and nothing else. The Keep action, the kept badge and the current row use it.
Focus rings move to a cool neutral so a system affordance is not confused with a musical
choice, status lines return to plain ink, and the Loop control becomes a neutral
`aria-pressed` toggle button sharing the vocal lab's existing mute-button primitive.

Rebuild the audition page as a two-pane workstation. A sticky application bar carries
the product name, review progress and an information button. The marketing headline is
replaced: `Choose samples.` and its subtitle give way to an accessible `Sample audition`
heading. The bar's product name and the page heading are the same node: a single `h1`
reading `Eidetic · Sample audition`, with no separate eyebrow above it and no subtitle
sentence beside it, so the page carries one label rather than three near-duplicates. The
existing intro sentence moves into the information panel with the disclaimers. The
decision buttons keep their current `Keep & next` and `Skip & next` wording, because the
"& next" tells the listener that the following candidate loads, and they gain `kbd` chips
rather than shorter labels.

Give the status region a defined home. `#status` is currently a full-width accent line
above the card and is the element that produces the shouted "Kept: Demo_rhythm_A.wav";
`audition.js` writes load state, save confirmations and errors to it. It moves into the
player pane directly above the transport, keeping its id, `role="status"` and
`aria-live="polite"` so the script needs no change. Ordinary confirmations render as
quiet ink and clear themselves; errors keep the shared `.notice.error` treatment, which
stays deliberately unmissable. Quieter applies to routine confirmation, not to failure.

Preserve the remove affordance the pilot guide documents. In the Kept view the row's
state column carries a quiet Remove control in place of the Kept badge; in the All view
that column shows the state badge alone. The capability is not dropped, and `li .remove`
keeps a defined slot in the new row grid. Below it, a
`minmax(280px, 360px) 1fr` grid places the candidate list on the left and the player on
the right, both reachable without scrolling; sessions cap at twelve candidates per role,
so the whole list fits. List rows gain aligned columns — ordinal, name, kind,
right-aligned duration and state — with durations rendered as `0:06.9` rather than the
current "6.86 seconds", and with skipped rows finally distinguishable from unreviewed
ones. Keyboard shortcuts move onto the controls they belong to as `kbd` chips instead of
a twelve-pixel prose footnote. The layout stacks below 900 pixels with the player first.
The two footer disclaimers and the unranked-candidates note move behind the information
button; nothing is deleted.

Draw the waveform on a canvas written fresh in `audition.js`, with a restyled
`<input type="range">` overlaid on it as the scrubber. Keeping the range element
preserves keyboard and assistive-technology behaviour that a `role="slider"` canvas
would have to reimplement. The vocal lab's `drawWaveform` is not reused: it is coupled
to region selection, start and end marks and `suggested_bars`, and duplicating about
forty lines of canvas code is cheaper and safer than refactoring twenty kilobytes of
otherwise untouched JavaScript. Unifying the two scripts remains separate later work.

Supply the peaks by adding `waveform` to the fields copied in `source_state`
(`vibe_session.py:137`), rounded to three decimal places. The values are already
computed during preparation (`vibe.py:78`) and already validated as present when a
session loads (`vibe_session.py:80`); the audition payload is the only place they are
stripped. Rounding takes each source from roughly nine kilobytes to three and discards
no precision a 96-pixel canvas can render.

Move the vocal lab onto the same tokens and primitives. Its structure is sound and is
retained, including the numbered track headings and the separate `--vocal` colour for
the second track. Every element id is preserved, as is the class contract `vibe.js`
depends on: `history-item`, `history-title`, `history-detail`, `history-note`,
`load-recipe`, `vocal-event` and the `notice` variants.

## Constraints and non-goals

The pages are served under `default-src 'self'` with `style-src 'self'` and
`script-src 'self'`, and ship inside a wheel. No web font is added: a self-hosted face
would need a new static route, package data and an installed-wheel check for a purely
cosmetic gain. Typographic quality comes from weight, size, tracking and tabular
numerals in the system stack instead. Inline `style` attributes remain unavailable;
setting individual properties through the CSSOM is unaffected.

Robin's `@you1anna/design-system` is not adopted. It is light-first, blue and grey,
carries generic application semantics, and is distributed as React components with CSS
modules, none of which suits a dark local audio tool with no build step.

The two `<audio controls>` elements on the vocal lab stay native. Replacing them means
reimplementing the start-and-end-at-playhead interactions against JavaScript this pass
does not otherwise touch. This is a deliberate inconsistency, recorded so it is not
mistaken for an oversight.

Five assertions pin current behaviour across two files, and three of them change.
`test_audition_server.py:20` and `scripts/check_installed_packages.py:98` both pin the
headline `Choose samples.`, and both are updated to the new heading rather than keeping
dead marketing copy alive to satisfy a test. `test_audition_server.py:100` asserts exact
dictionary equality on the `/api/sources` payload and is updated for the added
`waveform` field. Two assertions are deliberately preserved: `test_audition_server.py:21`
pins `Keep &amp; next`, whose wording this design retains, and
`test_audition_server.py:22-24` pins `Render audition` as present on the vocal lab and
absent from the audition page, which the restyle must not disturb. Both asset loops gain
`tokens.css`.

No change is made to session preparation, the shortlist format, the packet handoff,
audio serving, the token-protected write path or any safety behaviour. Auditioning and
Keep or Skip continue to leave source audio unchanged. `STATUS.md` records no audition
entry today and none is added.

## Verification and evidence

Run the full suite with `python3 scripts/dev_check.py test`, and the separate
installed-wheel check, which a source run cannot substitute for, to confirm
`tokens.css` ships and is served. Confirm the duplicate-removal goal mechanically:
`grep -nE '#[0-9a-fA-F]{3,6}' audition.css vibe.css` must return nothing.

Build a throwaway session outside the repository using the application's normal
builder, with percussive synthetic hits rather than sine tones so the waveform strip is
actually exercised, and inspect the running page in Chrome at 960 and 620 pixels.
Check contrast for the token pairs rather than assuming it; the current disabled state
at 45 percent opacity is not expected to pass and is re-specified.

Recapture `docs/images/audition.png` to the recipe recorded in `docs/images/README.md`:
the running application at a 960-pixel viewport, four synthetic demonstration files
prepared through the normal session builder, one Keep choice visible, and no private
library data. Capture with Chrome headless against the running local
server, using `--window-size=960,<height>` and `--hide-scrollbars` so the capture matches
a 960-pixel viewport rather than Chrome's default window, and allow the page to settle
before the shot so the waveform and list have rendered. Update the
README caption if the controls it names have changed.

Update `docs/GROOVE-AUDITION-PILOT.md`, whose "Listen and choose" steps describe using
Play/Pause, seek and Loop and will no longer match the transport. The documentation
standard confirmed on 10 September 2026 requires the guides to move with the product.

Visual quality is judged by Robin, not by the test suite. No automated check in this
work establishes that the interface looks professional.
