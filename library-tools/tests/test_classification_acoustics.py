from __future__ import annotations

import numpy as np
import pytest

from librarytools.classification.acoustics import infer_bar_fit_error, rhythm_periodicity


def test_short_onset_envelope_has_no_valid_periodicity() -> None:
    assert rhythm_periodicity(np.array([1.0, 0.5]), sample_rate=22_050) == 0.0


def test_bar_fit_error_measures_distance_to_a_whole_four_beat_bar() -> None:
    assert infer_bar_fit_error(6.0, 160.0) == 0.0
    assert infer_bar_fit_error(6.2, 160.0) == pytest.approx(0.2 / 6.0)
    assert infer_bar_fit_error(6.0, 0.0) == 1.0
