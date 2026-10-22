"""음성 받아쓰기 — faster-whisper (int8, CPU).

파일 경로를 직접 넘기면 PyAV 버전 충돌로 죽는 조합이 있어, ffmpeg 로 16kHz 모노 배열을 만들어 넘긴다.
실패해도 asr.json 에 error 를 남긴다.
faster-whisper · numpy 는 이 함수를 부를 때 불러온다(없으면 --no-asr 로 건너뛸 수 있게).
"""
import os
import subprocess

from . import write_json


def transcribe(video, model="small"):
    import numpy as np
    from faster_whisper import WhisperModel

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-ac", "1",
                          "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    m = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 1)
    segs, info = m.transcribe(audio, vad_filter=True, beam_size=1)
    lines = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
              "logprob": round(s.avg_logprob, 2), "no_speech": round(s.no_speech_prob, 2)}
             for s in segs]
    return {"model": model, "language": info.language,
            "lang_prob": round(info.language_probability, 3), "lines": lines}


def main(video, out, model="small"):
    try:
        res = transcribe(video, model)
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 결과 파일은 남긴다
        res = {"error": repr(e)[:500], "lines": []}
    write_json(out / "asr.json", res)
    return res
