"""
duet_worker.py — 合拍视频批量合成：后端（纯 ffmpeg 逻辑，不依赖 Qt）

功能：
  * ffmpeg / ffprobe 路径解析
  * 视频时长 / 尺寸 / 音轨探测
  * 第一步：时间线对齐（人物视频变速 + 循环 + 尾部裁剪 → 缓存视频）
  * 抽取单帧（用于预览）
  * 模板几何计算（上下画框 + 等宽/等高填充 + 偏移）
  * 构建最终渲染命令
"""
import os
import sys
import math
import json
import subprocess

REF_W = 1080
REF_H = 1920
CANVAS_W = 1080
CANVAS_H = 1920

ASPECT_RATIOS = [
    ("9:16", "9:16 竖屏 (1080×1920)", 1080, 1920),
    ("3:4",  "3:4 竖屏 (1080×1440)",  1080, 1440),
    ("1:1",  "1:1 方屏 (1080×1080)",  1080, 1080),
    ("4:3",  "4:3 横屏 (1440×1080)",  1440, 1080),
    ("16:9", "16:9 横屏 (1920×1080)", 1920, 1080),
]

ASPECT_RESOLUTIONS = {
    "9:16": [
        ("1080 × 1920（1080P 推荐）", 1080, 1920),
        ("720 × 1280（720P 快速）",   720,  1280),
        ("1440 × 2560（2K 高清）",    1440, 2560),
        ("2160 × 3840（4K 超清）",    2160, 3840),
    ],
    "3:4": [
        ("1080 × 1440（1080P 推荐）", 1080, 1440),
        ("720 × 960（720P 快速）",    720,  960),
        ("1440 × 1920（2K 高清）",    1440, 1920),
        ("2160 × 2880（4K 超清）",    2160, 2880),
    ],
    "1:1": [
        ("1080 × 1080（1080P 推荐）", 1080, 1080),
        ("720 × 720（720P 快速）",    720,  720),
        ("1440 × 1440（2K 高清）",    1440, 1440),
        ("2160 × 2160（4K 超清）",    2160, 2160),
    ],
    "4:3": [
        ("1440 × 1080（1080P 推荐）", 1440, 1080),
        ("960 × 720（720P 快速）",    960,  720),
        ("1920 × 1440（2K 高清）",    1920, 1440),
        ("2880 × 2160（4K 超清）",    2880, 2160),
    ],
    "16:9": [
        ("1920 × 1080（1080P 推荐）", 1920, 1080),
        ("1280 × 720（720P 快速）",   1280, 720),
        ("2560 × 1440（2K 高清）",    2560, 1440),
        ("3840 × 2160（4K 超清）",    3840, 2160),
    ],
}

_ASPECT_MAP = {k: (w, h) for k, _, w, h in ASPECT_RATIOS}
_CURRENT_ASPECT = "9:16"


def set_canvas_aspect(aspect: str) -> tuple:
    """设置全局画布比例（'9:16' / '3:4' / '1:1' / '4:3' / '16:9'），返回 (CANVAS_W, CANVAS_H)。"""
    global _CURRENT_ASPECT, CANVAS_W, CANVAS_H
    if aspect not in _ASPECT_MAP:
        aspect = "9:16"
    _CURRENT_ASPECT = aspect
    CANVAS_W, CANVAS_H = _ASPECT_MAP[aspect]
    return CANVAS_W, CANVAS_H


def get_canvas_aspect(tpl: dict = None) -> str:
    """获取当前画布比例；若 tpl 指定了有效 aspect 则优先返回 tpl['aspect']。"""
    if isinstance(tpl, dict):
        a = tpl.get("aspect")
        if a in _ASPECT_MAP:
            return a
    return _CURRENT_ASPECT


def get_canvas_size(tpl: dict = None) -> tuple:
    """返回画布基准像素尺寸 (cw, ch)。"""
    return _ASPECT_MAP.get(get_canvas_aspect(tpl), (1080, 1920))

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


# ── 路径 ──────────────────────────────────────────────────────────────────────

def get_install_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_data_dir() -> str:
    d = os.path.join(get_install_root(), "duet_data")
    os.makedirs(d, exist_ok=True)
    return d


_CACHE_ROOT = ""
CACHE_TAG = "合拍视频批量合成"


def set_cache_root(path: str):
    """设置用户自定义的缓存根目录（空字符串 = 默认：软件目录/duet_cache）。"""
    global _CACHE_ROOT
    _CACHE_ROOT = path or ""


def get_cache_dir() -> str:
    d = _CACHE_ROOT or os.path.join(get_install_root(), "duet_cache")
    os.makedirs(d, exist_ok=True)
    return d


def new_task_cache_dir() -> str:
    """
    每次任务新建一个缓存文件夹：<缓存根目录>/2026-10-06_合拍视频批量合成
    同一天第二次任务：..._02，第三次：..._03 …… 避免命名冲突。
    """
    import datetime
    root = get_cache_dir()
    base = f"{datetime.date.today():%Y-%m-%d}_{CACHE_TAG}"
    name, k = base, 2
    while os.path.exists(os.path.join(root, name)):
        name = f"{base}_{k:02d}"
        k += 1
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    return d


def list_task_cache_dirs() -> list:
    """列出缓存根目录下由本工具创建的任务缓存文件夹（只清理这些，避免误删用户文件）。"""
    root = get_cache_dir()
    out = []
    for n in os.listdir(root):
        p = os.path.join(root, n)
        if os.path.isdir(p) and (CACHE_TAG in n or n in ("aligned", "cards", "_selftest")):
            out.append(p)
    return out


def get_card_lib_dir() -> str:
    """图片卡片 / 字体的永久存储目录（保存预设时复制到这里）。"""
    d = os.path.join(get_install_root(), "duet_card_library")
    os.makedirs(d, exist_ok=True)
    return d


def get_ffmpeg() -> str:
    p = os.path.join(get_install_root(), "ffmpeg", "ffmpeg.exe")
    return p if os.path.isfile(p) else "ffmpeg"


def get_ffprobe() -> str:
    p = os.path.join(get_install_root(), "ffmpeg", "ffprobe.exe")
    return p if os.path.isfile(p) else "ffprobe"


# ── 探测 ──────────────────────────────────────────────────────────────────────

def probe_info(path: str) -> dict:
    """返回 {'duration': float, 'width': int, 'height': int, 'has_audio': bool}"""
    cmd = [get_ffprobe(), "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", path]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                         errors="ignore", creationflags=_NO_WINDOW)
    info = {"duration": 0.0, "width": 0, "height": 0, "has_audio": False}
    try:
        data = json.loads(res.stdout or "{}")
    except Exception:
        return info
    try:
        info["duration"] = float(data.get("format", {}).get("duration", 0) or 0)
    except Exception:
        pass
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and not info["width"]:
            w, h = int(s.get("width", 0)), int(s.get("height", 0))
            # 处理手机竖拍视频的旋转元数据
            rot = 0
            try:
                rot = int(s.get("tags", {}).get("rotate", 0))
            except Exception:
                pass
            for sd in s.get("side_data_list", []) or []:
                if "rotation" in sd:
                    try:
                        rot = int(sd["rotation"])
                    except Exception:
                        pass
            if abs(rot) % 180 == 90:
                w, h = h, w
            info["width"], info["height"] = w, h
        elif s.get("codec_type") == "audio":
            info["has_audio"] = True
    return info


# ── 第一步：时间线对齐 ─────────────────────────────────────────────────────────

def _atempo_chain(speed: float) -> str:
    """atempo 单个滤镜只支持 0.5~2.0，超出范围时串联。"""
    parts = []
    s = speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


def align_person_video(person_vid: str, viral_vid: str, out_path: str,
                       mute_person: bool = True, speed: float = 1.0) -> dict:
    """
    以主视频时长为基准，将人物视频变速后循环至等长，并裁掉多余尾部。
    返回 {'cache': out_path, 'duration': viral_duration}
    """
    v_info = probe_info(viral_vid)
    p_info = probe_info(person_vid)
    viral_dur = v_info["duration"]
    person_dur = p_info["duration"]
    if viral_dur <= 0:
        raise ValueError(f"无法读取主视频时长：{os.path.basename(viral_vid)}")
    if person_dur <= 0:
        raise ValueError(f"无法读取人物视频时长：{os.path.basename(person_vid)}")

    speed = max(0.1, float(speed))
    new_dur = person_dur / speed
    loops = max(1, math.ceil(viral_dur / new_dur))

    cmd = [get_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
           "-stream_loop", str(loops - 1), "-i", person_vid]

    vf = f"setpts=PTS/{speed:.4f}" if abs(speed - 1.0) > 1e-3 else "null"
    keep_audio = (not mute_person) and p_info["has_audio"]
    if keep_audio:
        af = _atempo_chain(speed) if abs(speed - 1.0) > 1e-3 else "anull"
        cmd += ["-filter_complex", f"[0:v]{vf}[v];[0:a]{af}[a]",
                "-map", "[v]", "-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-vf", vf, "-an"]

    cmd += ["-t", f"{viral_dur:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", os.path.abspath(out_path)]

    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                         errors="ignore", creationflags=_NO_WINDOW)
    if res.returncode != 0 or not os.path.isfile(out_path):
        raise RuntimeError(f"对齐失败：{os.path.basename(person_vid)}\n{res.stderr[-800:]}")
    return {"cache": out_path, "duration": viral_dur}


# ── 抽帧 ──────────────────────────────────────────────────────────────────────

def extract_frame_png(path: str, t: float = 0.0) -> bytes:
    """抽取 t 秒处的一帧，返回 PNG 字节（失败返回 b''）。"""
    cmd = [get_ffmpeg(), "-hide_banner", "-loglevel", "error",
           "-ss", f"{max(0.0, t):.3f}", "-i", path,
           "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"]
    try:
        res = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW, timeout=30)
        if res.returncode == 0 and res.stdout:
            return res.stdout
        # 超出时长时优先按原视频时长取模循环，再退回第 0 秒
        if t > 0:
            dur = probe_info(path).get("duration", 0.0)
            if dur > 0.1 and t >= dur:
                t_mod = t % dur
                res2 = subprocess.run(
                    [get_ffmpeg(), "-hide_banner", "-loglevel", "error",
                     "-ss", f"{max(0.0, t_mod):.3f}", "-i", path,
                     "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                    capture_output=True, creationflags=_NO_WINDOW, timeout=30
                )
                if res2.returncode == 0 and res2.stdout:
                    return res2.stdout
            return extract_frame_png(path, 0.0)
    except Exception:
        pass
    return b""


# ── 模板几何 ──────────────────────────────────────────────────────────────────

def default_template(name: str = "默认上下分屏") -> dict:
    return {
        "name": name,
        "order": "person_top",          # person_top / viral_top
        "split": 0.5,                   # 分割线位置（占画布高度比例）
        "top":    {"fill": "width", "ox": 0, "oy": 0},
        "bottom": {"fill": "width", "ox": 0, "oy": 0},
    }


# ── 多格 / 画中画 版式 ─────────────────────────────────────────────────────────
# 模板新格式：{"name": ..., "cells": [cell, ...]}
# cell = {"src": 视频来源, "x","y","w","h": 占画布比例(0~1), "fill": 填充规则,
#         "ox","oy": 偏移像素, "pip": 是否画中画小窗, "border": 白色边框像素}
SOURCES = ["viral", "person"] + [f"person{i}" for i in range(2, 13)]
SRC_LABELS = {
    "viral": "主视频",
    "person": "人物视频1",
    **{f"person{i}": f"人物视频{i}" for i in range(2, 13)},
}
FILL_MODES = [("cover", "铺满格子（超出裁切）"), ("width", "等宽对齐（宽=格子宽）"),
              ("height", "等高对齐（高=格子高）"), ("contain", "完整显示（留黑边）")]
ROTATE_MODES = [
    (0,   "不旋转 (0°)"),
    (90,  "顺时针 90° (向右转)"),
    (180, "旋转 180° (上下颠倒)"),
    (270, "逆时针 90° (向左转)"),
]


def cell_rotation(cell: dict = None, adj: dict = None) -> int:
    """计算格子内视频的总顺时针旋转角度（0 / 90 / 180 / 270）：模板格子旋转 + 任务单项微调旋转。"""
    r1 = int((cell or {}).get("rotate", 0) or 0)
    r2 = int((adj or {}).get("rotate", 0) or 0)
    return int(round((r1 + r2) / 90.0) * 90) % 360


def make_cell(src, x, y, w, h, fill="cover", pip=False, border=0, poly=None, rotate=0):
    c = {"src": src, "x": x, "y": y, "w": w, "h": h, "fill": fill,
         "ox": 0, "oy": 0, "pip": pip, "border": border}
    if rotate:
        c["rotate"] = int(rotate) % 360
    if poly:
        c["poly"] = [[float(px), float(py)] for px, py in poly]
    return c


def make_diag_cells(top_src="viral", bot_src="person", y_left=0.745, y_right=0.255, fill="cover"):
    """生成上下两格斜线分割版式：斜线从画布左边缘 (0, y_left) 连接到右边缘 (1, y_right)。"""
    yl = max(0.05, min(0.95, float(y_left)))
    yr = max(0.05, min(0.95, float(y_right)))
    h_top = max(yl, yr)
    y_bot = min(yl, yr)
    poly_top = [[0.0, 0.0], [1.0, 0.0], [1.0, yr], [0.0, yl]]
    poly_bot = [[0.0, yl], [1.0, yr], [1.0, 1.0], [0.0, 1.0]]
    return [
        make_cell(top_src, 0.0, 0.0, 1.0, h_top, fill=fill, poly=poly_top),
        make_cell(bot_src, 0.0, y_bot, 1.0, 1.0 - y_bot, fill=fill, poly=poly_bot),
    ]


def tpl_diag_ys(cells: list):
    """若前两个普通格子构成全宽斜线分割，返回 (y_left, y_right) 比例；否则返回 None。"""
    if not cells or len(cells) < 2:
        return None
    c0, c1 = cells[0], cells[1]
    if c0.get("pip") or c1.get("pip"):
        return None
    p0, p1 = c0.get("poly"), c1.get("poly")
    if not p0 or not p1 or len(p0) != 4 or len(p1) != 4:
        return None
    try:
        # 约定 p0 = [[0,0], [1,0], [1,yr], [0,yl]], p1 = [[0,yl], [1,yr], [1,1], [0,1]]
        yl0, yr0 = float(p0[3][1]), float(p0[2][1])
        yl1, yr1 = float(p1[0][1]), float(p1[1][1])
        if abs(yl0 - yl1) < 0.01 and abs(yr0 - yr1) < 0.01:
            return (yl0, yr0)
    except Exception:
        pass
    return None


def set_tpl_diag_ys(cells: list, y_left: float, y_right: float) -> bool:
    """更新斜线分割模板的左右端点高度比例 (y_left, y_right)，同时同步两格的包围盒与多边形顶点。"""
    if not cells or len(cells) < 2:
        return False
    yl = max(0.05, min(0.95, float(y_left)))
    yr = max(0.05, min(0.95, float(y_right)))
    c0, c1 = cells[0], cells[1]
    h_top = max(yl, yr)
    y_bot = min(yl, yr)
    c0["x"], c0["y"], c0["w"], c0["h"] = 0.0, 0.0, 1.0, h_top
    c0["poly"] = [[0.0, 0.0], [1.0, 0.0], [1.0, yr], [0.0, yl]]
    c1["x"], c1["y"], c1["w"], c1["h"] = 0.0, y_bot, 1.0, 1.0 - y_bot
    c1["poly"] = [[0.0, yl], [1.0, yr], [1.0, 1.0], [0.0, 1.0]]
    return True


def cell_poly_px(cell: dict, tpl: dict = None):
    """若格子带有多边形裁剪顶点 poly（0~1 比例），返回画布像素坐标列表 [(x, y), ...]；否则返回 None。"""
    poly = cell.get("poly") if cell else None
    if not poly or len(poly) < 3:
        return None
    cw, ch = get_canvas_size(tpl)
    return [(float(pt[0]) * cw, float(pt[1]) * ch) for pt in poly]


def cell_label_rect_px(cell: dict, tpl: dict = None) -> tuple:
    """返回格子用于绘制序号与文字标签的最佳像素矩形 (x, y, w, h)，针对斜切梯形自动偏向宽敞一侧。"""
    x, y, w, h = cell_rect_px(cell, tpl)
    poly = cell.get("poly")
    if not poly or len(poly) != 4:
        return x, y, w, h
    cw, ch = get_canvas_size(tpl)
    try:
        # 顶格 [[0,0],[1,0],[1,yr],[0,yl]] 或 底格 [[0,yl],[1,yr],[1,1],[0,1]]
        if abs(float(poly[0][1])) < 1e-3 and abs(float(poly[1][1])) < 1e-3:
            yl, yr = float(poly[3][1]), float(poly[2][1])
            cx = (0.36 if yl >= yr else 0.64) * cw
            cy = ((yl + yr) * 0.25) * ch
        else:
            yl, yr = float(poly[0][1]), float(poly[1][1])
            cx = (0.64 if yl >= yr else 0.36) * cw
            cy = (0.5 + (yl + yr) * 0.25) * ch
        bw, bh = w * 0.55, max(80.0, h * 0.42)
        return cx - bw / 2, cy - bh / 2, bw, bh
    except Exception:
        return x, y, w, h


def auto_assign_cell_sources(cells: list, viral_idx: int = None) -> list:
    """自动为格子列表分配不重复的视频来源：指定 viral_idx 为主视频，其余依次为 人物视频1..12。"""
    if not cells:
        return cells
    if viral_idx is None:
        viral_idx = next((i for i, c in enumerate(cells) if c.get("src") == "viral"), 0)
    viral_idx = max(0, min(len(cells) - 1, int(viral_idx)))
    person_srcs = [s for s in SOURCES if s != "viral"]
    p_idx = 0
    for i, c in enumerate(cells):
        if i == viral_idx:
            c["src"] = "viral"
        else:
            c["src"] = person_srcs[p_idx % len(person_srcs)]
            p_idx += 1
    return cells


def make_row_grid_cells(row_cols: list, row_heights: list = None, viral_index: int = 0, fill: str = "cover") -> list:
    """
    按「每行几格」快速生成平行分割线版式。
    row_cols: 例如 [1, 3, 3] 表示上1、中3、下3 共7格；
    row_heights: 每行高度比例列表（自动归一化），为 None 时若首行为1格且总行数>=3则首行占0.5，其余平分。
    viral_index: 哪一个格子（0-based）设为主视频。
    """
    rows = [max(1, int(c)) for c in (row_cols or [1, 1]) if int(c) >= 1]
    if not rows:
        rows = [1, 1]
    n_rows = len(rows)
    if row_heights and len(row_heights) == n_rows and sum(row_heights) > 0:
        total_h = float(sum(row_heights))
        hs = [float(h) / total_h for h in row_heights]
    else:
        if n_rows >= 3 and rows[0] == 1:
            rem = 0.5 / (n_rows - 1)
            hs = [0.5] + [rem] * (n_rows - 1)
        else:
            hs = [1.0 / n_rows] * n_rows

    cells = []
    y = 0.0
    for r_i, (n_col, rh) in enumerate(zip(rows, hs)):
        if r_i == n_rows - 1:
            rh = max(0.05, 1.0 - y)
        cw = 1.0 / n_col
        for c_i in range(n_col):
            cx = c_i * cw
            w = (1.0 - cx) if c_i == n_col - 1 else cw
            cells.append(make_cell("person", round(cx, 6), round(y, 6), round(w, 6), round(rh, 6), fill=fill))
        y += rh
    return auto_assign_cell_sources(cells, viral_idx=viral_index)


def snap_and_fill_cells(cells: list, tol: float = 0.035) -> list:
    """
    自动吸附并消除相邻方框之间的微小缝隙，使边缘对齐到画布边界 (0, 1)、常用等分线与相邻格子边缘。
    仅处理普通矩形格子（跳过画中画 pip 与多边形斜切 poly）。
    """
    rect_cells = [c for c in (cells or []) if not c.get("pip") and not c.get("poly")]
    if not rect_cells:
        return cells
    T = 1.0 / 3.0
    std_targets = [0.0, 0.25, T, 0.5, 2.0 * T, 0.75, 1.0]

    def snap_1d(vals: list) -> dict:
        # 先把接近的坐标聚类合并，再吸附到标准分位线/边界
        sorted_v = sorted(vals)
        groups = []
        for v in sorted_v:
            if not groups or abs(v - groups[-1][-1]) > tol:
                groups.append([v])
            else:
                groups[-1].append(v)
        mapping = {}
        for g in groups:
            avg = sum(g) / len(g)
            best_t = avg
            best_d = tol
            # 优先吸附画布边界 0.0 和 1.0
            if abs(avg - 0.0) <= tol * 1.3:
                best_t = 0.0
            elif abs(avg - 1.0) <= tol * 1.3:
                best_t = 1.0
            else:
                for t in std_targets:
                    d = abs(avg - t)
                    if d <= best_d:
                        best_d = d
                        best_t = t
            for v in g:
                mapping[v] = round(max(0.0, min(1.0, best_t)), 6)
        return mapping

    xs, ys = [], []
    for c in rect_cells:
        x1, y1 = float(c.get("x", 0)), float(c.get("y", 0))
        x2, y2 = x1 + float(c.get("w", 0.5)), y1 + float(c.get("h", 0.5))
        xs.extend([x1, x2])
        ys.extend([y1, y2])
    map_x = snap_1d(xs)
    map_y = snap_1d(ys)
    for c in rect_cells:
        x1, y1 = float(c.get("x", 0)), float(c.get("y", 0))
        x2, y2 = x1 + float(c.get("w", 0.5)), y1 + float(c.get("h", 0.5))
        nx1 = map_x.get(x1, x1)
        nx2 = map_x.get(x2, x2)
        ny1 = map_y.get(y1, y1)
        ny2 = map_y.get(y2, y2)
        if nx2 - nx1 >= 0.05:
            c["x"], c["w"] = round(nx1, 6), round(nx2 - nx1, 6)
        if ny2 - ny1 >= 0.05:
            c["y"], c["h"] = round(ny1, 6), round(ny2 - ny1, 6)
    return cells


def _layout_presets():
    T = 1.0 / 3
    pw, m = 0.28, 0.03                 # 小窗宽度、边距（画布 9:16，小窗也是 9:16 → 高度比例 = 宽度比例）
    py = 1 - 0.12 - pw                 # 小窗离底部留出一点空间
    full = make_cell("viral", 0, 0, 1, 1)
    pip = lambda src, x, y=py, w=pw: make_cell(src, x, y, w, w, pip=True, border=6)
    return [
        # ── 1. 平行分屏（分割线平行：上下、左右、多行多格拼接，最常用） ──
        ("平行分屏", "上1 / 下1", [make_cell("viral", 0, 0, 1, .5), make_cell("person", 0, .5, 1, .5)]),
        ("平行分屏", "左1 / 右1", [make_cell("viral", 0, 0, .5, 1), make_cell("person", .5, 0, .5, 1)]),
        ("平行分屏", "左右分屏（居中，底部留白）", [make_cell("viral", 0, .2, .5, .5625),
                                         make_cell("person", .5, .2, .5, .5625)]),
        ("平行分屏", "上1/3 / 下2/3", [make_cell("viral", 0, 0, 1, T), make_cell("person", 0, T, 1, 1 - T)]),
        ("平行分屏", "上2/3 / 下1/3", [make_cell("viral", 0, 0, 1, 2 * T), make_cell("person", 0, 2 * T, 1, T)]),
        ("平行分屏", "纵向三等分（上中下）", [make_cell("viral", 0, 0, 1, T), make_cell("person", 0, T, 1, T),
                           make_cell("person2", 0, 2 * T, 1, T)]),
        ("平行分屏", "上1 / 下2", [make_cell("viral", 0, 0, 1, .5), make_cell("person", 0, .5, .5, .5),
                            make_cell("person2", .5, .5, .5, .5)]),
        ("平行分屏", "上2 / 下1", [make_cell("person", 0, 0, .5, .5), make_cell("person2", .5, 0, .5, .5),
                            make_cell("viral", 0, .5, 1, .5)]),
        ("平行分屏", "上1 / 下3", [make_cell("viral", 0, 0, 1, .5), make_cell("person", 0, .5, T, .5),
                            make_cell("person2", T, .5, T, .5), make_cell("person3", 2 * T, .5, T, .5)]),
        ("平行分屏", "上1 / 下4（田字底）", [make_cell("viral", 0, 0, 1, .5),
                            make_cell("person", 0, .5, .5, .25), make_cell("person2", .5, .5, .5, .25),
                            make_cell("person3", 0, .75, .5, .25), make_cell("person4", .5, .75, .5, .25)]),
        ("平行分屏", "四宫格（2×2）", make_row_grid_cells([2, 2], [0.5, 0.5], viral_index=0)),
        ("平行分屏", "六格（上1 / 中2 / 下3）", make_row_grid_cells([1, 2, 3], [0.50, 0.25, 0.25], viral_index=0)),
        ("平行分屏", "六格（上1 / 中3 / 下2）", make_row_grid_cells([1, 3, 2], [0.50, 0.25, 0.25], viral_index=0)),
        ("平行分屏", "七格（上1 / 中3 / 下3）", make_row_grid_cells([1, 3, 3], [0.50, 0.25, 0.25], viral_index=0)),
        ("平行分屏", "十格（上1 / 下九宫格3×3）", make_row_grid_cells([1, 3, 3, 3], [0.52, 0.16, 0.16, 0.16], viral_index=0)),

        # ── 2. 不平行 / 错位与斜线（分割线不平行或错位T字/十字拼接） ──
        ("不平行/斜线", "斜线分屏（左低右高·主上人下）", make_diag_cells("viral", "person", 0.745, 0.255)),
        ("不平行/斜线", "斜线分屏（左低右高·人上主下）", make_diag_cells("person", "viral", 0.745, 0.255)),
        ("不平行/斜线", "斜线分屏（左高右低·主上人下）", make_diag_cells("viral", "person", 0.255, 0.745)),
        ("不平行/斜线", "斜线分屏（左高右低·人上主下）", make_diag_cells("person", "viral", 0.255, 0.745)),
        ("不平行/斜线", "五格（左2右1 / 下2）", [
            make_cell("viral", .38, 0, .62, 2 * T),
            make_cell("person", 0, 0, .38, T),
            make_cell("person2", 0, T, .38, T),
            make_cell("person3", 0, 2 * T, .5, 1 - 2 * T),
            make_cell("person4", .5, 2 * T, .5, 1 - 2 * T),
        ]),
        ("不平行/斜线", "五格（左1右2 / 下2）", [
            make_cell("viral", 0, 0, .62, 2 * T),
            make_cell("person", .62, 0, .38, T),
            make_cell("person2", .62, T, .38, T),
            make_cell("person3", 0, 2 * T, .5, 1 - 2 * T),
            make_cell("person4", .5, 2 * T, .5, 1 - 2 * T),
        ]),
        ("不平行/斜线", "七格（左2中1右2 / 下2）", [
            make_cell("viral", .25, 0, .50, 2 * T),
            make_cell("person", 0, 0, .25, T),
            make_cell("person2", 0, T, .25, T),
            make_cell("person3", .75, 0, .25, T),
            make_cell("person4", .75, T, .25, T),
            make_cell("person5", 0, 2 * T, .50, 1 - 2 * T),
            make_cell("person6", .50, 2 * T, .50, 1 - 2 * T),
        ]),
        ("不平行/斜线", "九格（左2右1 / 下左4右2）", [
            make_cell("viral", .32, 0, .68, 2 * T),
            make_cell("person", 0, 0, .32, T),
            make_cell("person2", 0, T, .32, T),
            make_cell("person3", 0, 2 * T, .16, (1 - 2 * T) * .5),
            make_cell("person4", .16, 2 * T, .16, (1 - 2 * T) * .5),
            make_cell("person5", 0, 2 * T + (1 - 2 * T) * .5, .16, (1 - 2 * T) * .5),
            make_cell("person6", .16, 2 * T + (1 - 2 * T) * .5, .16, (1 - 2 * T) * .5),
            make_cell("person7", .32, 2 * T, .34, 1 - 2 * T),
            make_cell("person8", .66, 2 * T, .34, 1 - 2 * T),
        ]),

        # ── 3. 画中画（背景 + 可自由增删的悬浮小窗口） ──
        ("画中画", "全屏背景 + 单小窗", [full, pip("person", 1 - m - pw)]),
        ("画中画", "全屏背景 + 双小窗", [full, pip("person", m), pip("person2", 1 - m - pw)]),
        ("画中画", "全屏背景 + 三小窗", [full, pip("person", m), pip("person2", (1 - pw) / 2),
                                    pip("person3", 1 - m - pw)]),
        ("画中画", "全屏背景 + 四小窗", [
            full,
            pip("person", 0.02, 0.64, 0.22),
            pip("person2", 0.26, 0.64, 0.22),
            pip("person3", 0.52, 0.64, 0.22),
            pip("person4", 0.76, 0.64, 0.22),
        ]),
    ]


LAYOUT_PRESETS = _layout_presets()


def template_from_cells(name: str, cells: list) -> dict:
    import copy
    tpl = {"name": name, "cells": copy.deepcopy(cells)}
    if tpl_diag_ys(cells) is not None:
        tpl["divider"] = {"width": 8, "color": "#000000"}
    return tpl


def tpl_cells(tpl: dict) -> list:
    """统一返回格子列表；旧版「上下分屏」模板自动转换（渲染结果完全一致）。"""
    if tpl.get("cells"):
        return tpl["cells"]
    _, ch = get_canvas_size(tpl)
    split_px = max(50, min(ch - 50, int(round(ch * float(tpl.get("split", 0.5))))))
    s = split_px / ch
    top_src, bot_src = ("person", "viral") if tpl.get("order", "person_top") == "person_top" else ("viral", "person")
    out = []
    for src, y, h, key in ((top_src, 0.0, s, "top"), (bot_src, s, 1 - s, "bottom")):
        b = tpl.get(key, {}) or {}
        cell = make_cell(src, 0.0, y, 1.0, h, fill=b.get("fill", "width"), rotate=int(b.get("rotate", 0) or 0))
        cell["ox"], cell["oy"] = int(b.get("ox", 0)), int(b.get("oy", 0))
        if b.get("ref_size"):
            cell["ref_size"] = list(b["ref_size"])
        out.append(cell)
    return out


def _ev(v: float) -> int:
    return int(round(v / 2.0)) * 2


def cell_rect_px(cell: dict, tpl: dict = None) -> tuple:
    """格子在画布上的像素矩形 (x, y, w, h)，全部取偶数，相邻格子无缝。"""
    cw, ch = get_canvas_size(tpl)
    x1 = max(0, min(cw, _ev(float(cell["x"]) * cw)))
    y1 = max(0, min(ch, _ev(float(cell["y"]) * ch)))
    x2 = max(0, min(cw, _ev((float(cell["x"]) + float(cell["w"])) * cw)))
    y2 = max(0, min(ch, _ev((float(cell["y"]) + float(cell["h"])) * ch)))
    return x1, y1, max(2, x2 - x1), max(2, y2 - y1)


def ordered_cells(tpl: dict) -> list:
    """绘制顺序：普通格子在下，画中画小窗在上。返回 [(编号, cell), ...]"""
    cells = list(enumerate(tpl_cells(tpl)))
    return [x for x in cells if not x[1].get("pip")] + [x for x in cells if x[1].get("pip")]


def sources_used(tpl: dict) -> list:
    used = {c.get("src") for c in tpl_cells(tpl)}
    return [s for s in SOURCES if s in used]


def layout_split_y(tpl: dict) -> int:
    """卡片「吸附分割线」使用的 Y：斜线分屏取斜线中点 Y；横竖分屏优先取贯穿全宽的第一条横向分界线；画中画用模板 split 或画面中间。"""
    cw, ch = get_canvas_size(tpl)
    cells = [c for c in tpl_cells(tpl) if not c.get("pip")]
    diag = tpl_diag_ys(cells)
    if diag is not None:
        return int(round((diag[0] + diag[1]) * 0.5 * ch))
    rects = [cell_rect_px(c, tpl) for c in cells]
    ys = sorted({y + h for _, y, _, h in rects if 0 < y + h < ch})
    for y in ys:
        span = sum(w for _, cy, w, rh in rects if abs((cy + rh) - y) <= 2)
        if span >= cw - 4:
            return y
    if ys:
        return ys[0]
    return int(round(ch * float(tpl.get("split") or 0.5)))


def box_layout(tpl: dict) -> dict:
    return {"split_y": layout_split_y(tpl), "cells": tpl_cells(tpl)}


# ── 画面整体：背景色 / 拼接分隔线 ──────────────────────────────────────────────

def tpl_bg_color(tpl: dict) -> str:
    """模板背景色（格子没覆盖到的区域），默认黑色。"""
    c = str((tpl or {}).get("bg_color") or "#000000").strip()
    return c if c.startswith("#") and len(c) in (4, 7) else "#000000"


def tpl_divider(tpl: dict) -> tuple:
    """(宽度px, 颜色)；宽度为 0 表示不画分隔线。"""
    d = (tpl or {}).get("divider") or {}
    try:
        w = max(0, int(d.get("width", 0) or 0))
    except Exception:
        w = 0
    c = str(d.get("color") or "#FFFFFF")
    return w, (c if c.startswith("#") else "#FFFFFF")


def divider_lines(tpl: dict) -> list:
    """
    返回斜线分割模板的分隔线段列表 [(x1, y1, x2, y2), ...]，像素坐标。
    宽度为 0 或非斜线模板时返回 []。
    """
    wd, _ = tpl_divider(tpl)
    if wd <= 0:
        return []
    cw, ch = get_canvas_size(tpl)
    cells = [c for c in tpl_cells(tpl) if not c.get("pip")]
    diag = tpl_diag_ys(cells)
    if diag is not None:
        return [(0.0, diag[0] * ch, float(cw), diag[1] * ch)]
    return []


def divider_rects(tpl: dict) -> list:
    """
    只在「矩形格子与矩形格子相接」的地方生成分隔条（画布四周、格子与背景相接处不画）。
    返回 [(x, y, w, h), ...]，像素坐标，分隔条以接缝为中心。画中画小窗和斜线格子不参与矩形分隔。
    """
    wd, _ = tpl_divider(tpl)
    if wd <= 0:
        return []
    cw, ch = get_canvas_size(tpl)
    cells = [c for c in tpl_cells(tpl) if not c.get("pip") and not c.get("poly")]
    rects = [cell_rect_px(c, tpl) for c in cells]
    half = wd / 2.0
    raw = []
    for i, (ax, ay, aw, ah) in enumerate(rects):
        for j, (bx, by, bw, bh) in enumerate(rects):
            if i == j:
                continue
            if abs(ax + aw - bx) <= 3:                      # A 的右边贴着 B 的左边 → 竖线
                y0, y1 = max(ay, by), min(ay + ah, by + bh)
                if y1 - y0 > 2:
                    x = (ax + aw + bx) / 2.0
                    raw.append((x - half, y0, wd, y1 - y0))
            if abs(ay + ah - by) <= 3:                      # A 的下边贴着 B 的上边 → 横线
                x0, x1 = max(ax, bx), min(ax + aw, bx + bw)
                if x1 - x0 > 2:
                    y = (ay + ah + by) / 2.0
                    raw.append((x0, y - half, x1 - x0, wd))
    out, seen = [], set()
    for x, y, w, h in raw:
        x1, y1 = max(0, int(round(x))), max(0, int(round(y)))
        x2, y2 = min(cw, int(round(x + w))), min(ch, int(round(y + h)))
        if x2 - x1 < 1 or y2 - y1 < 1:
            continue
        key = (x1, y1, x2 - x1, y2 - y1)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _ff_color(hexc: str) -> str:
    h = (hexc or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return "0x" + (h.upper() if len(h) == 6 else "000000")


def place_in_cell(src_w: int, src_h: int, cw: int, ch: int, cell: dict, adj: dict = None, tpl: dict = None,
                  already_rotated: bool = False) -> tuple:
    """视频在格子内的缩放尺寸与位置（相对格子左上角）。返回 (sw, sh, x, y)"""
    adj = adj or {}
    canv_w, canv_h = get_canvas_size(tpl)
    if src_w <= 0 or src_h <= 0:
        src_w, src_h = canv_w, canv_h
    rot = cell_rotation(cell, adj)
    if not already_rotated and rot in (90, 270):
        src_w, src_h = src_h, src_w
    ref = cell.get("ref_size")
    if isinstance(ref, (list, tuple)) and len(ref) == 2 and ref[0] > 0 and ref[1] > 0:
        ref_w, ref_h = float(ref[0]), float(ref[1])
    else:
        ref_w, ref_h = float(REF_W), float(REF_H)
    is_adapted = (abs(ref_w - canv_w) > 1 or abs(ref_h - canv_h) > 1)

    fill = cell.get("fill", "cover")
    sx, sy = cw / src_w, ch / src_h
    s = {"width": sx, "height": sy, "contain": min(sx, sy)}.get(fill, max(sx, sy))
    # 当切换画布尺寸（如从 9:16 切换到 16:9 / 4:3 / 1:1 / 3:4）或旋转 90°/270° 时，
    # 旧版模板中的等宽/等高若不足以铺满格子，自动升级为 cover 避免留黑边
    if (is_adapted or rot in (90, 270)) and fill in ("width", "height") and s < max(sx, sy):
        s = max(sx, sy)
    s *= float(adj.get("scale", 100)) / 100.0
    sw, sh = _even(src_w * s), _even(src_h * s)

    ox_raw = float(cell.get("ox", 0)) * (canv_w / ref_w)
    oy_raw = float(cell.get("oy", 0)) * (canv_h / ref_h)
    bx = (cw - sw) / 2.0 + ox_raw
    by = (ch - sh) / 2.0 + oy_raw
    # 跨尺寸自动适配时，限制模板预设偏移不超出视频边缘，防止因旧版大偏移（如 oy=312）在新尺寸露出黑边
    if is_adapted and fill != "contain":
        if sw >= cw:
            bx = max(float(cw - sw), min(0.0, bx))
        if sh >= ch:
            by = max(float(ch - sh), min(0.0, by))
    x = bx + int(adj.get("dx", 0))
    y = by + int(adj.get("dy", 0))
    return sw, sh, int(round(x)), int(round(y))


def _even(v: float) -> int:
    v = int(round(v))
    return max(2, v - (v % 2))


def task_source(task: dict, src: str):
    """返回 (路径, 宽, 高, 是否有声音)；任务里没有这一路视频时返回 None。"""
    if src == "viral":
        return task.get("viral"), task.get("v_w", 0), task.get("v_h", 0), bool(task.get("v_audio"))
    if src == "person":
        p = task.get("cache") or task.get("person")
        if not p:
            return None
        return p, task.get("p_w", 0), task.get("p_h", 0), bool(task.get("p_audio"))
    try:
        k = int(src.replace("person", "")) - 2
    except ValueError:
        return None
    ex = task.get("extra") or []
    if 0 <= k < len(ex) and (ex[k].get("cache") or ex[k].get("person")):
        e = ex[k]
        return e.get("cache") or e.get("person"), e.get("w", 0), e.get("h", 0), bool(e.get("audio"))
    return None


def task_source_meta(task: dict, src: str):
    """返回该视频源的完整元数据 dict，用于导出时动态循环对齐与变速。"""
    if src == "viral":
        p = task.get("viral")
        if not p:
            return None
        return {
            "path": p,
            "w": task.get("v_w", 0),
            "h": task.get("v_h", 0),
            "audio": bool(task.get("v_audio")),
            "raw_audio": bool(task.get("v_audio")),
            "dur": float(task.get("v_dur") or task.get("duration") or 0),
            "need_loop_align": False,
        }
    if src == "person":
        raw_p = task.get("person")
        cache_p = task.get("cache") or raw_p
        if not cache_p:
            return None
        is_pre_aligned = bool(
            cache_p and raw_p
            and os.path.normcase(os.path.abspath(cache_p)) != os.path.normcase(os.path.abspath(raw_p))
        )
        skip_align = bool(task.get("skip_align", False))
        return {
            "path": cache_p,
            "raw_path": raw_p or cache_p,
            "w": task.get("p_w", 0),
            "h": task.get("p_h", 0),
            "audio": bool(task.get("p_audio")),
            "raw_audio": bool(task.get("p_raw_audio", task.get("p_audio", False))),
            "dur": float(task.get("p_dur") or 0),
            "need_loop_align": (not is_pre_aligned) and (not skip_align),
        }
    try:
        k = int(src.replace("person", "")) - 2
    except ValueError:
        return None
    ex = task.get("extra") or []
    if 0 <= k < len(ex) and (ex[k].get("cache") or ex[k].get("person")):
        e = ex[k]
        raw_p = e.get("person")
        cache_p = e.get("cache") or raw_p
        is_pre_aligned = bool(
            cache_p and raw_p
            and os.path.normcase(os.path.abspath(cache_p)) != os.path.normcase(os.path.abspath(raw_p))
        )
        skip_align = bool(task.get("skip_align", False))
        return {
            "path": cache_p,
            "raw_path": raw_p or cache_p,
            "w": e.get("w", 0),
            "h": e.get("h", 0),
            "audio": bool(e.get("audio")),
            "raw_audio": bool(e.get("raw_audio", e.get("audio", False))),
            "dur": float(e.get("dur") or 0),
            "need_loop_align": (not is_pre_aligned) and (not skip_align),
        }
    return None


# ── 最终渲染命令 ──────────────────────────────────────────────────────────────

ENCODERS = {
    "cpu":   "libx264",
    "nvenc": "h264_nvenc",
    "amf":   "h264_amf",
    "qsv":   "h264_qsv",
}


def _encoder_args(enc_key: str, q: int) -> list:
    if enc_key == "nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(q), "-b:v", "0"]
    if enc_key == "amf":
        return ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp",
                "-qp_i", str(q), "-qp_p", str(q)]
    if enc_key == "qsv":
        return ["-c:v", "h264_qsv", "-global_quality", str(q)]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", str(q)]


def _ensure_cell_mask_png(cell: dict, x: int, y: int, w: int, h: int, tpl: dict = None) -> str:
    """为带 poly 的斜切格子生成 w x h 灰度遮罩 PNG（带抗锯齿与 1.5px 接缝防漏底扩边）。"""
    pts = cell_poly_px(cell, tpl)
    if not pts:
        return ""
    import hashlib
    key_str = f"{w}x{h}:{x},{y}:" + ";".join(f"{px:.2f},{py:.2f}" for px, py in pts)
    digest = hashlib.md5(key_str.encode("utf-8")).hexdigest()[:12]
    mask_dir = os.path.join(get_cache_dir(), "_masks")
    os.makedirs(mask_dir, exist_ok=True)
    out_p = os.path.join(mask_dir, f"cell_mask_{w}x{h}_{digest}.png")
    if os.path.isfile(out_p) and os.path.getsize(out_p) > 0:
        return out_p
    from PyQt6.QtCore import Qt, QPointF
    from PyQt6.QtGui import QImage, QPainter, QColor, QPolygonF, QPen
    img = QImage(w, h, QImage.Format.Format_Grayscale8)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(QColor(255, 255, 255))
    poly = QPolygonF([QPointF(px - x, py - y) for px, py in pts])
    p.drawPolygon(poly)
    p.end()
    tmp_p = f"{out_p}.{os.getpid()}.tmp.png"
    img.save(tmp_p, "PNG")
    try:
        os.replace(tmp_p, out_p)
    except Exception:
        if os.path.exists(tmp_p):
            try:
                os.remove(tmp_p)
            except Exception:
                pass
    return out_p


def _ensure_diag_divider_png(tpl: dict) -> str:
    """为斜线分割模板生成画布尺寸的透明分隔线图层 PNG。"""
    lines = divider_lines(tpl)
    wd, col_hex = tpl_divider(tpl)
    if not lines or wd <= 0:
        return ""
    cw, ch = get_canvas_size(tpl)
    import hashlib
    key_str = f"{cw}x{ch}:{wd}:{col_hex}:" + ";".join(
        f"{x1:.2f},{y1:.2f},{x2:.2f},{y2:.2f}" for x1, y1, x2, y2 in lines
    )
    digest = hashlib.md5(key_str.encode("utf-8")).hexdigest()[:12]
    mask_dir = os.path.join(get_cache_dir(), "_masks")
    os.makedirs(mask_dir, exist_ok=True)
    out_p = os.path.join(mask_dir, f"diag_div_{digest}.png")
    if os.path.isfile(out_p) and os.path.getsize(out_p) > 0:
        return out_p
    from PyQt6.QtCore import Qt, QPointF
    from PyQt6.QtGui import QImage, QPainter, QColor, QPen
    img = QImage(cw, ch, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(col_hex), float(wd), Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.MiterJoin)
    p.setPen(pen)
    for x1, y1, x2, y2 in lines:
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    p.end()
    tmp_p = f"{out_p}.{os.getpid()}.tmp.png"
    img.save(tmp_p, "PNG")
    try:
        os.replace(tmp_p, out_p)
    except Exception:
        if os.path.exists(tmp_p):
            try:
                os.remove(tmp_p)
            except Exception:
                pass
    return out_p


def build_render_cmd(task: dict, tpl: dict, out_path: str, *,
                     title_png: str = "", title_end: float = 0.0,
                     phone_png: str = "", phone_start: float = 0.0,
                     wm_png: str = "", global_speed: float = 1.0, max_3min: bool = False,
                     mute_viral: bool = False, volume: float = 1.0,
                     person_speed: float = None, mute_person: bool = None,
                     out_w: int = 1080, out_h: int = 1920,
                     quality: int = 23, enc_key: str = "cpu") -> list:
    """task 需包含：cache/person, viral, duration, p_w, p_h, v_w, v_h, p_audio, v_audio, adj（可选 extra）"""
    D = float(task["duration"])
    adj = task.get("adj", {}) or {}
    p_speed = max(0.1, float(person_speed if person_speed is not None else task.get("person_speed", 1.0)))
    p_mute = bool(mute_person if mute_person is not None else task.get("mute_person", True))
    canv_w, canv_h = get_canvas_size(tpl)
    cells = [(i, cl) for i, cl in ordered_cells(tpl) if task_source(task, cl.get("src"))]

    cmd = [get_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error"]
    src_idx, src_info, src_meta = {}, {}, {}
    for _, cl in cells:
        sname = cl["src"]
        if sname not in src_idx:
            meta = task_source_meta(task, sname)
            src_idx[sname] = len(src_idx)
            src_info[sname] = (meta["path"], meta["w"], meta["h"], meta["audio"])
            src_meta[sname] = meta
            if meta["need_loop_align"]:
                p_dur = meta["dur"]
                if p_dur <= 0:
                    p_dur = probe_info(meta["path"]).get("duration", 0)
                    meta["dur"] = p_dur
                eff_dur = (p_dur / p_speed) if p_dur > 0 else D
                loops = max(1, math.ceil(D / eff_dur)) if eff_dur > 0 else 1
                if loops > 1:
                    cmd += ["-stream_loop", str(loops - 1)]
            cmd += ["-i", meta["path"]]
    idx = len(src_idx)
    title_idx = phone_idx = None
    if title_png and os.path.isfile(title_png):
        cmd += ["-loop", "1", "-t", f"{D:.3f}", "-i", title_png]
        title_idx = idx
        idx += 1
    if phone_png and os.path.isfile(phone_png):
        cmd += ["-loop", "1", "-t", f"{D:.3f}", "-i", phone_png]
        phone_idx = idx
        idx += 1

    wm_idx = None
    if wm_png and os.path.isfile(wm_png):
        cmd += ["-loop", "1", "-t", f"{D:.3f}", "-i", wm_png]
        wm_idx = idx
        idx += 1

    # 多边形斜切遮罩输入 & 斜线分隔条输入
    cell_mask_idx = {}
    for k, (ci, cl) in enumerate(cells):
        if cl.get("poly"):
            x, y, w, h = cell_rect_px(cl, tpl)
            mp = _ensure_cell_mask_png(cl, x, y, w, h, tpl)
            if mp and os.path.isfile(mp):
                cmd += ["-loop", "1", "-t", f"{D:.3f}", "-i", mp]
                cell_mask_idx[k] = idx
                idx += 1
    diag_div_idx = None
    diag_div_png = _ensure_diag_divider_png(tpl)
    if diag_div_png and os.path.isfile(diag_div_png):
        cmd += ["-loop", "1", "-t", f"{D:.3f}", "-i", diag_div_png]
        diag_div_idx = idx
        idx += 1

    fc = [f"color=c={_ff_color(tpl_bg_color(tpl))}:s={canv_w}x{canv_h}:r=30:d={D:.3f}[base]"]
    # 同一路视频用在多个格子里时需要 split；人物视频仅标记对齐时在此统一完成变速与循环裁切
    labels = {}
    for sname, si in src_idx.items():
        meta = src_meta[sname]
        base_v = f"{si}:v"
        if meta["need_loop_align"]:
            vf_parts = []
            if abs(p_speed - 1.0) > 1e-3:
                vf_parts.append(f"setpts=PTS/{p_speed:.4f}")
            vf_parts.append(f"trim=duration={D:.3f},setpts=PTS-STARTPTS")
            base_v = f"palign_v{si}"
            fc.append(f"[{si}:v]{','.join(vf_parts)}[{base_v}]")
        n = sum(1 for _, cl in cells if cl["src"] == sname)
        if n == 1:
            labels[sname] = [base_v]
        else:
            outs = [f"src{si}_{j}" for j in range(n)]
            fc.append(f"[{base_v}]split={n}" + "".join(f"[{o}]" for o in outs))
            labels[sname] = outs
    last = "base"
    div_rects = divider_rects(tpl)
    div_color = _ff_color(tpl_divider(tpl)[1])
    div_done = (not div_rects) and (diag_div_idx is None)

    def _add_dividers(src_label):
        cur = src_label
        if div_rects:
            chain = ",".join(f"drawbox=x={x}:y={y}:w={w}:h={h}:color={div_color}@1:t=fill"
                             for x, y, w, h in div_rects)
            fc.append(f"[{cur}]{chain}[dv_r]")
            cur = "dv_r"
        if diag_div_idx is not None:
            fc.append(f"[{cur}][{diag_div_idx}:v]overlay=0:0[dv_d]")
            cur = "dv_d"
        return cur

    for k, (ci, cl) in enumerate(cells):
        if not div_done and cl.get("pip"):          # 分隔线画在普通格子之上、画中画小窗之下
            last = _add_dividers(last)
            div_done = True
        x, y, w, h = cell_rect_px(cl, tpl)
        info = src_info[cl["src"]]
        c_adj = adj.get(cl["src"])
        rot = cell_rotation(cl, c_adj)
        sw, sh, ox, oy = place_in_cell(info[1], info[2], w, h, cl, c_adj, tpl)
        lab = labels[cl["src"]].pop(0)
        b = int(cl.get("border", 0) or 0)
        if b > 0 and k not in cell_mask_idx:
            fc.append(f"color=c=white:s={w + 2 * b}x{h + 2 * b}:r=30:d={D:.3f}[bd{k}]")
            fc.append(f"[{last}][bd{k}]overlay={x - b}:{y - b}[lb{k}]")
            last = f"lb{k}"
        fc.append(f"color=c=black:s={w}x{h}:r=30:d={D:.3f}[box{k}]")
        rot_f = {90: "transpose=1,", 180: "hflip,vflip,", 270: "transpose=2,"}.get(rot, "")
        fc.append(f"[{lab}]{rot_f}scale={sw}:{sh},setsar=1[sv{k}]")
        if k in cell_mask_idx:
            m_idx = cell_mask_idx[k]
            fc.append(f"[box{k}][sv{k}]overlay=x={ox}:y={oy}:eof_action=repeat,format=yuva420p[cb_raw{k}]")
            fc.append(f"[{m_idx}:v]format=gray[msk{k}]")
            fc.append(f"[cb_raw{k}][msk{k}]alphamerge[cb{k}]")
        else:
            fc.append(f"[box{k}][sv{k}]overlay=x={ox}:y={oy}:eof_action=repeat[cb{k}]")
        fc.append(f"[{last}][cb{k}]overlay={x}:{y}[l{k}]")
        last = f"l{k}"
    if not div_done:
        last = _add_dividers(last)
    if title_idx is not None:
        fc.append(f"[{last}][{title_idx}:v]overlay=0:0:enable='between(t,0,{title_end:.3f})'[s3]")
        last = "s3"
    if phone_idx is not None:
        fc.append(f"[{last}][{phone_idx}:v]overlay=0:0:enable='gte(t,{phone_start:.3f})'[s4]")
        last = "s4"
    if wm_idx is not None:
        fc.append(f"[{last}][{wm_idx}:v]overlay=0:0[s5]")
        last = "s5"
    fc.append(f"[{last}]scale={out_w}:{out_h},format=yuv420p[outv]")

    audio_srcs = []
    if "viral" in src_idx and src_info["viral"][3] and not mute_viral:
        audio_srcs.append(f"[{src_idx['viral']}:a]")
    for sname, si in src_idx.items():
        if sname == "viral":
            continue
        meta = src_meta[sname]
        if meta["need_loop_align"]:
            if (not p_mute) and meta["raw_audio"]:
                af_parts = []
                if abs(p_speed - 1.0) > 1e-3:
                    af_parts.append(_atempo_chain(p_speed))
                af_parts.append(f"atrim=duration={D:.3f},asetpts=PTS-STARTPTS")
                pa_lbl = f"palign_a{si}"
                fc.append(f"[{si}:a]{','.join(af_parts)}[{pa_lbl}]")
                audio_srcs.append(f"[{pa_lbl}]")
        else:
            if src_info[sname][3] and not p_mute:
                audio_srcs.append(f"[{si}:a]")
    amap = None
    if len(audio_srcs) >= 2:
        fc.append("".join(audio_srcs) + f"amix=inputs={len(audio_srcs)}:duration=longest:normalize=0,volume={volume:.2f}[outa]")
        amap = "[outa]"
    elif len(audio_srcs) == 1:
        fc.append(f"{audio_srcs[0]}volume={volume:.2f}[outa]")
        amap = "[outa]"

    final_v = "outv"
    final_a = amap.strip("[]") if amap else None
    
    speed = max(0.1, float(global_speed))
    if max_3min and D > 180.0:
        req_speed = D / 179.5
        if req_speed > speed:
            speed = req_speed
            
    if abs(speed - 1.0) > 1e-3:
        fc.append(f"[{final_v}]setpts=PTS/{speed:.4f}[speedv]")
        final_v = "speedv"
        if final_a:
            af = _atempo_chain(speed)
            fc.append(f"[{final_a}]{af}[speeda]")
            final_a = "speeda"

    cmd += ["-filter_complex", ";".join(fc), "-map", f"[{final_v}]"]
    if final_a:
        cmd += ["-map", f"[{final_a}]", "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]
    cmd += _encoder_args(enc_key, quality)
    
    out_duration = D / speed
    cmd += ["-t", f"{out_duration:.3f}", "-movflags", "+faststart", os.path.abspath(out_path)]
    return cmd


def run_cmd(cmd: list) -> tuple:
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                         errors="ignore", creationflags=_NO_WINDOW)
    return res.returncode, res.stderr
