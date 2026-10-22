"""시트 판독 — claude CLI(claude -p, stream-json)로 시트를 한 장씩 읽혀 그림별 판독을 readings.json 에 모은다.

Anthropic SDK 는 쓰지 않는다. 실행 파일은 인자(claude=) 또는 환경변수 VFR_CLAUDE, 모델은 인자(model=)
또는 VFR_MODEL 로 받는다(모델을 안 주면 --model 을 넘기지 않는다). 프롬프트는 stdin 으로 넘긴다.

stream-json 을 한 줄씩 받는다. Read 로 그림이 열리면 readings 에 칸이 생기고, 그 뒤에 나온 글은 그 그림의
판독으로 묶는다 ('[판독] 파일' 머리줄이 있으면 그 파일에, 없으면 방금 연 그림에). 다른 도구를 부르면 묶음이 끝난다.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import threading

from . import write_json
from .sheets import sheet_files

HERE = pathlib.Path(__file__).resolve().parent
ENV_BIN, ENV_MODEL = "VFR_CLAUDE", "VFR_MODEL"
TIMEOUT = 900
IMG_RE = re.compile(r"\.(jpe?g|png|webp)$", re.I)
TEXT_MAX = 4000
HEAD_RE = re.compile(r"\[판독\]\s*\**\s*([^\s*]+)")
END_MARKS = {"[판독 끝]"}


def resolve_bin(claude=None):
    name = claude or os.environ.get(ENV_BIN) or "claude"
    found = shutil.which(name)
    if not found:
        raise FileNotFoundError("claude 실행 파일을 찾지 못했다: %r — --claude 또는 환경변수 %s 로 경로를 준다"
                                % (name, ENV_BIN))
    return found


def find(readings, name):
    name = pathlib.Path(name.strip("`*:,.")).name
    for i in range(len(readings) - 1, -1, -1):
        if readings[i]["file"] == name:
            return i
    return None


class Tracker:
    """stream-json 사건을 readings 목록으로 옮긴다. 목록이 바뀔 때마다 save() 를 부른다."""

    def __init__(self, readings, save):
        self.readings, self.save = readings, save
        self.tools = {}      # tool_use_id → 연 파일 경로
        self.current = None  # 방금 열어 성공한 그림의 readings 번호
        self.result = None

    def feed(self, line):
        try:
            e = json.loads(line)
        except ValueError:
            return
        typ = e.get("type")
        if typ == "assistant":
            for c in (e.get("message") or {}).get("content") or []:
                if isinstance(c, dict):
                    self._assistant(c)
        elif typ == "user":
            for c in (e.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    self._result(c)
        elif typ == "result":
            self.result = e

    def _attach(self, text):
        heads = list(HEAD_RE.finditer(text))
        parts = []
        if heads:
            if heads[0].start() > 0 and self.current is not None:
                parts.append((self.current, text[:heads[0].start()]))
            for i, m in enumerate(heads):
                end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
                idx = find(self.readings, m.group(1))
                if idx is not None:
                    parts.append((idx, text[m.start():end]))
        elif self.current is not None:
            parts.append((self.current, text))
        changed = False
        for idx, chunk in parts:
            chunk = "\n".join(ln for ln in chunk.splitlines() if ln.strip() not in END_MARKS).strip()
            if chunk:
                r = self.readings[idx]
                r["text"] = (r["text"] + "\n" + chunk).strip()[:TEXT_MAX]
                changed = True
        if changed:
            self.save()

    def _assistant(self, c):
        if c.get("type") == "text":
            text = (c.get("text") or "").strip()
            if text:
                self._attach(text)
        elif c.get("type") == "tool_use":
            self.current = None  # 다른 도구를 부르면 앞 그림의 판독 묶음은 끝난 것
            if c.get("name") == "Read":
                self.tools[c.get("id")] = str((c.get("input") or {}).get("file_path") or "")

    def _result(self, c):
        target = self.tools.get(c.get("tool_use_id"), "")
        if not IMG_RE.search(target):
            return
        content = c.get("content")
        got = isinstance(content, list) and any(
            isinstance(x, dict) and x.get("type") == "image" for x in content)
        if got and not c.get("is_error"):
            self.readings.append({"file": pathlib.Path(target).name, "path": target, "text": ""})
            self.current = len(self.readings) - 1
            self.save()


def fill(template, **kw):
    text = (HERE / "prompts" / template).read_text(encoding="utf-8")
    for k, v in kw.items():
        text = text.replace("{{%s}}" % k, str(v))
    return text


def read_rule(sheet):
    """그 시트 한 장만 읽게 하는 허용 규칙. 절대경로 앞에 / 를 하나 더 붙인 Read(//절대경로) 형식이다."""
    return "Read(/%s)" % pathlib.Path(sheet).resolve()


def run_sheet(exe, model, cwd, prompt, readings, save, sheet, timeout=TIMEOUT):
    """claude -p 한 번을 끝까지 돌린다. 읽기는 sheet 한 장(과 작업 폴더)으로 좁힌다. 돌려주는 값: {ok, error}."""
    args = [exe, "-p", "--output-format", "stream-json", "--verbose",
            "--permission-mode", "dontAsk", "--allowedTools", read_rule(sheet)]
    if model:
        args += ["--model", model]
    tr, timed_out = Tracker(readings, save), []
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as err:
        p = subprocess.Popen(args, cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=err, text=True, encoding="utf-8", errors="replace")
        killer = threading.Timer(timeout, lambda: (timed_out.append(1), p.kill()))
        killer.start()
        try:
            try:
                p.stdin.write(prompt)
                p.stdin.close()
            except OSError:  # 프롬프트를 받기 전에 죽은 경우 — 아래에서 '결과 없음'으로 처리
                pass
            for line in p.stdout:
                if line.strip():
                    tr.feed(line)
            p.wait()
        finally:
            killer.cancel()
        err.seek(0)
        tail = err.read()[-300:]
    if not tr.result:
        why = "TIMEOUT %ds" % timeout if timed_out else "결과 없이 끝남 (exit %s)" % p.returncode
        return {"ok": False, "error": (why + " " + tail).strip()}
    if tr.result.get("is_error"):
        return {"ok": False, "error": str(tr.result.get("result"))[:500]}
    return {"ok": True, "error": None}


def read_sheets(out, cut, claude=None, model=None, timeout=TIMEOUT):
    """out/sheet*.jpg 를 한 장씩 읽혀 out/readings.json 을 쓴다. 돌려주는 값: {sheets, errors}."""
    out = pathlib.Path(out)
    exe = resolve_bin(claude)
    model = model or os.environ.get(ENV_MODEL)
    probe = cut.get("probe") or {}
    readings, errors = [], []

    def save():
        write_json(out / "readings.json", readings)

    sheets = sheet_files(out)
    for s in sheets:
        prompt = fill("read.md", sheet=s.resolve(), width=probe.get("width"), height=probe.get("height"),
                      duration=probe.get("duration"), shots=len(cut.get("shots") or []))
        r = run_sheet(exe, model, out, prompt, readings, save, s.resolve(), timeout)
        i, problem = find(readings, s.name), r["error"]
        if i is None:  # 그림을 못 연 시트도 빈칸으로 남겨 어디가 빠졌는지 보이게 한다
            readings.append({"file": s.name, "path": str(s.resolve()), "text": ""})
            i, problem = len(readings) - 1, problem or "시트를 열지 못함"
        elif not readings[i]["text"].strip():
            problem = problem or "판독 글 없음"
        if problem:
            readings[i]["error"] = problem
            errors.append("%s: %s" % (s.name, problem))
    save()
    return {"sheets": len(sheets), "errors": errors}
