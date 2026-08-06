from __future__ import annotations

import numpy as np

from librarytools.classification.acoustics import rhythm_periodicity


def test_short_onset_envelope_has_no_valid_periodicity() -> None:
    assert rhythm_periodicity(np.array([1.0, 0.5]), sample_rate=22_050) == 0.0
