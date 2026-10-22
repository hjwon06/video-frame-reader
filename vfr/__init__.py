"""video-frame-reader — 영상 하나를 컷 · 시트 · 화면 글자 · 음성 · 모델 판독으로 풀고 숫자를 대조한다."""
import json
import os

__version__ = "0.1.0"


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    """임시 파일에 쓰고 바꿔치기한다 — 읽는 쪽이 반쯤 쓰인 파일을 보지 않는다."""
    path = os.fspath(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
