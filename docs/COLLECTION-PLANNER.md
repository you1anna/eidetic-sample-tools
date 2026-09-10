# Collection planner

Save candidate choices, see known repeats and try a different selection while
retaining pins. Each plan is a new, self-contained directory; its predecessor
remains intact.

**Experimental — first increment.** Selection currently uses explicit metadata
filters and reproducible seeded ordering. The musical brief is recorded context;
it is not interpreted by an audio model. Plans contain unreviewed candidates and
do not replace the listening, favourite approval or device export workflow.

## Create a plan

Install the current `library-tools` package in your existing Python 3.12
environment, following [setup](GETTING-STARTED.md). Use an onboarded library with
a completed inventory scan. Planning reads its existing index without decoding
audio, rescanning or changing indexed metadata. It writes only the requested plan
files; outputs inside `.eidetic/` also use the library's existing writer lock to
coordinate with backups. That destination must belong to the same library.

```bash
export SAMPLES_ROOT=/path/to/SAMPLES
export RUNS="$SAMPLES_ROOT/.eidetic/runs"
sample-collection plan tribal perc --root "$SAMPLES_ROOT" \
  --device octatrack --count 100 --freshness exclude --seed 10 \
  --history "$SAMPLES_ROOT/_EXPORT/previous-run/OCTATRACK" \
  --brief "Hypnotic groovy tribal techno with rap vocals" \
  --output-dir "$RUNS/collection-01"
```

Terms combine with AND; `--any` uses OR. Repeated `--role` and `--origin` filters
narrow the results. Search considers original aliases even when a curated copy
has a different name. Exact copies share one candidate identity.

Choose freshness explicitly for each new plan:

| Mode | Behaviour |
|---|---|
| `exclude` | Omit identities found in the supplied history for that device. |
| `prefer-new` | Put identities absent from that history ahead of known repeats. |
| `allow` | Keep all matching identities eligible and show known repeats. |

`exclude` and `prefer-new` require history. Without history, `allow` reports it
as unknown. If too few candidates qualify, the plan shows a shortage; it never
silently brings excluded sounds back to meet the requested count.

`--history` accepts a single export receipt JSON, a directory of
`*.wav.receipt.json` files, or the retained `eidetic-delegated-library-v1`
selection format. Repeat the flag to combine records. The planner records their
digests and filters by the target device; it never follows audio paths or imports
approval from those records. Foreign library IDs and malformed evidence are errors.

History means **recorded exports**, not proof of present device contents. Missing
history remains unknown. Different encodings or newly cut phrases may have
different file hashes; this increment does not detect related audio by sound.

## Regenerate while retaining a choice

Read `REVIEW.md` for the summary and full sample IDs. To retain a candidate, copy
its ID into `--pin`:

```bash
sample-collection regenerate --from-plan "$RUNS/collection-01" \
  --seed 11 --pin FULL_SAMPLE_ID_FROM_REVIEW \
  --output-dir "$RUNS/collection-02"
sample-collection show "$RUNS/collection-02"
```

Use a new seed to vary unpinned choices, and optional `--count` to change the
requested number. Existing pins persist; additional pins must be selected in the
parent plan. A pin preserves membership, not position or approval. The count must
accommodate all pins. This increment does not offer unpinning; start from an earlier
revision to revise that choice.

Regeneration uses the saved population, filters, brief, device and history. It
works without the source drive or original history files. Changing those inputs
requires a new initial plan. Candidates are not promised to be playable later:
source availability and integrity still need checking in the listening/export
workflow. Existing browser Keep/Skip decisions are not yet connected to plans.

## Saved files and limits

- `plan.json`: versioned metadata snapshot, selection, pins, policy and content
  digest, plus the parent plan ID for regenerated selections.
- `REVIEW.md`: count, known repeats, shortages and the candidate list.

Never edit a saved plan to change choices. Use regeneration; modified or malformed
plans are refused. Output directories must be new and outside the parent plan.
Digests detect accidental changes; they are not signatures or approval evidence.
Plan files include private library metadata and belong outside the public repository.

Each revision currently carries its full matching population for portability.
In a 21,689-identity scale check, a 1,000-candidate plan was about 9.2 MB; creation
and writing took 1.95 seconds, and reading/regenerating/writing took 1.82 seconds.
These are one-run measurements on the current Mac, not latency guarantees or
musical-quality results. Plan JSON has a 128 MiB limit; each history file is limited
to 32 MiB. Preview audio is not generated.

For repeatable performance comparisons without the sample drive, use the
[synthetic planner benchmark](DEVELOPMENT.md#compare-collection-planner-performance).

Device names scope history only at this stage. Capacity, format eligibility,
tempo compatibility and sound-family diversity are not checked by this planner.
Its JSON is not an export crate. The next increments connect plans to listening,
audio retrieval and validated device budgets under the
[assessed design](COLLECTION-PLANNING-ASSESSMENT.md).

`plan` and `regenerate` support `--json` for compact machine-readable summaries;
`show --json` emits the validated full plan.
