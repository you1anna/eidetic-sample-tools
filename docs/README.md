# Documentation

Start with the guide for the job you want to do. The root and package READMEs
explain what the tools do and why you would use them. Guides explain tasks;
references document commands; architecture guides explain the systems underneath.

| I want to… | Read |
|---|---|
| Install and make a first search | [Getting started](GETTING-STARTED.md) |
| Find, audition, approve and export sounds | [Workflows](WORKFLOWS.md) |
| Save a selection, control repeats and regenerate it | [Collection planner](COLLECTION-PLANNER.md) |
| Set up local AI and understand its costs | [AI setup](AI-SETUP.md) |
| Understand how the tools fit together | [Architecture](TECHNOLOGY.md) |
| Move between Macs, back up state or recover work | [Library lifecycle](LIFECYCLE.md) |
| Check device configuration | [Profiles](SAMPLE-FOUNDATION-WORKFLOW.md) |
| Develop or verify a change | [Development](DEVELOPMENT.md) |
| Report a problem or contribute listening/device feedback | [Contributing](../CONTRIBUTING.md) |
| See what is finished and what comes next | [Project status](../STATUS.md) and [roadmap](ROADMAP.md) |

Command references: [library tools](../library-tools/REFERENCE.md),
[sample export](../sample-tools/REFERENCE.md), [Ableton tools](../ableton-tools/REFERENCE.md).
Read the [safety model](SAFETY.md) before changing library audio.

## Architecture and systems

Start with the [overall architecture and diagram](TECHNOLOGY.md), then follow the
part of the system you need to understand:

| Guide | Detail |
|---|---|
| [State and data contracts](STATE-AND-CONTRACTS.md) | Storage ownership, file formats, identity, cross-machine paths, locks and interrupted work. |
| [Library architecture](../library-tools/ARCHITECTURE.md) | Database and scans, search versus planning, model workers/caches, browser decisions and curation. |
| [Export architecture](../sample-tools/ARCHITECTURE.md) | Crate validation, conversion, receipts, copy journals and large-collection costs. |
| [Ableton architecture](../ableton-tools/ARCHITECTURE.md) | Set traversal, parsing, reference resolution, completeness and report publication. |

These guides map responsibilities to source modules and distinguish current
behaviour from unfinished integrations. The [README design standard](README-DESIGN.md)
sets the baseline for future documentation and records the comparison examples.

## Evidence and history

The [set-generation trial](SET-GENERATION-TRIAL.md) records measured costs, listening
feedback and the approved export. The [collection assessment](COLLECTION-PLANNING-ASSESSMENT.md)
explains the remaining design risks. [Library history](LIBRARY-HISTORY.md) preserves
older operational findings without making them the current work queue.

Dated [reviews](REVIEW-2026-09-09.md), [decisions](../decisions/),
[specifications](superpowers/specs/) and [plans](superpowers/plans/) retain the
evidence and intent from their original sessions. They can describe superseded
behaviour or unfinished proposals. Use the current guides and project status
before following their commands or treating a proposal as implemented.
