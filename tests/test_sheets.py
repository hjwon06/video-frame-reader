from PIL import Image

from vfr import cuts, sheets


def test_sheet_times_groups_of_twelve():
    shots = [{"start": 0.0, "end": 60.0}]
    groups = sheets.sheet_times(shots, [], 60.0)
    assert [len(g) for g in groups] == [12, 12]  # 2.5초 간격 24칸
    assert groups[0][0] == 0.3


def test_sheet_times_cap_and_short_video_step():
    assert sum(len(g) for g in sheets.sheet_times([{"start": 0.0, "end": 300.0}], [], 300.0)) == 36
    # 3초 영상은 간격이 0.45초로 줄어 컷마다 2칸씩 잡힌다
    shots = [{"start": 0, "end": 1}, {"start": 1, "end": 2}, {"start": 2, "end": 3}]
    assert sheets.sheet_times(shots, [], 3.0) == [[0.3, 0.75, 1.3, 1.75, 2.3, 2.75]]


def test_fine_cut_adds_a_frame_unless_within_0_8s_of_existing():
    shots = [{"start": 0.0, "end": 60.0}]  # 기본 칸: 0.3, 2.8, 5.3 …
    base = sheets.sheet_times(shots, [], 60.0)
    far = sheets.sheet_times(shots, [[4.0, 0.12]], 60.0)  # 4.3 은 2.8 · 5.3 에서 1.0 이상
    near = sheets.sheet_times(shots, [[3.0, 0.12]], 60.0)  # 3.3 은 2.8 에서 0.5
    assert 4.3 in far[0] and 4.3 not in base[0]
    assert near == base


def test_make_writes_four_column_sheet_in_time_order(video, tmp_path):
    cut = cuts.measure(video, tmp_path)
    paths = sheets.make(video, cut, tmp_path)
    assert [p.rsplit("/", 1)[-1] for p in paths] == ["sheet1.jpg"]
    im = Image.open(paths[0]).convert("RGB")
    assert im.width == sheets.COLS * sheets.W + (sheets.COLS + 1) * sheets.GAP
    h = (im.height - 3 * sheets.GAP) // 2  # 6칸 = 2행

    def corner(i):  # 칸의 왼쪽 아래 — 글자 박스(가운데)와 시각 라벨(왼쪽 위)을 피한다
        x = sheets.GAP + (i % sheets.COLS) * (sheets.W + sheets.GAP) + 20
        y = sheets.GAP + (i // sheets.COLS) * (h + sheets.GAP) + h - 15
        return im.getpixel((x, y))
    assert sum(corner(0)) > 700            # 0.30s 흰 장면
    assert sum(corner(2)) < 60             # 1.30s 검정 장면
    r, g, b = corner(4)                    # 2.30s 노랑 장면
    assert r > 200 and g > 200 and b < 100
