from librarytools.classification.benchmarks import score_benchmark


def test_empty_benchmark_is_not_ready_or_publishable():
    score = score_benchmark([])

    assert score.total == 0
    assert score.ready is False
    assert score.passed is False
