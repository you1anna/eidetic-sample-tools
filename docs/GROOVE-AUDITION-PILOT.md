# Sample audition pilot

`sample-vibe` is a local listening chooser: hear a candidate, Keep or Skip it,
then compare the saved shortlist before entering the existing curation and export
workflow. This guide describes the current supported flow.

The current candidates are supplied explicitly and are unranked. Neither a filename
nor these technical checks establishes a match to a requested vibe or reference
track. This increment improves auditioning and the curation handoff; it does not
improve the algorithm that generates suggestions. Automated vibe retrieval and
cohesive set assembly remain future work.

## Prepare a session

Install `library-tools[review-ui]` in the package environment and install FFmpeg;
see [setup](GETTING-STARTED.md). Supply files you want to compare:

```bash
sample-vibe prepare --root "$SAMPLES_ROOT" \
  --anchor "PACKS/example/percussion-loop.wav" \
  --vocal "CATALOGUE/VOCALS/example-phrase.wav" \
  --output-dir /path/to/new-session --bpm 140
sample-vibe serve --session-dir /path/to/new-session --open
```

Repeat `--anchor` or `--vocal` for up to 12 candidates each. Both groups are
currently required. Paths may be absolute or relative to `--root`, must resolve
inside it and must contain at most 120 seconds of self-contained WAV, AIFF, FLAC,
MP3 or Ogg audio. Playlist containers and external media references are refused.
Preparation creates a new session outside the source library without opening its
database. Source audio remains unchanged.

## Listen and choose

1. Start `sample-vibe serve --session-dir PATH --open` with the source drive attached.
2. Click any sample to play it. Use Play/Pause, seek and Loop to inspect it.
3. Choose Keep or Skip. The next unreviewed sample loads; playback continues only if
   it was still playing when the choice finished saving. Undo restores the last choice.
4. Open Kept to compare, remove choices or download a playlist of the original files.

Choices save automatically to the session's `shortlist.json`.
Keeping a sample means keeping the **complete original source**, including a whole
vocal recording. This screen does not cut phrases or claim device readiness.

The UI does not need a library index to audition or save choices. It decodes only
one audio element at a time and does no audio rendering or model inference on a
selection click. This is a bounded usability pilot, not a whole-library
performance result. Source previews are WAV copies at 48 kHz; any attenuation to
avoid clipping is recorded, and source timing is retained.

## What saved choices mean

The chooser does **not** train a model or change future search rankings. It saves
the latest Keep/Skip decision for each original SHA-256 identity in this session.
Reset removes that decision. These files are resumable shortlist state, not a
complete training history: they do not capture the listening brief, why a sample
was skipped or earlier choices. A skip need not mean a sample is generally bad,
and an unreviewed or reset sample is not a negative example.

The existing `sample-find --preferred` separately orders results by recorded kit
pick counts; `sample-vibe` choices do not populate those counts. The existing tag,
acoustic-similarity and optional CLAP grouping methods are unchanged. Vocal-lab
pair judgments also remain separate from both ranking and shortlist choices.

A proposed next evaluation is to record context with listening judgments, reserve
unseen examples for comparison, and test a lightweight preference reranker against
the existing retrieval methods. Reuse cached acoustic features or embeddings where
appropriate before considering a new model. Measure whether the listener keeps
more useful candidates with less auditioning; no preference-based improvement has
yet been implemented or demonstrated. See the [roadmap](ROADMAP.md).

## From shortlist to export

The Kept view's **Prepare curation sheet** button creates a normal packet containing
exactly the kept original SHA-256 identities and paths, with decisions set to `keep`.
A current, correctly bound inventory is required. If unavailable, the UI explains
that setup is pending and still allows a shortlist playlist to be downloaded.
Follow [library setup](GETTING-STARTED.md) and [onboarding](LIFECYCLE.md); do not
invent a partial scan of the full library merely to enable this button.

Packet files are written beneath the session's `curation-packets/` directory.
The CLI can write the playlist and supports an explicit existing database for
packet preparation:

```bash
sample-vibe playlist --session-dir /path/to/session > /path/to/shortlist.m3u8
sample-vibe packet --session-dir /path/to/session \
  --output-dir /path/to/new-packet --library-db /path/to/library.sqlite
```

Then use the [canonical curation workflow](WORKFLOWS.md):

1. Review `labels.tsv`. Only samples you explicitly approve become `favourite`;
   each needs an accurate canonical `true_role` and your `descriptor`.
2. Validate the labels and use `sample-curate promote` to make curated copies.
3. Generate consumer views with a **small collection quota file**, using `--quotas`.
   The default Foundation quotas require a much larger collection. For example,
   if you approved two drum loops and one vocal loop, the TOML file is:

   ```toml
   [quotas]
   DRUM-LOOP = 2
   VOCAL-LOOP = 1
   ```

   Pass that file to `sample-curate views --labels … --quotas … --output-dir … --name …`.
   Adjust the roles/counts to the samples actually approved.
4. Preview the resulting crate with the existing `sample-export` list/dry-run
   commands for the intended device before doing an export.

Existing device constraints still apply. Long-form loops require a compatible
profile; the current Digitakt MKI and TR-8S export policies reject long-form roles.
This UI does not bypass those checks. No audio is promoted or exported by Keep,
playlist download or curation-sheet preparation.

## Optional vocal experiment

The earlier vocal editor is preserved at `/vocal-lab` on the same local server,
separate from the main chooser. It can render a cut against a loop, fit tempo,
place repetitions and save Works/Doesn't work/Unsure recipe judgments. Those
judgments cannot approve an original sample or rendered mix for export.

Its eight-bar 4/4 scene uses FFmpeg `atempo`, bounded to tempo ratios from 0.5 to 2,
with five-millisecond cut-edge fades and shared mix attenuation. A duration-based
bar-count suggestion is not a detected beat grid. Cut boundaries, speech clarity,
time-stretch artifacts and musical fit still need listening. Keep this experiment
optional until it demonstrably saves effort. The earlier
[design](superpowers/specs/2026-09-09-groove-audition-pilot-design.md) and
[implementation plan](superpowers/plans/2026-09-09-groove-audition-pilot.md) retain
its development history; they do not define the current main screen.

## Verification and local interaction

Automated tests cover persisted choice/reset behavior, original hashes, stale or
missing sources, index identity, exact packet contents, unchanged approval gates,
API authorization and failure responses. Live browser checks cover playback,
selection, persistence, undo and the curation handoff with synthetic fixtures.
Technical playback state and passing tests do not establish audible output quality
or that the samples work musically.

The server runs on the Mac at `127.0.0.1`; iPhone remote access and audio forwarding
are not established. Your interaction is needed on the Mac for the final listening
judgment. No local interaction is needed for the agent to launch the server and
exercise controls. Stop with Ctrl-C and rerun the command to resume; no background
service is installed.
