"""화면 글자 읽기 (OCR) — 모델 판독과 숫자를 맞춰 보기 위한 글자 목록을 뽑는다.

컷마다 가운데 1장 + 작은 변화 직후를 뽑아(최대 20장) tesseract 로 두 번 읽는다.
그대로 한 번(화면 UI · 어두운 글자), 반전해서 한 번(색 박스 위 흰 자막).
모델을 한 번만 올리도록 목록 파일로 한꺼번에 넘긴다.
"""
import os
import re
import subprocess
import tempfile

from . import write_json

KEEP = re.compile(r"[가-힣]{2,}|[0-9][0-9,.%$]{2,}|[A-Za-z]{4,}")


def pick_times(cut, cap=20):
    dur = cut["probe"]["duration"]
    ts = [round((s["start"] + s["end"]) / 2, 2) for s in cut["shots"]]
    for f, _ in cut["fine"]:
        c = round(f + 0.3, 2)
        if c < dur - 0.1 and all(abs(c - x) > 1.0 for x in ts):
            ts.append(c)
    ts = sorted(ts)
    if len(ts) > cap:
        ts = [ts[int(i * len(ts) / cap)] for i in range(cap)]
    return ts


def _frames(video, ts, tmp):
    """시각마다 [원본, 반전] 그림 경로 두 개를 차례로 돌려준다."""
    paths = []
    for i, t in enumerate(ts):
        a, b = os.path.join(tmp, "f%02d.png" % i), os.path.join(tmp, "n%02d.png" % i)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1", a],
                       check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a, "-vf",
                        "format=gray,negate,eq=contrast=1.6", b], check=True)
        paths += [a, b]
    return paths


def _clean(page):
    out = []
    for ln in page.splitlines():
        ln = re.sub(r"\s+", " ", ln).strip()
        if KEEP.search(ln) and ln not in out:
            out.append(ln)
    return out


def read(video, cut, lang="kor+eng"):
    ts = pick_times(cut)
    with tempfile.TemporaryDirectory() as tmp:
        paths = _frames(video, ts, tmp)
        lst = os.path.join(tmp, "list.txt")
        with open(lst, "w", encoding="utf-8") as f:
            f.write("\n".join(paths) + "\n")
        r = subprocess.run(["tesseract", lst, "stdout", "-l", lang, "--psm", "11"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=1800)
    pages = r.stdout.split("\f")
    rows = []
    for i, t in enumerate(ts):
        lines = []
        for page in pages[2 * i:2 * i + 2]:  # 시각마다 원본 · 반전 두 쪽
            lines += [ln for ln in _clean(page) if ln not in lines]
        rows.append({"t": t, "lines": lines})
    return {"lang": lang, "frames": len(ts), "pages": len(pages), "rows": rows}


def main(video, cut, out, lang="kor+eng"):
    """out/ocr.json 을 쓴다. 실패해도 error 를 담아 파일은 남긴다(실패와 '아직'을 구분하려고)."""
    try:
        res = read(video, cut, lang)
    except Exception as e:  # noqa: BLE001 — 실패도 결과 파일에 남긴다
        res = {"error": repr(e)[:500], "rows": []}
    write_json(out / "ocr.json", res)
    return res
