# Library storage

Keep original packs, searchable catalogue audio and approved favourites as
separate [library zones](WORKFLOWS.md#library-zones). Device exports are derived
copies that can be rebuilt from those sources and retained listening decisions.

Set `SAMPLES_ROOT` to the library location. `EXPORT_ROOT` defaults to `_EXPORT/`
inside that root and can point to another staging location. Hardware media uses
the [device-specific transfer route](../sample-tools/REFERENCE.md#transfer-to-a-card).

Back up source audio, labels, manifests and the inventory. A second copy on the
same physical drive does not protect against drive failure; undo records are
not backups. See the [safety model](SAFETY.md#backup-responsibilities).

Continue with the canonical [workflow](WORKFLOWS.md). Historical observations
about the reference library remain in [library history](LIBRARY-HISTORY.md);
[project status](../STATUS.md) records the current checkpoint.
