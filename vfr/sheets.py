"""화면 시트 — 정한 시각의 프레임을 한 장(4열)에 붙인다. 한 장에 최대 12칸, 칸마다 왼쪽 위에 시각 라벨.

  sheet_times(shots, fine, dur)  시트에 넣을 시각을 12개씩 묶어 돌려준다
  make(video, cut, out)          out/sheet1.jpg … 를 만든다
"""
import io
import pathlib
import re
import subprocess

from PIL import Image, ImageDraw, ImageFont

FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/Library/Fonts/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf")
COLS, W, GAP = 4, 360, 6
SHEET_RE = re.compile(r"^sheet(\d+)\.jpg$")


def _font(size):
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def sheet_times(shots, fine, dur, cap=36):
    """판독용 시트 시각. 컷마다 들어가자마자 1장 + 일정 간격마다 1장, 작은 변화 직후 1장. 12장씩 묶는다.
    간격은 2.5초가 기본이지만 짧은 영상은 최소 12칸이 되게 줄인다(0.45초까지) — 간격이 길면
    짧은 화면 하나를 통째로 놓치기 때문이다."""
    step = min(2.5, max(0.45, dur / 12)) if dur else 2.5
    ts = []
    for s in shots:
        t = s["start"] + 0.3
        while t < s["end"] - 0.15:
            ts.append(round(t, 2))
            t += step
    for f, _ in fine:
        c = round(f + 0.3, 2)
        if c < dur - 0.1 and all(abs(c - x) > 0.8 for x in ts):
            ts.append(c)
    ts = sorted(set(ts))
    if len(ts) > cap:
        ts = [ts[int(i * len(ts) / cap)] for i in range(cap)]
    return [ts[i:i + 12] for i in range(0, len(ts), 12)]


def _frame(video, t, width=None):
    vf = ["-vf", "scale=%d:-2" % width] if width else []
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % t, "-i", str(video), "-frames:v", "1",
                        *vf, "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, timeout=60)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("프레임 추출 실패 %.2f초: %s" % (t, r.stderr.decode(errors="replace")[-200:]))
    return Image.open(io.BytesIO(r.stdout)).convert("RGB")


def _label(img, x, y, text, font):
    d = ImageDraw.Draw(img)
    left, top, right, bottom = d.textbbox((0, 0), text, font=font)
    d.rectangle([x, y, x + (right - left) + 12, y + (bottom - top) + 10], fill=(0, 0, 0))
    d.text((x + 6 - left, y + 5 - top), text, fill=(255, 255, 255), font=font)


def sheet(video, times, out):
    ims = [_frame(video, t, W) for t in times]
    h = ims[0].height
    rows = (len(ims) + COLS - 1) // COLS
    canvas = Image.new("RGB", (COLS * W + (COLS + 1) * GAP, rows * h + (rows + 1) * GAP), "white")
    font = _font(20)
    for i, (t, im) in enumerate(zip(times, ims)):
        x, y = GAP + (i % COLS) * (W + GAP), GAP + (i // COLS) * (h + GAP)
        canvas.paste(im, (x, y))
        _label(canvas, x + 4, y + 4, "%.2fs" % t, font)
    canvas.save(out, quality=88)
    return out


def sheet_files(out):
    """out 안의 sheet<숫자>.jpg 를 숫자 순서로(sheet2 → sheet10) 돌려준다."""
    found = [(int(m.group(1)), p) for p in pathlib.Path(out).glob("sheet*.jpg")
             for m in [SHEET_RE.match(p.name)] if m]
    return [p for _, p in sorted(found)]


def make(video, cut, out):
    """cut(cuts.json 내용)의 시각대로 out/sheet1.jpg … 를 만들고 경로 목록을 돌려준다."""
    groups = sheet_times(cut["shots"], cut["fine"], cut["probe"]["duration"])
    for old in sheet_files(out):
        old.unlink()
    return [str(sheet(video, g, out / ("sheet%d.jpg" % (i + 1)))) for i, g in enumerate(groups)]
