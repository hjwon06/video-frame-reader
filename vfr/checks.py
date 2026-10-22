"""판독 대조 — 모델이 그림에서 읽은 숫자를 화면 글자(OCR) · 받아쓰기와 맞춰 본다.

판정이 아니라 힌트다. OCR 은 색 박스 위 글자를 놓치고 오탈자가 많아서 'OCR 에 없음' 이 곧 '틀림' 은 아니다.
사람이 그림을 다시 봐야 할 곳을 가리키는 용도다:
  ocr   OCR 에 같은 숫자가 있다
  part  OCR 에 정수 부분만 같은 숫자가 있다 (소수점 아래가 다르거나 없음)
  asr   OCR 에는 없고 받아쓰기에 있다
  none  어디에도 없다 → 사람이 그림을 직접 볼 곳
"""
import datetime
import re

from . import read_json, write_json

NUM_RE = re.compile(r"[$₩]?[+-]?\d[\d,]*(?:\.\d+)?%?")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\b\d{1,2}:\d{2}(?::\d{2})?\b")


def tokens(text):
    """(원래 표기, 숫자만) 목록. 시각 라벨(0.30s)과 한 자리 숫자는 뺀다."""
    out = []
    for m in NUM_RE.finditer(text or ""):
        if text[m.end():m.end() + 1] == "s":  # 시트 그림의 시각 라벨
            continue
        tok = m.group(0)
        n = re.sub(r"[^\d.]", "", tok).strip(".")
        digits = sum(ch.isdigit() for ch in n)
        if digits < 2 or (digits == 2 and not re.search(r"[$₩%.,]", tok)):  # 15분 · MA20 같은 잡음
            continue
        out.append((tok, n))
    return out


def _corpus(d):
    ocr = read_json(d / "ocr.json", {}) or {}
    asr = read_json(d / "asr.json", {}) or {}
    o, a = set(), set()
    for row in ocr.get("rows") or []:
        for line in row.get("lines") or []:
            o.update(n for _, n in tokens(line))
    for line in asr.get("lines") or []:
        a.update(n for _, n in tokens(line.get("text") or ""))
    return o, a, bool(ocr.get("rows")), bool(asr.get("lines"))


def _body(text):
    # "[판독] sheet1.jpg" 같은 머리줄과 날짜 · 시각의 숫자는 대조 대상이 아니다
    body = "\n".join(l for l in (text or "").splitlines() if not l.strip().startswith("["))
    return DATE_RE.sub(" ", body)


def run(out):
    """out/readings.json 의 숫자를 out/ocr.json · asr.json 과 대조해 out/checks.json 을 쓴다."""
    o, a, has_o, has_a = _corpus(out)
    o_int = {x.split(".")[0] for x in o}
    readings = read_json(out / "readings.json", []) or []
    by_file, total = {}, {"tokens": 0, "ocr": 0, "part": 0, "asr": 0, "none": 0}
    for r in readings:
        items = by_file.setdefault(r["file"], [])
        seen = {i["n"] for i in items}
        for tok, n in tokens(_body(r.get("text"))):
            if n in seen:
                continue
            seen.add(n)
            if n in o:
                hit = "ocr"
            elif n.split(".")[0] in o_int:
                hit = "part"
            elif n in a:
                hit = "asr"
            else:
                hit = "none"
            items.append({"tok": tok, "n": n, "hit": hit})
            total["tokens"] += 1
            total[hit] += 1
    res = {"at": datetime.datetime.now().isoformat(timespec="seconds"),
           "has_ocr": has_o, "has_asr": has_a, "summary": total, "by_file": by_file}
    write_json(out / "checks.json", res)
    return res
