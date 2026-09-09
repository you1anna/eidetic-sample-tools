# Set-generation trial

**9 September 2026 — 19 approved favourites exported and software-verified;
card transfer and hardware listening pending.**

Test whether a musical brief can become a useful Octatrack collection with less
selection effort. The initial brief is hypnotic, groovy tribal techno with rap
vocals, using 140 BPM as the trial's working tempo. Machine speed and musical
usefulness are separate outcomes.

## What the earlier successful run establishes

The September 7 collection contained 240 Octatrack files. Retained transfer
evidence records copy/readback verification, and September 8 feedback records
successful use and improved browsing. Those records describe assistant-guided
selection using the brief, source context, metadata and fresh audio checks.
They do not establish that local CLAP inference selected that collection.

The source choices, technical screening results and export commands survive;
the complete selection algorithm and stage timings do not. Replaying those
exports is different from generating an equally useful new collection.

The older 63-file local-classifier packet is a separate experiment. Its successful
classification benchmark must not stand in for the September hardware result.

## Measured costs on the current Mac

The initial inventory contained 23,927 audio locations: 15,393 in `CATALOGUE`,
8,075 in `PACKS` and 459 in `CURATED`. Content hashing resolved 21,689 distinct
identities. The later promotion added 19 curated copies without adding distinct
identities. Exports and quarantine are excluded from the source inventory.

| Stage | Observed wall time |
|---|---:|
| Walk the library and inspect audio headers | 13.05 s |
| Complete content-hash inventory on the SSD | 98.25 s |
| Recover origins and generate tags, without acoustic feature extraction | 26.98 s |
| Both local models: 256 new, unique samples | 47.03 s |
| Repeat those 256 using cached embeddings | 0.404 s |
| Separate checkpoint loading and prompt encoding baseline | 10.14 s |
| Both models: the actual 192-candidate trial pool | 36.36 s |
| Prepare the 24 browser audition copies | 2.04 s |

Model checkpoints were already installed. Both pinned CLAP models ran offline,
sequentially, on CPU with two threads and two files per batch. Peak individual
worker memory was about 1.5 GiB for the 256-file test. That sample was
proportional across catalogue/pack locations and duration groups, including a
source longer than 120 seconds processed through bounded excerpts. All 512
embeddings hit the cache on repeat, with identical model votes and no inference.

Subtracting the measured loading baseline gives roughly 0.144 seconds per new
file for both models under that sample mix. Scaling to 22,000 files suggests
**about 53 minutes of model processing**. This is a conditional estimate, not a
measured full-library run. It excludes inventory, other acoustic analysis,
selection orchestration, listening and export. Cache state, clip mix, duplicate
content, CPU contention and sustained performance can change it.

The current default timeout is 300 seconds per entire model worker. A complete
library pass would need a resumable execution strategy and suitable timeouts;
the existing command is not a ready-made background library analyser.

The 0.404-second repeat measures embedding-based scoring, not complete packet
classification. Classification still reads sources and measures rhythm. A
40-file rhythm check took 3.15 seconds in a fresh process with warmed disk/JIT
caches; in-process repetition was faster. Full-library acoustic feature fill
has not been measured in this trial.

Eight files failed the initial SoundFile header read. FFprobe could inspect one;
seven also failed FFprobe. These files were excluded from this candidate trial
and retained unchanged for separate investigation.

## First listening comparison

1. Evaluate the complete header survey and indexed identities. Exclude curated
   duplicates and unsuitable lengths for the current browser, which accepts
   sources up to 120 seconds. Record exclusions instead of claiming complete
   audio understanding.
2. Select 192 plausible candidates using explicit source/name context, duration
   and source diversity: 96 grooves and 96 vocal candidates. Include previously
   useful originals where relevant; a fresh search does not require excluding them.
3. Score the same pool with both local models against brief-specific audio
   prompts. Preserve scores, checkpoint revisions, prompts and timings. Relative
   prompt scores are not calibrated musical-quality probabilities.
4. Compare six contextual picks with six model-ranked picks for each sound type.
   Show shared picks once if present. This run yielded 24 distinct candidates.
   Shuffle within the groove/vocal groups and hide the method during listening;
   original filenames remain visible.
5. Record Keep/Skip decisions in the existing browser audition tool, plus user
   feedback on groove, vocal character, tempo suitability and listening effort.

This is a temporary diagnostic selection workflow using existing model APIs,
not a new packaged brief-to-set command. AI ranked the narrowed pool, not every
file in the library. The test can measure its added value within that pool;
it cannot establish how many useful sounds the initial contextual filter missed.

The real trial embeddings have been retained in the portable library cache for
reuse. The user reviewed all 24 candidates and kept 19:

| Selection method | Grooves kept | Vocals kept | Total kept |
|---|---:|---:|---:|
| Contextual recommendation | 6/6 | 5/6 | 11/12 |
| Local-model ranking | 5/6 | 3/6 | 8/12 |

The user's reasons were groovy, tribal and funky character for the kept sounds;
wrong tempo or poorer fit for the rejects. The methods selected different files,
so local models contributed eight additional kept candidates. This small trial
supports testing them together with contextual selection; it does not establish
a general winner or prove that the contextual shortlist covered the library well.
Listening time was not supplied, so useful sounds per minute remains unmeasured.

Tempo compatibility needs an explicit constraint: the high model ranking of a
slower drum loop did not make it useful for this brief. Another handoff required
attention: preparation suggested the one-shot `PERC` role for seven kept loops
and no role for another. The user approved the corrected collection explicitly:
11 rhythm loops, two vocal loops and six vocal phrases/chops. All 19 were promoted
and their original and curated hashes passed the promotion check.

The Octatrack export contains 19 WAVs totalling 29.0 MB: 16-bit PCM at 44.1 kHz,
with source channel counts preserved. Every file passed full decoding, source
and output receipt hashes, duration and format checks. A fresh exporter preview
verified reuse of all 19 without reconversion. No current card was mounted for
transfer; hardware playback, assignment and save/reload are still unverified.

## Repetition and variety

Comparing original content hashes with the September 7 Octatrack collection
found six repeats among the 24 auditioned sounds and five among the 19 approved
sounds. All five approved repeats are vocals: three contextual picks and two
model-ranked picks. The other 14 were absent from that earlier collection.

Repetition was permitted by the trial policy; previous export was neither an
exclusion nor a visible browser label. The three repeated contextual choices
ranked 24th, 54th and 72nd among the 96 vocal candidates on local-model score.
The two repeated model choices ranked third and fourth. Repetition therefore
cannot be explained simply by taking the highest AI scores.

Exact novelty also falls short of musical variety: 11 of the 19 approved sounds
come from three related Riemann packs. Future selection needs separate controls
for previous exports, source families and similar variants. The current browser
and automatic packet preparation do not expose those controls.

## Direction for larger collections

The [design and performance assessment](COLLECTION-PLANNING-ASSESSMENT.md) identifies
the safeguards, measured planning costs and acceptance checks needed before scaling.

Use a collection plan that shows the brief, tempo policy, role balance, target
devices, new-versus-previously-exported counts and estimated converted size
before listening. A sound should carry a short selection reason and its known
export history. The next collection should make its novelty policy explicit;
user preferences on repetition and browsing versus performance are pending.

Capacity has different meanings across devices:

| Device | Browsing storage | Active-use or import constraint |
|---|---|---|
| Octatrack MKII | Audio pool on the mounted CompactFlash card | A project has 128 Flex and 128 Static sample slots; a larger audio pool remains browsable. |
| Digitakt MKI | 1 GB +Drive, shared by projects | Each project uses at most 127 sample slots and 64 MB of sample memory. |
| TR-8S | SD card supplies import files | Internal user-sample storage allows up to 400 files and about 600 seconds at 44.1 kHz mono; existing imports consume this allowance. Import folders hold at most 256 files each. |

These are separate budgets, not ratios of removable-disk space. Sources:
[Octatrack quick guide](https://www.elektron.se/wp-content/uploads/2024/09/Ocatrack-MKII-Quick-Guide_ENG.pdf),
[Digitakt manual](https://www.elektron.se/wp-content/uploads/2024/09/Digitakt_User_Manual_ENG_OS1.51_231108.pdf),
[TR-8S reference](https://static.roland.com/assets/media/pdf/TR-8S_Reference_eng03_W.pdf)
and [specifications](https://www.roland.com/us/products/tr-8s/).

The existing exporter checks individual crates. It does not measure free card
space or aggregate internal-device usage; its Digitakt project cap also applies
to browsing crates. A larger-library planner must expose those distinctions and
keep current export checks intact. Device budgets remain unknown until mounted
media or device usage is inspected. No profile limits were changed in this trial.

## Remaining end-to-end checkpoints

- Refine the brief or selection policy from the listening feedback; capture
  active listening time in the next round.
- Agree the final collection size and balance before expanding the shortlist.
- Transfer to the current Octatrack media and verify playback, assignment,
  save/reload and usefulness in a real pattern with the user.

The main product gap is a reproducible brief-to-collection selection process.
Other friction includes separate classification and favourite decisions,
repeated command/file handoffs, and limited explicitly identified rap material.
The trial should determine where local audio models reduce that work before
making them the required selection route.
