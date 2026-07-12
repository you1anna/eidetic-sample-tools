# Foundation v1 decision corpus

Foundation v1 is the first closed-loop evidence run for Eidetic Sample Tools.
It turns a reviewed sample library into a small, performance-tested collection
while preserving the decisions that made it useful.

## Purpose

The product's distinctive asset is not an automatic role label. It is a
traceable chain from an original sample, through a human listening decision, to
a device crate and its outcome in real musical work.

```text
SHA-256 sample identity
  -> human audition label
  -> curated copy and consumer view
  -> device-specific export
  -> session outcome
```

Each link remains inspectable. A later recommendation system may use these
records to rank candidates, but it must never treat them as permission to move,
promote, remove or export audio without the existing human gates.

## Scope and boundary

This run begins with the existing 216-row packet at
`library-tools/manifests/foundation-v1-review/`. The packet is a working
artifact and must not be reformatted, regenerated or edited by automation while
the reviewer is completing it.

The corpus is private by default:

- retain hashes, paths relative to `SAMPLES/`, labels and outcome metadata;
- keep source audio in the backed-up sample library and never in the repository;
- do not publish, share or train a public model on vendor sample audio or
  derived audio features without a separate rights review; and
- do not make claims that a supplier's pack licence grants redistribution,
  training or dataset rights.

This preserves the value of the workflow without assuming rights that the
project does not have.

## Evidence model

The existing label sheet is the source of truth for the audition decision. Its
required fields are already enforced by `sample-curate validate`:

| Field | Meaning |
|---|---|
| `sample_id` | Stable SHA-256 identity of the reviewed content. |
| `current_path` | Source path relative to the sample root at review time. |
| `decision` | `reject`, `keep` or `favourite`. |
| `true_role` | Human-confirmed role; required for a favourite. |
| `descriptor` | Brief human description; required for a favourite. |
| `tags` and `notes` | Optional context, uncertainty and listening rationale. |

After a successful export, add an outcome sheet beside the generated consumer
views, for example `library-tools/manifests/foundation-v1/outcomes.tsv`. Use
this header exactly:

```tsv
sample_id\trun_id\tdevice\tcrate\tsession_id\toutcome\tcontext\tnotes\trecorded_at
```

Allowed `outcome` values are `untested`, `retained`, `replaced`, `retired` and
`revisit`. `session_id` is a local, human-readable identifier such as
`2026-07-12-hardgroove-jam-01`; it does not need to identify a released work.
One row records one sample's outcome in one session. Leave a sample unrecorded
rather than inventing an outcome.

## Operating sequence

1. Finish the existing listening sheet. For every row, record a decision. For
   every favourite, also record a valid `true_role` and concise `descriptor`.
2. Freeze a copy of the completed label sheet with the packet metadata. Do not
   regenerate the review packet between validation and promotion.
3. Validate the completed labels, then promote only favourites. Promotion
   verifies that each source's hash still matches the reviewed identity.
4. Write consumer views and resolve the Octatrack crate. Preview the export
   with `--list` and `--dry-run` before writing converted copies.
5. Use the crate in at least one real hardware session. Record only observed
   outcomes in `outcomes.tsv`.
6. Review the retained/replaced/revisit records before selecting a Foundation
   v2 queue or building a recommendation layer.

The first milestone is not a larger catalogue or a model. It is a small,
hash-traceable, ear-approved Octatrack crate that survives a real session.

## What this can support later

Once there are several completed runs, the evidence can support private,
suggestion-only capabilities:

- rank new candidates by similarity to retained favourites;
- surface useful role and descriptor combinations for a particular device;
- identify samples repeatedly retired or replaced; and
- compare performance usefulness with filename, acoustic and source-pack
  evidence.

It cannot establish universal musical truth, confer rights over source audio or
replace human listening. A personalised ranking system should be evaluated
against held-out, later human decisions before it influences review order.

## Advancement gates

| Gate | Evidence required | Result |
|---|---|---|
| Curation complete | Valid labels, frozen packet metadata and hash-verified promotion | A trusted `CURATED/` collection. |
| Device complete | Reviewed Octatrack crate and successful export preflight | A hardware-ready copy. |
| Session complete | Outcome rows from a real session | First closed-loop product evidence. |
| Learning-ready | Multiple completed runs with consistent outcome records | Evaluate a private, suggestion-only ranker. |

