import shutil
import subprocess

import pytest
from PIL import Image, ImageStat

from vfr import cuts, ocr


def _need_eng():
    if not shutil.which("tesseract"):
        pytest.skip("tesseract 가 PATH 에 없다")
    langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
    if "eng" not in langs.split():
        pytest.skip("tesseract eng 언어 데이터가 없다")


def test_pick_times_uses_shot_centers_and_caps():
    cut = {"probe": {"duration": 3.0}, "fine": [],
           "shots": [{"start": 0, "end": 1}, {"start": 1, "end": 2}, {"start": 2, "end": 3}]}
    assert ocr.pick_times(cut) == [0.5, 1.5, 2.5]
    many = {"probe": {"duration": 100.0}, "fine": [],
            "shots": [{"start": i, "end": i + 1} for i in range(50)]}
    assert len(ocr.pick_times(many)) == 20


def test_pick_times_adds_fine_cut_unless_near_a_center():
    cut = {"probe": {"duration": 10.0}, "shots": [{"start": 0, "end": 10}], "fine": [[2.0, 0.1], [4.6, 0.1]]}
    # 중심 5.0 에서 1.0 이내인 4.9 는 빠지고 2.3 만 붙는다
    assert ocr.pick_times(cut) == [2.3, 5.0]


def test_second_page_is_the_inverted_frame(video, tmp_path):
    """시각마다 [원본, 반전] 두 장이 나가고, 반전본은 밝기가 뒤집혀 있어야 한다."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg 가 없다")
    a, b = ocr._frames(video, [0.5], str(tmp_path))  # 0.5초 = 흰 장면
    mean = lambda p: ImageStat.Stat(Image.open(p).convert("L")).mean[0]
    assert mean(a) > 200 and mean(b) < 80


def test_reads_number_text_from_synthetic_video(video, tmp_path):
    _need_eng()
    cut = cuts.measure(video, tmp_path)
    res = ocr.main(video, cut, tmp_path, lang="eng")
    assert (tmp_path / "ocr.json").exists() and "error" not in res
    assert res["frames"] >= 3 and res["pages"] >= 2 * res["frames"]
    assert any("4821" in ln for row in res["rows"] for ln in row["lines"]), res["rows"]


def test_failure_still_leaves_ocr_json(tmp_path):
    cut = {"probe": {"duration": 1.0}, "fine": [], "shots": [{"start": 0, "end": 1}]}
    res = ocr.main(tmp_path / "missing.mp4", cut, tmp_path)
    assert res["rows"] == [] and res["error"]
    assert "error" in (tmp_path / "ocr.json").read_text(encoding="utf-8")
