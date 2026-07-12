# Roadmap

## Product direction

Eidetic Sample Tools is a personal system first. Its job is to make one real
sample workflow safer, faster and easier to trust.

The longer-term opportunity is a focused product for hardware-based electronic
musicians: bring order to a large sample library, make deliberate selections by
ear, and prepare those selections correctly for each instrument. Work should
move in that direction only when it also improves the current studio.

## Maturity levels

| Level | Meaning in this repository |
|---|---|
| **Stable** | Used in the current personal workflow and covered by tests. |
| **Beta** | Implemented and usable, but still being calibrated or refined. |
| **Experimental** | Research capability whose output needs extra scrutiny. |
| **Planned** | Specified or proposed, but not implemented. |
| **Retired** | Kept for historical context and no longer recommended. |

These labels describe engineering maturity. They are not promises of public
support or release dates.

## Current foundation

The repository already contains the hard part of a credible product idea:

- manifest-first review and organisation;
- dry-run defaults for file moves;
- content-hash identity that survives path changes;
- human-gated promotion into a small working collection;
- device profiles and validated export rules; and
- visible evidence when an automated approach is unreliable.

This is more than a collection of conversion scripts. It is a trust model for
moving from an untidy archive to a performance-ready collection.

## Near-term personal priorities

1. Apply and verify the planned catalogue foundation on the backed-up SSD.
2. Complete the foundation-v1 ear review.
3. Produce trusted Octatrack, Digitakt and TR-8S exports.
4. Simplify installation without weakening the current workflow.
5. Test the process against a second library before generalising it.

The current IP focus is the [Foundation v1 decision corpus](FOUNDATION-V1-DECISION-CORPUS.md):
preserve the path from content identity through listening, device preparation
and real-session outcome. This is private workflow evidence, not a claim of
rights to redistribute source packs or train a public model on them.

The dated [project status](../STATUS.md) remains the authority for immediate
operational actions.

## Research tracks

Research remains part of the product, provided its limits are explicit:

- Acoustic feature analysis and inspectable sound tags.
- Ear-labelled benchmarks for drum-role models.
- Conservative near-duplicate detection.
- Planned MIDI generation, Ableton inspection, bounce analysis and stem
  separation.

See the [decision records](../decisions/), [design specifications](superpowers/specs/)
and [implementation plans](superpowers/plans/) for the evidence, including work
that was rejected or downgraded.

## What would make this a product

The current code has product value, but it is not yet a product someone else can
adopt confidently. The main gaps are:

- one portable installation and upgrade path;
- unified configuration rather than knowledge of repository internals;
- clear compatibility and preflight reporting;
- a guided workflow that joins review, curation and export;
- recovery tools that are easy to understand under pressure; and
- evidence from musicians and libraries beyond the current studio.

A graphical interface may eventually help, but it should follow a proven
workflow rather than define one prematurely.

## Deliberately undecided

The repository does not yet choose a licence, price, distribution model or
release schedule. It also does not assume that the final product must be a
desktop application.

Those decisions should follow evidence: repeated personal use, a reliable
portable setup, and successful trials outside the Eidetic studio.
