# Agent guidance

Follow [AGENTS.md](AGENTS.md) for the read order, repository boundaries, safety
rules and Git workflow. It is the shared entry point for all coding assistants.

Use the existing environment and test the current checkout:

```bash
python3 scripts/dev_check.py doctor
python3 scripts/dev_check.py test
```

For focused tests, installed-wheel checks and the synthetic scale benchmark, see
[Development](docs/DEVELOPMENT.md). macOS and Linux CI cover the core packages;
local-model checks use a separate environment and workflow.

- [Project status](STATUS.md): completed work, outstanding user choices and the next increment.
- [Architecture](docs/TECHNOLOGY.md): package boundaries, identity, models and export.
- [Workflows](docs/WORKFLOWS.md): supported commands from search through export.
- [Documentation index](docs/README.md): current guides and dated evidence.

Keep operational facts in the status and trial records rather than duplicating
them here. Historical plans are not proof of current code or approval for new work.
