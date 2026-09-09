# Profiles and configuration

TOML profiles describe the capabilities used by library analysis and export.
Device definitions live in [`profiles/devices/`](../profiles/devices/); the
bundled `eidetic-studio` profile selects Octatrack MKII, Digitakt MKI and TR-8S.

Inspect the resolved profile:

```bash
sample-profile show --profile eidetic-studio
```

To select it locally:

```toml
# ~/.config/eidetic-sample-tools/config.toml
profile = "eidetic-studio"
```

Precedence is `--profile`, `MUSIC_TOOLS_PROFILE`, then local configuration.
Library profile commands fall back to the bundled profile; the exporter uses
built-in device defaults when no profile is selected. Set library and export
paths separately as described in [Getting started](GETTING-STARTED.md).

`sample-profile validate --source-kb /path/to/source-document.md` checks version
and date headers against the profile's source metadata. It does not test hardware
or inspect the library. Device additions require implementation and validation
beyond a profile edit.

For curation and export, use the [workflow guide](WORKFLOWS.md).
