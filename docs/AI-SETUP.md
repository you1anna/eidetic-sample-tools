# Reinstallable local AI

Keep the two existing CLAP models. They classify existing audio; they do not
generate samples or train on your library. Inference runs on your CPU, uses RAM
and takes time. No paid token API is involved and sample audio is not uploaded.
Installing this environment does not start a background service.

## Install once per Apple Silicon Mac

This tested snapshot targets **Python 3.12 on macOS arm64**. Intel Macs and Linux
need their own tested dependency resolution; do not assume this lock covers them.
The core toolkit continues to have separate macOS/Linux checks.

From the repository root, use a new local environment. Keep it off the sample SSD.
This environment contains the complete toolkit plus AI; it does not need a second
worker environment or changes to existing environments.

```bash
python3.12 -m venv "$HOME/.venvs/eidetic-ai"
source "$HOME/.venvs/eidetic-ai/bin/activate"
python -m pip install --require-hashes --only-binary=:all: -r requirements-ai-macos-arm64.txt
python -m pip install --no-build-isolation --no-deps './library-tools[audio-classifier,review-ui,dev]' ./sample-tools ./ableton-tools
python -m pip check
sample-ai doctor
sample-ai download
sample-ai check
```

If the environment is read-only, give librosa/Numba a writable local compilation
cache before checking or classifying:

```bash
export NUMBA_CACHE_DIR="$HOME/.cache/eidetic-sample-tools/numba"
mkdir -p "$NUMBA_CACHE_DIR"
```

FFmpeg and FFprobe remain system dependencies for the wider toolkit. A regular
package install above copies the selected source revision; changing the checkout
does not change that installation until you reinstall it. Retain the source
revision with the lockfile. The lock pins transitive Python dependencies and
checks download hashes; it does not pin macOS, Python patch releases or FFmpeg.

`download` fetches only the required files for the two existing checkpoint
revisions. It is the network/download step and can be rerun to reuse the cache.
`check` always works offline on one generated one-second tone in a temporary
directory. It loads both models sequentially, verifies fresh embeddings and
cached reuse, and reports time, peak worker memory and installed versions as JSON.
It never scans or opens the sample library. Use `--threads 1` for less CPU
contention or `--worker-timeout SECONDS` if this small check exceeds its limit.

The default model cache is `~/.cache/huggingface/hub`. To choose another **local**
cache, set `HF_HOME` consistently before both download and use. Models remain
separate from the portable library database; the embeddings travel with that
database. See [Hugging Face caching](https://huggingface.co/docs/huggingface_hub/guides/manage-cache)
and [offline configuration](https://huggingface.co/docs/transformers/installation#offline-mode).

## Use with 22,000 samples

See the [real-library trial](SET-GENERATION-TRIAL.md) for measured indexing,
256-file inference and cache timings, the conditional whole-library estimate,
and the listening results and remaining hardware checks. The steps below describe
current supported commands; they do not automate selection from a musical brief.

1. Build/reuse the ordinary index and acoustic features with `sample-tag`.
   These do not require CLAP. Avoid `--rescan` when no fresh inventory is needed.
2. Use `sample-find` to narrow the library by role, tags, origin or acoustic
   similarity. Prepare a small audition packet using the normal curation workflow.
3. Apply AI grouping only to that packet. Start with a few dozen candidates;
   loading a model once for a packet amortises startup cost.
4. Listen, record decisions and promote through the existing workflow. AI scores
   never replace musical approval. Unchanged embeddings are reused across packets.

```bash
export SAMPLES_ROOT=/path/to/SAMPLES
export RUNS="$SAMPLES_ROOT/.eidetic/runs"
HF_HUB_OFFLINE=1 sample-curate --root "$SAMPLES_ROOT" classify-packet \
  --labels "$RUNS/session-01/labels.tsv" \
  --benchmark "$RUNS/session-01/benchmark-labels.tsv" \
  --threads 2 --batch-size 2 --worker-timeout 300
```

The packet must already exist. Models run one at a time and exit when finished.
The timeout applies to each model worker including loading and all of its batches,
not to every individual sample or the whole command. Source verification and
acoustic analysis are outside that worker timeout. A timeout terminates the worker;
completed embedding batches remain in SQLite for a retry. The active batch may
need recomputing. Larger packets may need a higher timeout.

Threads and batch size control CPU contention and working memory; they are not a
hard RAM quota or a guarantee that Ableton will be unaffected. Use `--threads 1
--batch-size 1` or classify outside a recording session when responsiveness matters.
The model's internal excerpt batches remain bounded at eight excerpts. Do not
change model revisions or excerpt policies casually: those changes invalidate
embedding reuse. Existing cached embeddings are retained; no forced rebuild occurs.

Two 512-dimensional float16 vectors per sample require about **43 MiB for 22,000
samples**, before SQLite keys/indexes, prompt embeddings and other library data.
Storage is modest; uncached inference over the whole library is the costly step.
There is no automatic whole-library AI job in this setup. Inspect cache growth
with `sample-library maintenance --root "$SAMPLES_ROOT" --json`.

## Measured verification, 9 September 2026

On this Apple Silicon Mac, Python 3.12.13:

- Dependency environment: about 867 MB; model files/cache: about 1.3 GB.
- First offline synthetic check, both models: 36.6 seconds including first-use
  startup; peak worker memory about 1.13 GiB, one worker at a time.
- Repeating from SQLite embeddings: 0.16 seconds, without loading either model.
- Both existing real-model integration tests passed offline in 8.7 seconds.
- Final combined standard suite: 721 passed; the two optional model integrations
  were also run separately and passed. Installed-wheel lifecycle/browser checks
  passed outside the checkout. A ready-to-use wheel installation is available on
  this Mac in `~/.venvs/eidetic-ai`; existing environments were preserved.
- The installed wheel also passed the offline AI check outside the checkout,
  using an explicit writable `NUMBA_CACHE_DIR` under the execution sandbox.

These are installation checks, not classification-accuracy measurements or a
whole-library throughput estimate. Longer clips, batch size, CPU load and machine
hardware change runtime and memory use.

## Updating and testing

The lockfile is generated from `library-tools/pyproject.toml`, including the
`audio-classifier`, `review-ui` and `dev` extras. Its header records the `uv pip
compile` command used. Keep it distinct from the lightweight core test snapshot.
For a dependency update, change the supported package ranges if needed, regenerate
the lock, install it into a fresh environment, run `pip check`, the combined test
suite, `sample-ai check`, and both real-model tests. Do not freeze an unrelated
working environment or silently upgrade dependencies during classification.

```bash
HF_HUB_OFFLINE=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  RUN_CLAP_INTEGRATION=1 RUN_DUAL_CLAP_INTEGRATION=1 \
  python -m pytest library-tools/tests/test_model_workers.py \
  library-tools/tests/test_packet_classifier.py -q
```

The manually triggered [AI workflow](../.github/workflows/ai-checks.yml) installs
the hashed snapshot, caches checkpoint downloads, runs offline tests and retains
the synthetic performance report. It has a 20-minute job limit. Ordinary push/PR
tests continue to skip model downloads; remote AI CI has not been run by this work.
