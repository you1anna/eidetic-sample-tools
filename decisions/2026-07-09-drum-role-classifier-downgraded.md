# Drum-Role Classifier Downgraded After Failed Calibration

Date: 2026-07-09  
Project: eidetic-music-tools  
State: Active — classifier experimental only

## Decision

The integrated `faraway1nspace/DrumClassifer-CNN-LSTM` model is not a trusted
source of role truth. It may generate review candidates, but it must not
authorise moves, exclusions, hardware crates, or wider library organisation.

This supersedes the trust claim in
`decisions/2026-07-09-drum-role-classifier-adopted.md`. Human audition remains
authoritative.

## Evidence

The first route calibration tested ten files that the model labelled `snr`
(mapped locally to `CLAP-SNARE`) with probabilities from 0.803 to 0.985. Robin
auditioned all ten and confirmed all ten were kick drums: 0/10 proposed moves
were correct. The complete 62-file `KICKS → CLAP-SNARE` route is therefore
rejected for batch movement; no files moved.

The integration itself reproduced the upstream implementation:

- upstream and clean-room inference agreed on `snr` for all 10 files;
- the two model files had identical SHA-256 hashes;
- maximum absolute top-probability difference was 0.027.

The failure is model suitability and validation design, not a corrupted class
map or model file.

Measured domain difference:

- audition set median spectral centroid: 3,796 Hz; filename-canonical kick set:
  162 Hz;
- audition set median sub-energy ratio: 0.056; filename-canonical kick set:
  0.996.

The original validation used 12 easy filename-canonical kicks and 36 obvious
contaminants. It did not establish recall across processed or atypical kicks.
The `trust >= 0.80` band was an uncalibrated raw softmax threshold, not measured
real-world accuracy. Upstream training data is unavailable.

## Boundaries

- Stop the classifier-led cleanup plan before move-plan generation.
- Preserve the saved audit and Robin's labels as evaluation evidence.
- Do not move any of the 62 `KICKS → CLAP-SNARE` candidates.
- Do not treat the remaining 280 high-confidence mismatches as safe moves.
- The current `library-tools` venv also lacks the optional Torch/librosa
  dependencies; reproduce future model work in an explicit, recorded
  environment.

## Recommended Next Step

Ask Robin whether he is willing to label a representative benchmark of roughly
100 samples (about 25 each for KICKS, CLAP-SNARE, HATS-CYM, and PERC). If yes,
use that benchmark to score the current model and licensed alternatives before
integrating another classifier. If no, retire automated role movement and keep
organisation human-reviewed.
