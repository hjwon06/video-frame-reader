import json

import pytest
from PIL import Image

from vfr import cli, reader

CUT = {"probe": {"width": 640, "height": 360, "duration": 3.0}, "fine": [],
       "shots": [{"n": i + 1, "start": float(i), "end": float(i + 1), "len": 1.0} for i in range(3)]}


def _sheets(d, n=3):
    for i in range(1, n + 1):
        Image.new("RGB", (40, 30), "white").save(d / ("sheet%d.jpg" % i))


def _readings(d):
    return json.loads((d / "readings.json").read_text(encoding="utf-8"))


def test_every_sheet_gets_a_reading(tmp_path, fake_claude, monkeypatch):
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    _sheets(tmp_path)
    res = reader.read_sheets(tmp_path, CUT, claude=fake_claude, model="some-model")
    assert res == {"sheets": 3, "errors": []}
    rd = _readings(tmp_path)
    assert [r["file"] for r in rd] == ["sheet1.jpg", "sheet2.jpg", "sheet3.jpg"]
    for r in rd:
        assert r["file"] in r["text"] and "4,821.50" in r["text"]
        assert "[판독 끝]" not in r["text"] and "error" not in r
    calls = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert len(calls) == 3  # 시트 한 장에 claude 한 번
    argv = calls[0]["argv"]
    assert argv[:3] == ["-p", "--output-format", "stream-json"] and "--verbose" in argv
    assert argv[argv.index("--model") + 1] == "some-model"
    for n, call in enumerate(calls, 1):  # 허용 도구는 그 시트 한 장의 절대경로 — 'Read' 단독이 아니다
        rule = call["argv"][call["argv"].index("--allowedTools") + 1]
        sheet = (tmp_path / ("sheet%d.jpg" % n)).resolve()
        assert rule != "Read" and rule == "Read(/%s)" % sheet and rule.startswith("Read(//")
    assert "640x360" in calls[0]["prompt"] and "sheet1.jpg" in calls[0]["prompt"]
    assert "{{" not in calls[0]["prompt"]  # 자리표시자가 남지 않는다


def test_sheets_are_read_in_numeric_order(tmp_path, fake_claude, monkeypatch):
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    for n in (10, 2):
        Image.new("RGB", (40, 30), "white").save(tmp_path / ("sheet%d.jpg" % n))
    res = reader.read_sheets(tmp_path, CUT, claude=fake_claude)
    assert res == {"sheets": 2, "errors": []}
    assert [r["file"] for r in _readings(tmp_path)] == ["sheet2.jpg", "sheet10.jpg"]
    rules = [json.loads(x)["argv"] for x in log.read_text(encoding="utf-8").splitlines()]
    assert [a[a.index("--allowedTools") + 1].rsplit("/", 1)[1] for a in rules] == ["sheet2.jpg)", "sheet10.jpg)"]


def test_reading_without_head_line_attaches_to_opened_sheet(tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "nohead")
    _sheets(tmp_path, 2)
    assert reader.read_sheets(tmp_path, CUT, claude=fake_claude)["errors"] == []
    assert all("4,821.50" in r["text"] for r in _readings(tmp_path))


def test_opened_but_unread_sheet_is_marked(tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "silent")
    _sheets(tmp_path, 2)
    res = reader.read_sheets(tmp_path, CUT, claude=fake_claude)
    assert len(res["errors"]) == 2
    assert all(r["text"] == "" and r["error"] == "판독 글 없음" for r in _readings(tmp_path))


def test_crash_is_recorded_not_raised(tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "crash")
    _sheets(tmp_path, 2)
    res = reader.read_sheets(tmp_path, CUT, claude=fake_claude)
    assert len(res["errors"]) == 2 and "결과 없이 끝남" in res["errors"][0]
    assert [r["file"] for r in _readings(tmp_path)] == ["sheet1.jpg", "sheet2.jpg"]


def test_binary_comes_from_env_and_missing_binary_is_clear(tmp_path, fake_claude, monkeypatch):
    _sheets(tmp_path, 1)
    monkeypatch.setenv("VFR_CLAUDE", fake_claude)
    assert reader.read_sheets(tmp_path, CUT)["errors"] == []
    monkeypatch.setenv("VFR_CLAUDE", str(tmp_path / "nope"))
    with pytest.raises(FileNotFoundError, match="VFR_CLAUDE"):
        reader.read_sheets(tmp_path, CUT)


def test_cli_runs_every_stage(video, tmp_path, fake_claude, monkeypatch):
    """cli 가 컷 → 시트 → 판독 → 대조를 실제로 부른다 (OCR · 음성은 끈다)."""
    out = tmp_path / "out"
    code = cli.main(["run", str(video), "--out", str(out), "--no-ocr", "--no-asr", "--claude", fake_claude])
    assert code == 0
    assert (out / "cuts.json").exists() and (out / "sheet1.jpg").exists()
    assert not (out / "ocr.json").exists() and not (out / "asr.json").exists()
    assert [r["file"] for r in _readings(out)] == ["sheet1.jpg"]
    checks = json.loads((out / "checks.json").read_text(encoding="utf-8"))
    assert checks["summary"]["tokens"] == 2 and checks["summary"]["none"] == 2  # OCR · 음성이 없으니 전부 none


def test_cli_no_llm_skips_reader_and_checks(video, tmp_path):
    out = tmp_path / "out"
    assert cli.main(["run", str(video), "--out", str(out), "--no-ocr", "--no-asr", "--no-llm"]) == 0
    assert (out / "cuts.json").exists() and (out / "sheet1.jpg").exists()
    assert not (out / "readings.json").exists() and not (out / "checks.json").exists()


def test_cli_missing_video_exits_2(tmp_path, capsys):
    assert cli.main(["run", str(tmp_path / "none.mp4"), "--out", str(tmp_path / "o")]) == 2
    assert "영상 파일이 없다" in capsys.readouterr().err


def test_cli_missing_claude_exits_1_with_reader_failure(video, tmp_path, capsys):
    out = tmp_path / "out"
    code = cli.main(["run", str(video), "--out", str(out), "--no-ocr", "--no-asr",
                     "--claude", str(tmp_path / "nope")])
    err = capsys.readouterr().err
    assert code == 1
    assert "판독 실패" in err and "!! reader:" in err
