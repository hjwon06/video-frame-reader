from vfr import cuts


def test_thresholds_are_the_documented_ones():
    assert (cuts.BIG, cuts.FINE, cuts.GAP) == (0.20, 0.10, 0.25)


def test_cuts_at_merges_within_gap_and_keeps_peak():
    scores = [(0.0, 0.0), (1.00, 0.5), (1.10, 0.9), (1.40, 0.3), (2.0, 0.15), (3.0, 0.05)]
    assert cuts.cuts_at(scores, cuts.BIG) == [[1.0, 0.9], [1.4, 0.3]]
    # 0.10 임계에서는 2.0초의 작은 변화도 잡힌다 — 0.05 는 여전히 아래
    assert [t for t, _ in cuts.cuts_at(scores, cuts.FINE)] == [1.0, 1.4, 2.0]


def test_cuts_at_gap_is_measured_from_first_of_cluster():
    # 0.25초 이상 떨어지면 별개 컷이다
    assert len(cuts.cuts_at([(1.0, 0.5), (1.25, 0.5)], 0.2)) == 2
    assert len(cuts.cuts_at([(1.0, 0.5), (1.24, 0.5)], 0.2)) == 1


def test_measure_finds_both_scene_boundaries(video, tmp_path):
    res = cuts.measure(video, tmp_path)
    assert (tmp_path / "cuts.json").exists()
    assert len(res["big"]) == 2
    for (t, _), want in zip(res["big"], (1.0, 2.0)):
        assert abs(t - want) <= 0.25, res["big"]
    assert [s["n"] for s in res["shots"]] == [1, 2, 3]
    assert abs(res["probe"]["duration"] - 3.0) < 0.3
    assert res["probe"]["audio"] is True and res["audio"]["mean_db"] is not None
