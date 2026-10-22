"""모델을 내려받지 않는다 — WhisperModel 을 가짜로 바꿔 ffmpeg 가 만든 배열 모양과 파일 쓰기만 본다."""
import types

import pytest

pytest.importorskip("faster_whisper")
np = pytest.importorskip("numpy")

import faster_whisper  # noqa: E402

from vfr import asr  # noqa: E402

CALLS = {}


class FakeModel:
    def __init__(self, name, **kw):
        CALLS["init"] = (name, kw)

    def transcribe(self, audio, **kw):
        CALLS["audio"], CALLS["kw"] = audio, kw
        seg = types.SimpleNamespace(start=0.1, end=1.234, text=" hello 98765 ", avg_logprob=-0.3,
                                    no_speech_prob=0.02)
        return [seg], types.SimpleNamespace(language="en", language_probability=0.91234)


def test_passes_16khz_mono_float_array(video, tmp_path, monkeypatch):
    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
    res = asr.main(video, tmp_path)
    audio = CALLS["audio"]
    assert audio.dtype == np.float32 and audio.ndim == 1
    assert abs(len(audio) - 3 * 16000) < 0.3 * 16000  # 3초짜리 소리가 16kHz 모노로 나온다
    assert float(np.abs(audio).max()) <= 1.0 and float(np.abs(audio).max()) > 0.01  # 사인파가 실려 있다
    assert CALLS["init"][0] == "small" and CALLS["init"][1]["compute_type"] == "int8"
    assert CALLS["kw"] == {"vad_filter": True, "beam_size": 1}
    assert res["lines"] == [{"start": 0.1, "end": 1.23, "text": "hello 98765", "logprob": -0.3,
                             "no_speech": 0.02}]
    assert (tmp_path / "asr.json").exists()


def test_failure_leaves_asr_json_with_error(video, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no model")
    monkeypatch.setattr(faster_whisper, "WhisperModel", boom)
    res = asr.main(video, tmp_path)
    assert res["lines"] == [] and "no model" in res["error"]
    assert "no model" in (tmp_path / "asr.json").read_text(encoding="utf-8")
