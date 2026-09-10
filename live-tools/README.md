# Live tools

**Inspect a loaded Ableton Live Set and review small edits before applying them.**

This independent, experimental package needs no sample library or index. It adds
routing checks, saved snapshots and guarded edits through an explicitly installed
Max for Live bridge. Actual Live operation still needs hardware qualification.

[Setup and command reference](REFERENCE.md) · [Architecture](ARCHITECTURE.md)

## Start with a snapshot

After [staging and loading the device](REFERENCE.md#stage-and-load-the-device):

```bash
eidetic-live doctor
eidetic-live inspect --output session.json
```

Inspection includes the loaded Set's identity, tempo, transport, track routing,
monitoring, device inventory and Session clips. Detail mode adds exposed device
parameters and Arrangement clips. Missing responses produce an incomplete result.

## Make a small, reviewable change

You can plan exposed parameter changes, insert allowlisted native audio effects,
duplicate an existing template track, create and name Session clips, or place a
Session clip at an explicit free Arrangement position. Plans retain the expected
state; apply checks it again and records readback in a receipt.

Structural edits require stopped transport and a separate checkpoint of the saved
Set. An uncertain response stops the operation; read-only reconciliation helps
establish what happened. Save changes in Live manually after verification.

[Follow the edit example](REFERENCE.md#plan-and-apply) · [Safety limits](REFERENCE.md#limits)
