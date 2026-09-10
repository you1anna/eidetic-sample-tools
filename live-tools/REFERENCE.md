# Live tools reference

Requires Python 3.12+, Ableton Live with Max for Live, and Node for Max. Native
device insertion requires Live 12.3+. Runtime support is checked against exposed
Live API capabilities. This package has software boundary tests; real device and
musical workflow qualification is still pending.

## Stage and load the device

Install this package explicitly using the repository installer or `pip install ./live-tools`.
No import or installation script changes a Live device. Stage to a new directory:

```bash
eidetic-live stage-device /path/to/eidetic-runtime
```

The directory contains `eidetic_live.maxpat`, isolated `eidetic_runtime.js` and
`eidetic_receiver.js`, upstream licence, and a file-hash/build manifest. Keep these
files together; do not overwrite an existing upstream device. Optional `--port`
and `--ack-port` change the staged loopback ports; configure matching client ports.

1. Open a blank Max MIDI Effect from Live and open its Max editor.
2. Open the staged patcher in Max. Copy its patcher objects and connections into
   the blank Max MIDI Effect, replacing its blank patcher content. Preserve the
   complete supplied patch and its Node receiver wiring.
3. Save the device as `Eidetic Live.amxd` in the staging directory alongside the
   two isolated JavaScript files. Include those dependencies if freezing the
   device. This manual build must be verified in Max; staging does not create an
   `.amxd` binary or prove the device works.
4. Load one instance in the intended saved Live Set. Remove/disable other bridge
   instances using the same ports. Confirm Node for Max starts without a bind
   error in its console.
5. Configure a 16–256 byte authentication token in the device's `set_auth_token`
   message, then send it. The packaged message contains only a placeholder.
   Use the same secret in `EIDETIC_LIVE_TOKEN` in the client environment. Do not
   save a real token into the public patch or include it in reports. Token setup
   is transient and may need repeating after device reload.
6. Run `eidetic-live doctor`. Verify the Set name/path and runtime build/instance
   identity. A legacy/stale build is rejected. After replacing staged source,
   rebuild/reload the device and repeat this check; existing plans become stale.

The extension deliberately reserves `/api/get live_set eidetic_runtime` as a
bridge pseudo-property; it is not a Live Object Model property. It returns the
source build ID, JS-load instance ID, current Song ID and official Song
`file_path`/`name`. Unsaved Sets have no usable saved path and cannot be edited.

## Configuration

The default command/ACK ports are `127.0.0.1:9000` and `127.0.0.1:9001`.
`~/.config/eidetic-live/config.json`, `EIDETIC_LIVE_CONFIG`, or the global
`--config FILE` option selects JSON transport configuration:

```json
{"host":"127.0.0.1","port":9000,"ack_port":9001,"timeout":3.0}
```

Token input is only the `EIDETIC_LIVE_TOKEN` environment variable. It is never
written to plans, receipts or staging manifests. `lock_path` optionally overrides
the default per-ACK-port lock in `~/.cache/eidetic-live`. All cooperating clients
using that ACK port must share the same lock path. Socket bind conflicts and lock
timeouts fail clearly. Non-loopback hosts and privileged/equal ports are refused.

## Inspect, compare and check

```bash
eidetic-live inspect --detail --output before.json
eidetic-live inspect --detail --output after.json
eidetic-live diff before.json after.json --output changes.json
eidetic-live check --profile expected.json --snapshot after.json
```

Use the global `--summary` option for concise human output, for example
`eidetic-live --summary inspect` or `eidetic-live --summary check --profile expected.json`.
It also works with doctor and diff. Requested output files always remain JSON.

Read-only JSON reports carry `schema`, `schema_version: 1` and completeness.
Inspection is sequential, not an atomic Live transaction. It rechecks Set identity
and track IDs at the end. API/packet errors produce `complete: false` and exit 2.
Mixer volume, panning, activation and sends are included. Track IDs are valid for a loaded Set instance; paths can change after insertions.

Expectation profiles use explicit names and optional routing/monitor values:

```json
{
  "schema_version": 1,
  "tracks": [{"name":"Audio 1","current_monitoring_state":2,"arm":0}],
  "forbid_monitoring": ["Desk Return"],
  "manual_checks": ["Audio interface and physical clock"]
}
```

Routing keys are `input_routing_type`, `input_routing_channel`,
`output_routing_type`, `output_routing_channel`. A string expectation compares the
reported routing dictionary's `display_name`. Ambiguous/missing tracks fail.
Monitoring Off is 2. Manual checks yield `unverified`, never `pass`; the bridge
cannot establish physical interface, buffer, sample-rate or clock settings.

## Plan and apply

Create `operations.json` containing one explicit structural operation, or a batch
of at most 32 independent exposed parameter changes:

```json
[{"op":"set_parameter","path":"live_set tracks 0 devices 0 parameters 1","value":0.5}]
```

```bash
eidetic-live plan operations.json --output reviewed-plan.json
eidetic-live apply reviewed-plan.json --apply --receipt receipt.json
eidetic-live reconcile receipt.json --output reconciliation.json
eidetic-live restore-parameters receipt.json --output restore-plan.json
```

Apply requires both the explicit flag and a fresh receipt path. It refuses changed
plan content, runtime identity, target IDs/values, source files or saved Set bytes.
Receipts are journalled before sends; no mutation is automatically retried.
A complete receipt verifies Live memory readback. `restore-parameters` builds a
fresh parameter-only plan when current values still equal the verified applied
values; review and apply that plan normally. It never overwrites later tweaks. Save the Set manually, then
inspect after reload to verify persistence. Reconciliation only reads state; a
new plan is needed before a deliberate retry.

For structural operations, stop transport/recording, save Live manually, make a
separate `.als` checkpoint copy and pass `--checkpoint /path/to/checkpoint.als`
when planning. The copy must match the saved Set hash. This protects saved bytes;
the software cannot prove that unsaved changes were saved before copying.
Structural plans contain one operation so that subsequent paths are replanned.

| `op` | Required fields beyond `op` and canonical `path` |
|---|---|
| `set_parameter` | `value`; target is an exposed `devices N ... parameters N` path. Enabled/min/max/quantisation checked. |
| `insert_device` | `device`, zero-based `index`; target is a track. |
| `duplicate_template` | `name`; target is an existing track to duplicate and rename. |
| `create_clip` | `name`, and either positive MIDI `length` in beats or absolute audio `file_path`; target is an empty `clip_slots N`. |
| `name_clip` | `name`; target is an existing Session `clip_slots N clip`. |
| `place_clip` | `clip_path`, explicit `start` in beats; target is the source clip's track. Existing Arrangement overlaps are refused. |

Native insertion allowlist: EQ Eight, Auto Filter, Utility, Compressor, Glue
Compressor, Saturator, Reverb, Delay, Echo and Limiter. Plug-ins and Max devices
must already exist in a manually prepared template. The API cannot promise full
preset/library browsing or arbitrary instrument loading. Duplication fingerprints
exposed top-level parameters and Session clip IDs; nested rack internals, MIDI
notes and automation are not exhaustively fingerprinted.

## Retain a manual bounce

Export WAV from Live explicitly, then link it to an edit receipt:

```bash
eidetic-live retain-bounce --receipt receipt.json --audio bounce.wav --output bounce-lineage.json
```

The fresh lineage file records audio/receipt hashes and WAV metadata. It does not
render audio, verify musical approval, or prove which Set produced the supplied
file. AIFF/FLAC lineage is not currently supported.

## Python API

`LiveClient(config=None)` exports `get(path, property)`, `set(path, property, value)`,
`call(path, method, args)`, `request(address, args, write=False)`, `describe(path)`,
`children(path, child)`, `runtime()` and `inspect(detail=False)`. Get/call collapse
singleton result lists; request returns the validated ACK payload dictionary.
`get(path, 'id')` resolves the object's ID through describe. Bare `id N` references
resolve through Live, but compound `id N child ...` paths are not supported.

The low-level set/call/request methods are integration primitives and do not
replace the public guarded edit workflow. There is no raw mutation CLI.
`eideticlive.edits` exports `plan_edits(client, operations, checkpoint=None)`,
`apply_plan(client, plan, receipt_path=None)` (a fresh path is required), and
`reconcile(client, receipt)`. A client `exclusive()` context serialises compound
operations against cooperating clients; it cannot lock out manual Live actions.

## Limits

No automatic rendering, saving, undo, retry, plug-in preset authoring, replacing
occupied clips, routing changes or tempo changes are provided by guarded edits.
UDP acknowledgement loss means the mutation may already have happened. Receipts
and checkpoint files are evidence, not an automatic rollback system. User actions
or other non-cooperating controllers can still race a sequential operation.

Primary API references: [Song](https://docs.cycling74.com/apiref/lom/song/),
[Track](https://docs.cycling74.com/apiref/lom/track/),
[ClipSlot](https://docs.cycling74.com/apiref/lom/clipslot/),
[Clip](https://docs.cycling74.com/apiref/lom/clip/).
