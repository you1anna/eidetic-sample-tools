# README design notes

**Reviewed 10 September 2026.** The README is the entry point for a musician
deciding whether to try the tools. Detailed operational and engineering material
belongs in linked guides so that initial decision does not require learning the
implementation.

## Comparable projects

The comparison used the published READMEs of established audio and CLI projects.
Their popularity is context for choosing examples, not evidence that a README
pattern causes adoption.

| Project | Useful presentation pattern | Applied here |
|---|---|---|
| [beets](https://github.com/beetbox/beets#readme) | Explains the audience and purpose, demonstrates a concrete result, and links capabilities to deeper documentation. | A clear musician-facing promise, task-based benefits and an image of the working audition interface. |
| [librosa](https://github.com/librosa/librosa#readme) | Separates first-time tutorials from API reference and release information; surfaces verifiable project metadata. | Distinct user-guide, command-reference and architecture paths, plus a live CI badge. |
| [spotDL](https://github.com/spotDL/spotify-downloader#readme) | Leads with the outcome and a simple usage path; moves advanced options into linked or expandable material; provides contribution guidance. | A minimal first command, setup links, expandable system diagram and a contributor entry point. |

The previous READMEs concentrated on command inventories, installation variants,
flags and file formats. That made readers learn the tools' structure before seeing
their practical value. The new pages lead with outcomes and let readers choose
their next level of detail.

## Reader paths

1. **Understand:** root README — audience, benefits, visible interface, supported
   devices and current maturity.
2. **Try:** getting-started guide — installation, one safe inspection and a first search.
3. **Use:** workflow and feature guides — complete tasks with explicit write steps.
4. **Look up:** package references — commands, formats, options and compatibility.
5. **Extend:** architecture guides — modules, contracts, data ownership, recovery
   and performance costs, linked to source.

## Evidence and presentation

- The interface image is a capture of the actual application using synthetic
  demonstration files, with an explicit caption. It contains no private library data.
- The CI badge links to the real workflow. Maturity and trial claims link to their
  evidence; planned AI retrieval and capacity budgeting remain labelled as unfinished.
- The architecture diagram remains available from the root README, with the full
  diagram and more detailed system explanations one level below it.
- Contribution guidance includes listening and hardware feedback as well as code,
  because usefulness depends on musical and instrument results.
- The licence is still undecided. No licence, package-release or download-count
  badge has been added without an underlying published fact.

These choices make the repository easier to evaluate. Wider adoption will also
depend on installation reliability, musical results, device testing and maintenance.
