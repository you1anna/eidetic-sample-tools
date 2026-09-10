# Ableton Live control

Use the optional Live bridge to inspect a running Set, compare it with a known
checkpoint and apply a small reviewed edit plan. The package is experimental.
Its transport and safety contracts have synthetic test coverage; the staged Max
device, target Live-version behaviour, audible routing and studio hardware remain to be
qualified on the target system.

[Safety](SAFETY.md) · [State contracts](STATE-AND-CONTRACTS.md) ·
[Package reference](../live-tools/REFERENCE.md) · [Current status](../STATUS.md)

## What the two Ableton packages do

`ableton-tools` reads saved `.als` files while Live is closed or elsewhere. It
never talks to a running application. `live-tools` talks to one explicitly loaded
Max for Live device over loopback. It can observe the current Set and apply a
narrow allowlisted plan; it does not edit `.als` files directly.

Installing either package changes no Set. Importing `eideticlive` does not stage
or load a device. Device staging copies reviewed source and a build manifest only
to the destination you name.

## Install the optional layer

From the repository root, inside the same Python 3.12 environment as the library
tools:

```bash
python -m pip install -e ./live-tools -e './library-tools[live]'
python -m pip check
eidetic-live doctor
```

The `live` extra adds Flask for the audition browser and the exact matching
`eidetic-live-tools` version. The ordinary library/export/Ableton install does not
include either dependency.

## Stage and attach the bridge deliberately

Choose an empty local working folder. Staging never searches Live's directories
or modifies an installed device:

```bash
eidetic-live stage-device /path/to/eidetic-live-device
```

Read the staged build manifest and MIT notice. Open the staged patch in Max for
Live, build the `.amxd`, place or load it through Live's normal interface, then
save a dedicated test Set. Reload the device after changing its source. These are
manual Live steps; a successful staging command does not establish that the
device loaded or that its ports are reachable.

The default transport binds to loopback ports 9000 and 9001. Use different ports
only when you stage the device with the same values and record them in a JSON
configuration file:

```json
{
  "host": "127.0.0.1",
  "port": 9000,
  "ack_port": 9001,
  "timeout": 3.0,
  "lock_path": "/path/to/local/eidetic-live.lock"
}
```

Pass that file with `eidetic-live --config /path/to/live.json ...`. Keep the lock
and configuration on this Mac rather than the sample drive.

## Inspect before editing

Start with a detailed snapshot:

```bash
eidetic-live inspect --detail --output /path/to/checkpoint.json
```

Confirm `complete` is true and check the build ID, bridge instance ID, Set ID,
saved path/name, transport, tracks, routing, monitoring, arm state, devices and
clip slots. A missing saved path, changed bridge instance or partial inspection
is a mismatch to resolve, not a checkpoint to work around.

For a repeatable intended setup, compare the snapshot with a public or local
profile:

```bash
eidetic-live check --profile /path/to/profile.json \
  --snapshot /path/to/checkpoint.json --output /path/to/check.json
```

Manual items stay `unverified`; the command does not turn an inaudible route or
unplayed clip into a pass. Compare two observations without touching Live:

```bash
eidetic-live diff /path/to/checkpoint.json /path/to/after.json
```

## Apply a reviewed edit plan

Set a fresh mutation token in the shell that runs the CLI and configure the same
token in the staged device. The token is read from the environment and is never
written into snapshots, plans or reports:

```bash
export EIDETIC_LIVE_TOKEN='replace-with-a-long-random-value'
```

Write the intended operations JSON using the allowlisted operation shapes in the
[package reference](../live-tools/REFERENCE.md). Planning contacts Live, captures
the current exact runtime/Set identity and expected-before values, and writes no
mutation:

```bash
eidetic-live plan /path/to/operations.json --output /path/to/plan.json
```

Structural operations also require stopped transport, a manually saved Set and a
separate byte-matching `.als` checkpoint copy:

```bash
eidetic-live plan /path/to/structural-operation.json \
  --checkpoint /path/to/checkpoint-copy.als --output /path/to/plan.json
```

Read the complete plan, especially its Set identity, expected-before values and
target paths. Applying requires an explicit flag and receipt destination:

```bash
eidetic-live apply /path/to/plan.json --apply \
  --receipt /path/to/receipt.json
```

Each operation checks the expected current value and reads back the result. The
tool stops on a mismatch. It does not retry after an uncertain mutation reply:
Live may have applied a request even when its acknowledgement was lost. Inspect
the same Set and reconcile the receipt instead:

```bash
eidetic-live reconcile /path/to/receipt.json --output /path/to/reconciliation.json
```

For a complete parameter-only receipt, prepare a guarded restore plan:

```bash
eidetic-live restore-parameters /path/to/receipt.json \
  --output /path/to/restore-plan.json
```

This refuses to overwrite a parameter that was changed again after the receipt.
Read the generated plan, then apply it through the same explicit `eidetic-live
apply ... --apply --receipt ...` path. Structural operations have no automatic
restore plan.

After a clean receipt, listen, inspect routing and meters, save the Set, close and
reload it, then inspect again. Those checks establish the musical and persistence
result that the transport cannot prove.

## Audition a saved plan in Live

Prepare the browser from a validated collection plan. The session keeps the full
candidate identity list and creates working WAVs lazily in batches of 12:

```bash
sample-vibe prepare --root /path/to/SAMPLES --plan /path/to/plan.json \
  --output-dir /path/to/plan-audition
sample-vibe serve --session-dir /path/to/plan-audition --open
```

In the browser, choose `Playback: Live`, enter the path to the currently open,
saved `.als`, and select **Preview attachment**. Read the JSON preview, including
the Set and bridge identity, retained checkpoint and the managed track names. The
checkpoint is a byte-matching `.als` copy under the audition session's
`live-checkpoints/`; keep it with the session. **Confirm in Live** creates only
missing Reference and Candidate audio tracks; the Set tempo stays unchanged.

Selecting another sample does not load or play it automatically. Select **Preview
candidate load**, review the exact working WAV and managed slot, then confirm. You
can separately preview and confirm a sample as the managed Reference. **Play**
fires the Candidate and, when selected, the Reference; Stop affects only the two
managed tracks. Other Set tracks may remain audible. Gain shows Live's normalised
clip value as dB. Loop can be enabled only after Warp is on; correct the grid and
loop bounds manually in Live first.

The Warp switch and mode menu write only the loaded managed clip and show Live's
readback. Available modes come from that clip. Grid markers and loop bounds still
need manual correction in Live; the browser does not infer timing.

Any Live error disconnects the browser controls for that serving process. Inspect
the Set and attachment evidence before restarting; there is no automatic fallback
or reconnect. **Read recovery report** performs no write. After a bridge reload,
Preview attachment and Confirm can reuse recognised managed tracks and verified
clips, creating only a missing track. An uncertain operation is never replayed.
None of these controls changes tempo or converts a Keep into export approval. Save
the Set manually in Live.

Keep and Skip remain attached to the original `sample_id`, independent of the
current batch or working WAV. When listening is complete, create the ordinary
curation packet and add the favourite role/name evidence separately:

```bash
sample-vibe packet --session-dir /path/to/plan-audition \
  --output-dir /path/to/curation-packet
```

Before relying on this path for a session, qualify device load/reload, exact Set
attachment, managed-track reuse, audible preview, routing, Warp/grid display,
Keep/Skip persistence, Set save/reload and safe recovery from a lost mutation
acknowledgement. Record the actual Live build and staged-device build ID with the
result.

If the sample drive remounts at another path before you resume, verify and rebind
the version 2 session before serving it:

```bash
sample-vibe rebind-root --session-dir /path/to/plan-audition \
  --root /new/path/to/SAMPLES
```

## Retain bounce evidence

If a later workflow renders audio, bind the retained file to its successful edit
receipt rather than treating any similarly named bounce as proof:

```bash
eidetic-live retain-bounce --receipt /path/to/receipt.json \
  --audio /path/to/render.wav --output /path/to/render-evidence.json
```

This records file evidence. It does not judge the mix, prove real-time playback or
replace listening.
