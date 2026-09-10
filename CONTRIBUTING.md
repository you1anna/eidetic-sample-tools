# Contributing

Help make large sample libraries easier to use in real musical sessions.
Listening feedback, hardware checks, bug reports and clearer documentation are
useful alongside code changes.

## Report a problem or suggest an improvement

Search the [existing issues](https://github.com/you1anna/eidetic-sample-tools/issues)
first. A useful report describes what you were trying to do, what you expected,
what happened, and the smallest steps that reproduce it. For command failures,
include the command, error, operating system and code revision or package version.

This repository is public. Use made-up paths and small synthetic fixtures where
possible; remove private names and paths from logs. Do not attach a commercial
sample pack or a private project archive.

## Listening and hardware feedback

For selection feedback, describe the musical brief, working tempo and what made
sounds useful or unsuitable. Include candidate/keep counts and listening time
when available. Distinguish repeat sounds from different variations of one sound.

For a device check, include the instrument model, firmware, export profile and
how files reached it. Report playback, assignment and save/reload separately.
A successful conversion or card copy does not establish those hardware results.
Start with the [small hardware test](docs/WORKFLOWS.md#first-device-smoke-test).

## Work on code or documentation

Read the [architecture overview](docs/TECHNOLOGY.md) to find the responsible
package, then follow the [development guide](docs/DEVELOPMENT.md) for environment
setup and focused checks. Use the [current status](STATUS.md) and
[roadmap](docs/ROADMAP.md) to distinguish implemented behaviour from proposals.
Discuss changes to hardware profiles or safety behaviour in an issue first.

Keep changes bounded and describe the user-visible result and the verification
that actually ran. A bug fix should include a regression check when practical;
hardware claims should include the device observation. Avoid adding private
library state, generated exports or model caches to a change.

Documentation has four levels:

| Reader's question | Home |
|---|---|
| What does this do, and why would I use it? | Root and package READMEs, with a concrete example and a clear starting link. |
| How do I complete this task? | Guides in `docs/`. |
| Which commands, fields and options are available? | Each package's `REFERENCE.md`. |
| How does the system work, and where are its limits? | System and package architecture guides, linked to source. |

Keep README language accessible to musicians. Put implementation details in the
lower-level guides, and label unfinished features and measured examples clearly.
Check local links, examples and diagram rendering after documentation edits.

## Licence status

No software licence has been selected yet. This guide does not introduce or
change licensing terms.
