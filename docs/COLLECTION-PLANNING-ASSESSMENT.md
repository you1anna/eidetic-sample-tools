# Larger collection planning: design assessment

**9 September 2026 — assessment recorded before implementation.**

**10 September:** the [first collection-planner increment](COLLECTION-PLANNER.md)
adds immutable metadata plans, explicit history/freshness and retained pins.
The larger listening, audio-retrieval and export changes assessed below remain
separate increments.

The approach is viable at the current 21,689 unique samples. Proceed with a
collection planner, but separate preparation, interactive selection, listening
decisions and device execution. Increasing the existing 24-sound audition limit
or repeatedly calling packet classification would carry avoidable problems into
the larger workflow.

The user's support is approval of the direction in principle. Freshness defaults,
collection sizes and browsing-versus-performance scope remain undecided. This
assessment does not approve additional sounds or change device profiles.

## Measured performance

Read-only checks used the current SSD index and checkout. Times below are medians
of three runs in one process; they are not cold-start or sustained-load guarantees.

| Operation | Measured time | Scope |
|---|---:|---|
| Load indexed identities, tags and selection metadata | 0.272 s | All 21,689 identities |
| Query `tribal` AND `perc` | 0.024 s | 1,629 matches; current metadata rules |
| Apply existing family round-robin | 0.077 s | All identities; 4,709 inferred families |
| Exclude 240 previous Octatrack identities | 0.00087 s | In-memory set lookup after loading history |

Basic planning is inexpensive at this size. There is no current need for a
separate vector database or distributed service.

An additional synthetic arithmetic check scored two sets of 512-dimensional
vectors against six prompts in 0.0023 s, with vectors already in memory. This
does **not** measure real model loading, cache retrieval, inference or diversity
selection. Two models' raw audio vectors occupy about 42.4 MiB as float16 or
84.7 MiB as float32 at this library size.

The earlier real-model test took 47.03 s for 256 new samples and 0.404 s on cached
repeat. Its roughly 53-minute whole-library inference estimate remains conditional.
See the [trial report](SET-GENERATION-TRIAL.md) for measurement limits. An interactive
Replace action must reuse prepared data; it must not trigger another library scan
or audio-analysis pass.

## Issues to resolve before larger exports

### 1. Regeneration can lose decisions or destabilise hardware paths

The current session is an immutable small list. Saved decisions reject unknown
IDs, while updates have no expected-revision check for stale browser tabs. Feeding
fresh recommendations through the existing *heard shortlist* handoff would label
them `keep`. A pin must mean retain a candidate, not approve it.

Export filenames also contain a sample's position within its role. Removing one
row can rename later retained files. Copying the new selection leaves old files
in place and may replace files at matching destination paths. This can create
duplicates and make saved device references difficult to reason about.

**Required design:** freeze each plan revision, its policy and source IDs. Preserve
listening events independently, reject stale updates and retain pinned or kept
choices during regeneration. Bind favourite approval to the reviewed selection
and any processing recipe. Freeze published output paths; revisions must either
preserve those paths or publish to explicitly distinct collection folders. Preview
additions and replacements across all batches. Pruning old exports stays separate.

Evidence: [shortlist state](../library-tools/src/librarytools/vibe_shortlist.py),
[curation handoff](../library-tools/src/librarytools/curate.py),
[export naming and copying](../sample-tools/src/sampletools/export.py).

### 2. History can imply more certainty than it provides

A staged export is not proof of transfer, and a past transfer is not proof a sound
is still present on the device. Card mount names can be reused; SD contents cannot
establish TR-8S internal imports. Missing Mac mini history must remain visible.
Deleting rebuildable exports must not erase the history used to judge freshness.

Whole-file hashes correctly prove exact identity, but converted, retagged or
trimmed files can have new hashes despite containing familiar audio. Excluding an
entire vocal source can also hide a useful new phrase from it.

**Required design:** distinguish known exported, transferred and currently observed
presence. Scope history by library, device, evidence source and time. Store the
plan's history snapshot and provenance outside rebuildable output folders. Track
parent/recipe lineage for toolkit-created derivatives; report unknown lineage
honestly. Retain integrity hashes even when similarity suggests a related sound.
Use library identity and relative paths for cross-Mac plans and reviews.

Evidence: [export receipts](../sample-tools/src/sampletools/receipts.py),
[transfer records](../sample-tools/src/sampletools/export.py),
[portable packet roots](../library-tools/src/librarytools/artifacts.py),
[onboarding history](../library-tools/src/librarytools/onboarding.py).

### 3. More novelty can reduce musical usefulness

Excluding previous Octatrack selections leaves 96 grooves and 61 vocals in the
192-candidate trial pool. Only three of its seven explicitly rap-named candidates
remain. This is a limit of that metadata-filtered pool, not proof the full library
contains only three unused rap samples.

Existing filename-family grouping is too coarse to become a hard diversity rule:
one inferred family contains 1,156 files; another groups 903 files across multiple
roles. A vendor prefix is not a reliable definition of one sound with variants.
Conversely, distinct packs can contain similar material. Globally suppressing a
Skip for wrong tempo would incorrectly suppress it for another musical brief.

**Required design:** apply role and tempo policy before diversity ranking, retaining
unknown tempo as uncertainty. Separate one-shots, tempo-bound loops and phrases
intended for chopping; do not penalise them identically. Use relevance-qualified
candidates, explicit source caps and cautious similarity grouping. Keep a route
for exploration outside familiar name/source matches. Show shortages instead of
silently relaxing strict exclusions, adding weak matches or filling disk space.
Scope rejection reasons to the brief; global suppression needs a separate choice.

AI relevance, diversity and history should remain separate explanations. Softmax
scores depend on the prompt alternatives and are not comparable quality ratings
across briefs. Freeze model, prompt, analysis-coverage and selection-policy versions
with each plan so later analysis cannot silently change it.

The user cost must be measured too. At an illustrative ten seconds per candidate,
reviewing 1,000 sounds takes nearly three hours before any device work. Use short,
resumable queues, preserve previous decisions and provide one clear final approval
for the reviewed collection. More candidates should not mean repeated CLI/file
handoffs or reviewing retained favourites from scratch.

Evidence: [family grouping and search](../library-tools/src/librarytools/find.py),
[model scoring](../library-tools/src/librarytools/classification/models.py),
[observed selection and feedback](SET-GENERATION-TRIAL.md).

### 4. Device budgets require aggregate accounting

Current limits apply to individual crates. Splitting a large selection into valid
crates does not establish that the combined import fits. For example, two TR-8S
crates with 250 files and 400 seconds each pass those individual limits but together
exceed the profile's declared 400-file/600-second totals. The exporter currently
does not load the profile's total-file field. Its duration sum also treats missing
duration as zero and does not distinguish stereo memory consumption.

Free storage, an import-folder limit and active project memory are different
budgets. The planner must show unknown device usage until it is supplied or observed.
Current Digitakt/TR-8S crate rules also reject long-form roles; a larger planner
must respect this scope rather than silently route Octatrack loops everywhere.

**Required design:** validate the entire proposed collection and each batch. Report
count, elapsed duration and converted bytes separately. Resolve mono/stereo memory
rules against hardware evidence before claiming internal capacity. Reject missing
measurements when the relevant capacity check depends on them. Preserve current
profiles and approval gates; any proposal to change those constraints needs its
own review.

Evidence: [profile loading](../sample-tools/src/sampletools/config.py),
[crate checks](../sample-tools/src/sampletools/export.py),
[device capacity distinctions and manuals](SET-GENERATION-TRIAL.md#direction-for-larger-collections).

### 5. Current interactive paths do unnecessary work as the pool grows

Each embedding cache lookup opens a writable database connection and takes the
writer lock; normal model voting reads each vector twice per model. The classifier
review server holds the library writer lock throughout the browser session.
Packet classification still hashes sources and measures rhythm on warm embedding
cache hits. Full inventory refresh hashes every file again.

The audition tool eagerly converts all previews, validates the full session on
requests and rehashes requested source/preview audio. Its browser rebuilds every
row on selection and performs a linear position lookup inside that loop. Raising
the 12-per-category limits would not create a scalable browser.

**Required design:** bulk read-only planning snapshots; versioned analysis caches;
bounded background inference with progress, cancellation, per-file failures and
restart checkpoints. Keep models loaded across inference batches instead of
reloading them for many tiny jobs. Use paged metadata, a small review queue and
lazy previews with bounded read-ahead and cache storage. Retain source verification
at approval/export boundaries and explicit invalidation for cached playback.
Refactor lock scope deliberately rather than removing existing locking safeguards.

Avoid a full pairwise similarity matrix: at 21,689 files one float32 matrix alone
would occupy 1.75 GiB per model. Score the library against brief prompts, then
diversify a bounded relevant pool with incremental similarity updates. Measure
requested large collection sizes as well as top-24 selection.

Evidence: [cache access](../library-tools/src/librarytools/classification/cache.py),
[model workers](../library-tools/src/librarytools/classification/workers.py),
[classifier CLI locking](../library-tools/src/librarytools/curate_cli.py),
[audition preparation](../library-tools/src/librarytools/vibe.py),
[session loading](../library-tools/src/librarytools/vibe_session.py),
[browser rendering](../library-tools/src/librarytools/resources/audition.js).

### 6. Large transfers need realistic space and recovery planning

Conversion and card copying create temporary files alongside existing destinations.
A collection can fit in its final state but run out of space during replacement.
There is no current free-space preflight. Transfers protect individual files, not
the collection as a whole; completed files remain after a later failure. Retries
create new operation IDs and rediscover existing copies through hash checks.

The transfer journal rewrites and fsyncs the entire item list twice per file.
Its written JSON therefore grows roughly quadratically. A synthetic 1,000-item
manifest illustrates about 0.6 GB of journal writes and 2,000 fsync operations;
this is a size calculation, not a measured transfer-time result. The journal lives
on the library drive, not the destination card.

**Required design:** use staged file sizes for final space checks, account for
temporary replacements and a reserve, and recheck before copying. Persist per-file
events or transactional status updates with compact snapshots. Tie resumptions to
the frozen plan and show partial completion. Verify aggregate destination paths
before the first copy; do not infer cleanup permission from a revised selection.

Evidence: [conversion and transfer](../sample-tools/src/sampletools/export.py),
[durable receipt writes](../sample-tools/src/sampletools/receipts.py).

## Recommended implementation order and acceptance checks

1. **Read-only planner:** stable plan revisions, explicit history scope, freshness,
   role/tempo policy, useful diversity and honest shortages. Same snapshot/settings/
   seed must reproduce the same IDs; a new seed must preserve pins and decisions.
   Test renamed duplicates, incomplete history, derivative lineage and stale updates.
2. **Larger review workflow:** paginate a 1,000-result collection while rendering
   at most about 50 rows. Target first-page and warm Replace responses within two
   seconds on this Mac; this is an acceptance target, not an achieved guarantee.
   Verify cancellation, progress restoration and bounded preview storage. Measure
   useful new sounds per active review minute as well as raw keep rate.
3. **Prepared audio retrieval:** bulk cache reads and resumable inference. Benchmark
   1,000 representative uncached files with a mid-run interruption; completed
   embeddings must survive and failed files must not restart good work. Warm
   regeneration must not decode or hash the whole library. Keep review usable while
   analysis runs, without allowing competing unsafe mutations. Report eligible,
   analysed, cached, failed and excluded identity counts. Until the eligible pool
   has prepared embeddings, describe results as partial coverage; never treat
   missing embeddings as low relevance or silently omit unanalysed material. A
   1,000-file performance test does not establish whole-library AI selection.
4. **Larger export execution:** stable paths, aggregate budgets, space preflight and
   resumable transfer evidence. Benchmark 100/1,000/5,000-file plans and warm reuse
   on synthetic libraries; test multi-file interruption and retry. Complete the
   existing 19-file Octatrack hardware round trip before a substantially larger
   transfer, then validate each additional device separately.

These are separable stages, not prerequisites for an all-at-once rewrite. No new
service or vector database is justified by the current measurements.

## Verification performed

- The real index benchmark above was read-only; its database SHA-256 was unchanged.
- Synthetic vector arithmetic and journal-size calculations ran locally without
  source audio inference or card writes. Their timings do not predict full workflow
  latency.
- Focused existing search, shortlist, export-lifecycle and device-profile tests:
  **109 passed in 3.06 seconds** against the checkout.
- Tests for the proposed behaviour, sustained whole-library inference, full-sized
  browser interaction, low-space transfer and physical device use remain future
  acceptance work. Passing the existing suite does not cover the gaps identified
  above.

No implementation, profile, approval default or sample-library content changed
as part of this assessment.
