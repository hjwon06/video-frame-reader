"""가짜 claude — `claude -p --output-format stream-json` 처럼 stdin 프롬프트를 받아 사건을 한 줄씩 찍는다.

FAKE_CLAUDE_MODE: ok(기본) | nohead(머리줄 없이 판독) | silent(그림만 열고 글 없음) | crash(결과 없이 종료)
FAKE_CLAUDE_LOG: 받은 인자를 JSON 으로 덧붙일 파일 경로
"""
import json
import os
import re
import sys


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def assistant(*content):
    emit({"type": "assistant", "message": {"content": list(content)}})


def main():
    prompt = sys.stdin.read()
    if os.environ.get("FAKE_CLAUDE_LOG"):
        with open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8") as f:
            f.write(json.dumps({"argv": sys.argv[1:], "prompt": prompt}, ensure_ascii=False) + "\n")
    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    m = re.search(r"\S+sheet\d+\.jpg", prompt)
    if not m:
        print("fake_claude: 프롬프트에서 시트 경로(sheet<숫자>.jpg)를 찾지 못했다", file=sys.stderr)
        sys.exit(4)
    path = m.group(0)
    name = os.path.basename(path)
    emit({"type": "system", "subtype": "init", "session_id": "fake-session", "model": "fake"})
    assistant({"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": path}})
    emit({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
          "content": [{"type": "image", "source": {"type": "base64", "data": ""}}]}]}})
    if mode == "crash":
        sys.exit(3)
    if mode != "silent":
        body = "- 0.30s: 합계 4,821.50 USD, 점유율 37.5%% (%s)" % name
        head = "" if mode == "nohead" else "[판독] %s\n" % name
        assistant({"type": "text", "text": head + body})
        assistant({"type": "text", "text": "[판독 끝]"})
    emit({"type": "result", "subtype": "success", "is_error": False, "session_id": "fake-session",
          "duration_ms": 1, "num_turns": 2, "result": "ok"})


if __name__ == "__main__":
    main()
