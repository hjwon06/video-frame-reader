"""공용 준비물 — ffmpeg lavfi 합성 영상(장면 3개 · 숫자 글자 · 사인파 소리)과 가짜 claude 실행 파일."""
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/Library/Fonts/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf")
TEXT = "TOTAL 4821"


def need(tool):
    if not shutil.which(tool):
        pytest.skip("%s 가 PATH 에 없다" % tool)


@pytest.fixture(scope="session")
def video(tmp_path_factory):
    """흰 · 검정 · 노랑 장면 1초씩(경계 1.0초 · 2.0초). 글자 박스는 세 장면에 계속 떠 있다."""
    need("ffmpeg")
    need("ffprobe")
    font = next((f for f in FONTS if os.path.exists(f)), None)
    if not font:
        pytest.skip("drawtext 에 쓸 글꼴이 없다")
    filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    if "drawtext" not in filters:
        pytest.skip("ffmpeg 에 drawtext 필터가 없다")
    path = tmp_path_factory.mktemp("media") / "synthetic.mp4"
    src = ["-f", "lavfi", "-i"]
    cmd = ["ffmpeg", "-v", "error", "-y",
           *src, "color=c=white:s=640x360:r=25:d=1", *src, "color=c=black:s=640x360:r=25:d=1",
           *src, "color=c=yellow:s=640x360:r=25:d=1", *src, "sine=frequency=440:duration=3",
           "-filter_complex",
           "[0:v][1:v][2:v]concat=n=3:v=1:a=0,drawtext=fontfile=%s:text='%s':fontsize=72:"
           "fontcolor=black:box=1:boxcolor=white:boxborderw=14:x=(w-text_w)/2:y=(h-text_h)/2[v]"
           % (font, TEXT),
           "-map", "[v]", "-map", "3:a", "-c:v", "mpeg4", "-q:v", "2", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-shortest", str(path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]
    return path


@pytest.fixture
def fake_claude(tmp_path):
    """tests/fake_claude.py 를 실행 파일처럼 부를 수 있게 감싼 스크립트 경로(실행 권한은 여기서 준다)."""
    wrapper = tmp_path / "fake-claude"
    wrapper.write_text("#!%s\nimport runpy\nrunpy.run_path(%r, run_name='__main__')\n"
                       % (sys.executable, str(ROOT / "tests" / "fake_claude.py")), encoding="utf-8")
    wrapper.chmod(0o755)
    return str(wrapper)
