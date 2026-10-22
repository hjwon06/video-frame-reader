"""컷 · 소리 측정 — ffmpeg 한 번 디코딩으로 모든 프레임의 장면 점수를 받아 임계별로 자른다.

임계 0.20 = 큰 컷(장면 전환), 0.10 = 자막 · 애니메이션 같은 작은 변화.
0.25초 안에 몰린 변화는 하나로 친다(전환 효과가 여러 프레임에 걸치므로).
"""
import json
import re
import subprocess

from . import write_json

BIG, FINE, GAP = 0.20, 0.10, 0.25


def _run(cmd, timeout=900):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def probe(video):
    r = _run(["ffprobe", "-v", "error", "-show_entries",
              "stream=codec_type,codec_name,width,height,r_frame_rate:format=duration",
              "-of", "json", str(video)])
    try:
        j = json.loads(r.stdout)
        duration = float(j["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        raise RuntimeError("ffprobe 가 영상 길이를 읽지 못했다: %s" % (r.stderr.strip()[-200:] or video))
    st = j.get("streams", [])
    v = next((s for s in st if s.get("codec_type") == "video"), {})
    num, _, den = (v.get("r_frame_rate") or "0/1").partition("/")
    return {"duration": round(duration, 2),
            "width": v.get("width"), "height": v.get("height"),
            "fps": round(int(num) / max(int(den or 1), 1), 2), "vcodec": v.get("codec_name"),
            "audio": any(s.get("codec_type") == "audio" for s in st)}


def scene_scores(video):
    """[(초, 점수)] — metadata=print 가 로그(stderr)에 프레임마다 pts_time 과 scene_score 를 찍는다."""
    r = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-an", "-vf",
              "scale=270:-2,select='gte(scene,0)',metadata=print", "-f", "null", "-"])
    out, t = [], None
    for line in r.stderr.splitlines():
        m = re.search(r"pts_time:([0-9.]+)", line)
        if m:
            t = float(m.group(1))
            continue
        m = re.search(r"lavfi\.scene_score=([0-9.]+)", line)
        if m and t is not None:
            out.append((t, float(m.group(1))))
            t = None
    return out


def cuts_at(scores, th):
    res = []
    for t, s in scores:
        if s <= th:
            continue
        if res and t - res[-1][0] < GAP:
            res[-1][1] = max(res[-1][1], s)
        else:
            res.append([t, s])
    return [[round(t, 2), round(s, 3)] for t, s in res]


def audio(video):
    e = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn", "-af",
              "silencedetect=noise=-35dB:d=0.35,volumedetect", "-f", "null", "-"], 300).stderr

    def num(pat):
        m = re.search(pat, e)
        return float(m.group(1)) if m else None
    return {"mean_db": num(r"mean_volume: (-?[0-9.]+) dB"),
            "peak_db": num(r"max_volume: (-?[0-9.]+) dB"),
            "silence_starts": [round(float(x), 2) for x in re.findall(r"silence_start: (-?[0-9.]+)", e)]}


def measure(video, out):
    """영상을 재서 out/cuts.json 을 쓰고 같은 내용을 돌려준다."""
    info = probe(video)
    sc = scene_scores(video)
    big = cuts_at(sc, BIG)
    bounds = [0.0] + [t for t, _ in big] + [info["duration"]]
    spans = [(a, b) for a, b in zip(bounds, bounds[1:]) if b - a > 0.05]
    shots = [{"n": i + 1, "start": round(a, 2), "end": round(b, 2), "len": round(b - a, 2)}
             for i, (a, b) in enumerate(spans)]
    res = {"probe": info, "frames": len(sc), "big": big, "fine": cuts_at(sc, FINE),
           "shots": shots, "audio": audio(video) if info["audio"] else None}
    write_json(out / "cuts.json", res)
    return res
