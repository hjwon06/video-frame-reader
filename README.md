# video-frame-reader

영상 파일 하나를 받아 **장면 경계 · 화면 시트 · 화면 글자(OCR) · 음성 받아쓰기 · 모델 판독**을 뽑고,
모델이 그림에서 읽은 **숫자를 OCR · 받아쓰기와 대조**해 사람이 다시 볼 곳을 가리키는 작은 파이썬 패키지다.
모델 판독은 Claude Code CLI(`claude -p`)로만 한다. Anthropic SDK 를 직접 부르지 않는다.

## 흐름

```
전처리                         추론                              후처리
영상 ─ cuts   ─ cuts.json  ┐
     ─ sheets ─ sheet1.jpg … ├─ reader (claude -p, 시트 1장 = 1회) ─ readings.json ─ checks ─ checks.json
     ─ ocr    ─ ocr.json   ┤                                              ▲
     ─ asr    ─ asr.json   ┘──────────── 대조 말뭉치 ──────────────────────┘
```

1. **전처리** — `cuts`: ffmpeg 한 번 디코딩으로 프레임마다 장면 점수를 받아 임계 0.20(큰 컷) / 0.10(작은 변화)로 자른다.
   0.25초 안에 몰린 변화는 하나로 센다. `sheets`: 컷마다 첫 프레임, 일정 간격, 작은 변화 직후의 프레임을
   4열 · 최대 12칸 시트에 붙이고 칸마다 시각 라벨을 단다. `ocr`: 컷 가운데 프레임 등 최대 20장을 tesseract 로
   읽는다(원본 + 반전). `asr`: ffmpeg 가 만든 16kHz 모노 배열을 faster-whisper 에 넘긴다.
2. **추론** — `reader`: 시트를 한 장씩 `claude -p --output-format stream-json` 으로 읽힌다. 그림이 열린 뒤 나온 글을
   그 그림의 판독으로 묶어 `readings.json` 에 모은다.
3. **후처리** — `checks`: 판독 글의 숫자를 OCR · 받아쓰기 숫자와 맞춰 네 갈래(`ocr` / `part` / `asr` / `none`)로 표시한다.

## 설치

- Python 3, `ffmpeg` · `ffprobe`
- OCR: `tesseract` 와 `kor`, `eng` 언어 데이터 (예: `apt install tesseract-ocr tesseract-ocr-kor`)
- 모델 판독: `claude` (Claude Code CLI) 설치와 로그인
- 파이썬 패키지: `pip install -r requirements.txt`

`faster-whisper` 는 처음 실행할 때 모델을 내려받는다. 받아쓰기가 필요 없으면 `--no-asr`.

## 실행

```
python -m vfr run sample.mp4 --out out/
python -m vfr run sample.mp4 --out out/ --no-llm            # 모델 없이 컷 · 시트 · OCR · 받아쓰기만
python -m vfr run sample.mp4 --out out/ --no-asr --no-ocr   # 컷 · 시트 · 판독 · 대조
python -m vfr run sample.mp4 --out out/ --claude /path/to/claude --model <모델 이름>
```

| 옵션 | 뜻 |
|---|---|
| `--no-llm` / `--no-asr` / `--no-ocr` | 해당 단계를 건너뛴다 |
| `--claude` | claude 실행 파일. 없으면 환경변수 `VFR_CLAUDE`, 그것도 없으면 PATH 의 `claude` |
| `--model` | 모델 이름. 없으면 환경변수 `VFR_MODEL`, 그것도 없으면 `--model` 을 넘기지 않는다 |
| `--asr-model` | faster-whisper 모델 이름 (기본 `small`) |
| `--ocr-lang` | tesseract 언어 (기본 `kor+eng`) |

한 단계가 실패해도 나머지는 계속 돌고, 끝에 실패 목록을 찍고 종료 코드 1 을 돌려준다.
컷 · 시트 단계(ffmpeg)가 실패하면 바로 종료 코드 2.

## 출력 파일 (`--out` 폴더)

| 파일 | 내용 |
|---|---|
| `cuts.json` | 영상 정보, 프레임 수, 큰 컷(0.20) · 작은 변화(0.10) 시각과 점수, 컷 구간(`shots`), 소리 측정 |
| `sheet1.jpg` … | 화면 시트. 한 장 12칸까지, 최대 3장 |
| `ocr.json` | 시각별 읽은 글자 줄. 실패하면 `error` 와 빈 `rows` |
| `asr.json` | 문장별 시작 · 끝 · 글 · 신뢰 지표. 실패하면 `error` 와 빈 `lines` |
| `readings.json` | 시트(그림)마다 `{file, path, text}`. 읽지 못한 시트는 `error` 가 붙는다 |
| `checks.json` | 판독 속 숫자의 대조 결과. `by_file` 에 숫자별 `hit`, `summary` 에 갈래별 개수 |

`checks.json` 은 `readings.json` 이 있을 때만 만든다(`--no-llm` 이면 만들지 않는다).

## 설계 이유

- **반전 OCR** — 같은 프레임을 그대로 한 번, 흑백 반전 + 대비를 올려 한 번 더 읽는다. 색 박스 위의 흰 자막은
  그대로 읽으면 놓치는 경우가 있고, 반전하면 어두운 글자가 되어 잡히는 경우가 있어서다. 두 결과의 줄을 합친다.
  어느 쪽이 얼마나 더 잘 읽는지는 이 저장소에서 따로 재지 않았다.
- **대조는 판정이 아니라 힌트** — OCR 은 오탈자가 많고 색 위의 글자를 놓치므로 'OCR 에 없음'이 곧 '틀림'이 아니다.
  반대로 모델이 읽은 숫자가 OCR 에 있어도 맞다는 보증은 아니다. 그래서 `none`(어디에도 없음)을 '사람이 그림을 직접
  볼 곳'으로 가리키는 데만 쓴다.
  - `ocr` — OCR 에 같은 숫자가 있다
  - `part` — OCR 에 정수 부분만 같은 숫자가 있다 (소수점 아래가 다르거나 없음)
  - `asr` — OCR 에는 없고 받아쓰기에 있다
  - `none` — 어디에도 없다
  - 시각 라벨(`0.30s`), 한 자리 숫자, 날짜 · 시각, 단위 없는 두 자리 숫자는 대조에서 뺀다.
- **시트 한 장 = claude 한 번** — 한 호출이 길어져 중간에 끊겨도 앞 시트의 판독은 남고, 어느 시트가 비었는지 알 수 있다.
- **LLM 은 claude CLI 로만** — 프롬프트는 stdin 으로 넘기고, 허용 도구는 `Read` 하나이고, 모델은 그 시트 파일과 `--out` 폴더 안만 읽을 수 있다.

## 시험

```
pytest
```

ffmpeg 로 만든 합성 영상(장면 3개 · 숫자 글자)과 가짜 claude 실행 파일(`tests/fake_claude.py`)을 쓴다.
ffmpeg · tesseract · faster-whisper 가 없으면 해당 시험은 건너뛴다. 모델 내려받기와 네트워크를 쓰는 시험은 없다.
정확도 · 속도는 재지 않았다.
