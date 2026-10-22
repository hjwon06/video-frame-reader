"""python -m vfr run <영상> --out <폴더> [--no-llm] [--no-asr] [--no-ocr]

흐름: 컷 측정 → 시트 → (OCR) → (받아쓰기) → (모델 판독) → 숫자 대조.
각 단계의 결과는 --out 폴더에 파일로 남는다. 한 단계가 실패해도 다음 단계는 계속하고, 끝에 종료 코드 1 로 알린다.
"""
import argparse
import pathlib
import subprocess
import sys

from . import asr, checks, cuts, ocr, reader, sheets


def build_parser():
    p = argparse.ArgumentParser(prog="vfr", description="영상 프레임 판독 · 숫자 대조")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="영상 하나를 풀어 --out 폴더에 결과를 쓴다")
    r.add_argument("video", help="로컬 영상 파일")
    r.add_argument("--out", required=True, help="결과 폴더(없으면 만든다)")
    r.add_argument("--no-llm", action="store_true", help="모델 판독(claude CLI)을 건너뛴다")
    r.add_argument("--no-asr", action="store_true", help="음성 받아쓰기를 건너뛴다")
    r.add_argument("--no-ocr", action="store_true", help="화면 글자 읽기를 건너뛴다")
    r.add_argument("--claude", help="claude 실행 파일 경로 (기본: 환경변수 VFR_CLAUDE, 없으면 PATH 의 claude)")
    r.add_argument("--model", help="claude 모델 (기본: 환경변수 VFR_MODEL, 없으면 CLI 기본값)")
    r.add_argument("--asr-model", default="small", help="faster-whisper 모델 이름 (기본 small)")
    r.add_argument("--ocr-lang", default="kor+eng", help="tesseract 언어 (기본 kor+eng)")
    return p


def run(args):
    video, out = pathlib.Path(args.video), pathlib.Path(args.out)
    if not video.is_file():
        print("영상 파일이 없다: %s" % video, file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    try:
        cut = cuts.measure(video, out)
        paths = sheets.make(video, cut, out)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
        print("컷 · 시트 단계 실패 (ffmpeg / ffprobe 설치와 영상 파일을 확인): %s" % e, file=sys.stderr)
        return 2
    print("컷 %d개 · 시트 %d장" % (len(cut["shots"]), len(paths)))
    errors = []
    if not args.no_ocr:
        res = ocr.main(video, cut, out, args.ocr_lang)
        print("ocr: %s" % (res.get("error") or "%d장" % len(res["rows"])))
        if res.get("error"):
            errors.append("ocr: " + res["error"])
    if not args.no_asr:
        res = asr.main(video, out, args.asr_model)
        print("asr: %s" % (res.get("error") or "%d문장" % len(res["lines"])))
        if res.get("error"):
            errors.append("asr: " + res["error"])
    if not args.no_llm:
        try:
            res = reader.read_sheets(out, cut, args.claude, args.model)
            print("판독: 시트 %d장 · 실패 %d" % (res["sheets"], len(res["errors"])))
            errors += ["reader " + e for e in res["errors"]]
        except Exception as e:  # noqa: BLE001 — 판독이 죽어도 앞 단계 결과는 남긴다
            print("판독 실패: %s" % e, file=sys.stderr)
            errors.append("reader: %s" % e)
    if (out / "readings.json").exists():
        total = checks.run(out)["summary"]
        print("대조: " + " ".join("%s=%d" % kv for kv in total.items()))
    for e in errors:
        print("!! " + e, file=sys.stderr)
    return 1 if errors else 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    return run(args)
