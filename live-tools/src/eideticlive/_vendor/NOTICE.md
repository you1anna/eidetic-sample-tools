# Upstream notice

`bridge.py`, `resources/live_udp_bridge.js`, `resources/live_udp_bridge.maxpat`
and `resources/osc_loopback_receiver.js` are vendored unchanged from
[codex-live-bridge](https://github.com/sunflower-of-parchman/codex-live-bridge) commit
`6b9ed94dd471d2b33c3218792e644a4f85fb32e3`.
The upstream MIT licence is retained in `LICENSE`. Eidetic reuses its OSC codec,
request layouts, ACK parsers and validators. Staging appends the separately
maintained `eidetic_extension.js` and renames runtime files in an isolated folder.

The preserved source bytes were checked against the upstream Git blob IDs:

| Local file | Upstream Git blob |
|---|---|
| `bridge.py` | `f385c52afa821d0f33790be0f3a3a3db193b132e` |
| `LICENSE` | `518015a608a9b92f116f46eef053bf580ad4dcf7` |
| `resources/live_udp_bridge.js` | `740ebb739b310949c9b217ad0b7357d65237c8c6` |
| `resources/live_udp_bridge.maxpat` (upstream `LiveUdpBridge.maxpat`) | `4a34e709dd7c439d66709337a6a449ecbb2818eb` |
| `resources/osc_loopback_receiver.js` | `b14c440ee4bdbcaebb64d5e542fec651bb21be7e` |
