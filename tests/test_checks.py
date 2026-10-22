import json

from vfr import checks


def _write(d, name, obj):
    (d / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _setup(d, readings):
    _write(d, "ocr.json", {"rows": [{"t": 0.5, "lines": ["TOTAL 4,821.50 USD", "share 37.9%"]}]})
    _write(d, "asr.json", {"lines": [{"start": 0, "end": 1, "text": "volume 987,654 units"}]})
    _write(d, "readings.json", readings)


def test_four_way_hits(tmp_path):
    _setup(tmp_path, [{"file": "sheet1.jpg", "text":
        "[판독] sheet1.jpg\n- 0.30s: 합계 4,821.50 달러 / 점유율 37.5% / 거래량 987,654 / 코드 5555"}])
    res = checks.run(tmp_path)
    hits = {i["n"]: i["hit"] for i in res["by_file"]["sheet1.jpg"]}
    assert hits == {"4821.50": "ocr", "37.5": "part", "987654": "asr", "5555": "none"}
    assert res["summary"] == {"tokens": 4, "ocr": 1, "part": 1, "asr": 1, "none": 1}
    assert res["has_ocr"] and res["has_asr"]
    assert json.loads((tmp_path / "checks.json").read_text(encoding="utf-8"))["summary"]["none"] == 1


def test_ocr_wins_over_asr_and_part_needs_same_integer(tmp_path):
    _setup(tmp_path, [{"file": "a.jpg", "text": "4,821.50 그리고 4,822.50"}])
    _write(tmp_path, "asr.json", {"lines": [{"text": "4,821.50 4,822.50"}]})
    hits = {i["n"]: i["hit"] for i in checks.run(tmp_path)["by_file"]["a.jpg"]}
    assert hits == {"4821.50": "ocr", "4822.50": "asr"}  # 정수부 4822 는 OCR 에 없다 → part 아님


def test_noise_is_not_checked(tmp_path):
    text = "[판독] sheet1.jpg\n0.30s 15분 MA20 7 2026-10-22 12:30:45 값 1,5"
    assert checks.tokens(checks._body(text)) == [("1,5", "15")]  # 두 자리라도 쉼표가 있으면 대상
    assert checks.tokens("15분 MA20 7 1.28s") == []


def test_duplicates_count_once_per_file_and_missing_inputs_ok(tmp_path):
    _write(tmp_path, "readings.json", [{"file": "a.jpg", "text": "9999 9999"},
                                       {"file": "a.jpg", "text": "9999 8888"}])
    res = checks.run(tmp_path)  # ocr.json · asr.json 이 없어도 돈다
    assert [i["n"] for i in res["by_file"]["a.jpg"]] == ["9999", "8888"]
    assert not res["has_ocr"] and not res["has_asr"] and res["summary"]["none"] == 2
