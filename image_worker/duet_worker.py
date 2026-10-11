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

CANVAS_W = 1080
CANVAS_H = 1920

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
        # 超出时长时退回第 0 秒
        if t > 0:
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
SOURCES = ["viral", "person", "person2", "person3", "person4"]
SRC_LABELS = {"viral": "主视频", "person": "人物视频1", "person2": "人物视频2",
              "person3": "人物视频3", "person4": "人物视频4"}
FILL_MODES = [("cover", "铺满格子（超出裁切）"), ("width", "等宽对齐（宽=格子宽）"),
              ("height", "等高对齐（高=格子高）"), ("contain", "完整显示（留黑边）")]


def make_cell(src, x, y, w, h, fill="cover", pip=False, border=0):
    return {"src": src, "x": x, "y": y, "w": w, "h": h, "fill": fill,
            "ox": 0, "oy": 0, "pip": pip, "border": border}


def _layout_presets():
    T = 1.0 / 3
    pw, m = 0.28, 0.03                 # 小窗宽度、边距（画布 9:16，小窗也是 9:16 → 高度比例 = 宽度比例）
    py = 1 - 0.12 - pw                 # 小窗离底部留出一点空间
    full = make_cell("viral", 0, 0, 1, 1)
    pip = lambda src, x: make_cell(src, x, py, pw, pw, pip=True, border=6)
    return [
        ("常用", "上1 / 下1", [make_cell("viral", 0, 0, 1, .5), make_cell("person", 0, .5, 1, .5)]),
        ("常用", "上1/3 / 下2/3", [make_cell("viral", 0, 0, 1, T), make_cell("person", 0, T, 1, 1 - T)]),
        ("常用", "上2/3 / 下1/3", [make_cell("viral", 0, 0, 1, 2 * T), make_cell("person", 0, 2 * T, 1, T)]),
        ("常用", "纵向三等分", [make_cell("viral", 0, 0, 1, T), make_cell("person", 0, T, 1, T),
                           make_cell("person2", 0, 2 * T, 1, T)]),
        ("多格", "上1 / 下2", [make_cell("viral", 0, 0, 1, .5), make_cell("person", 0, .5, .5, .5),
                            make_cell("person2", .5, .5, .5, .5)]),
        ("多格", "上1 / 下3", [make_cell("viral", 0, 0, 1, .5), make_cell("person", 0, .5, T, .5),
                            make_cell("person2", T, .5, T, .5), make_cell("person3", 2 * T, .5, T, .5)]),
        ("多格", "上1 / 下4", [make_cell("viral", 0, 0, 1, .5),
                            make_cell("person", 0, .5, .5, .25), make_cell("person2", .5, .5, .5, .25),
                            make_cell("person3", 0, .75, .5, .25), make_cell("person4", .5, .75, .5, .25)]),
        ("多格", "四宫格", [make_cell("viral", 0, 0, .5, .5), make_cell("person", .5, 0, .5, .5),
                         make_cell("person2", 0, .5, .5, .5), make_cell("person3", .5, .5, .5, .5)]),
        ("画中画", "全屏背景 + 小窗", [full, pip("person", 1 - m - pw)]),
        ("画中画", "全屏背景 + 双小窗", [full, pip("person", m), pip("person2", 1 - m - pw)]),
        ("画中画", "全屏背景 + 三小窗", [full, pip("person", m), pip("person2", (1 - pw) / 2),
                                    pip("person3", 1 - m - pw)]),
    ]


LAYOUT_PRESETS = _layout_presets()


def template_from_cells(name: str, cells: list) -> dict:
    import copy
    return {"name": name, "cells": copy.deepcopy(cells)}


def tpl_cells(tpl: dict) -> list:
    """统一返回格子列表；旧版「上下分屏」模板自动转换（渲染结果完全一致）。"""
    if tpl.get("cells"):
        return tpl["cells"]
    split_px = max(50, min(CANVAS_H - 50, int(round(CANVAS_H * float(tpl.get("split", 0.5))))))
    s = split_px / CANVAS_H
    top_src, bot_src = ("person", "viral") if tpl.get("order", "person_top") == "person_top" else ("viral", "person")
    out = []
    for src, y, h, key in ((top_src, 0.0, s, "top"), (bot_src, s, 1 - s, "bottom")):
        b = tpl.get(key, {}) or {}
        cell = make_cell(src, 0.0, y, 1.0, h, fill=b.get("fill", "width"))
        cell["ox"], cell["oy"] = int(b.get("ox", 0)), int(b.get("oy", 0))
        out.append(cell)
    return out


def _ev(v: float) -> int:
    return int(round(v / 2.0)) * 2


def cell_rect_px(cell: dict) -> tuple:
    """格子在 1080x1920 画布上的像素矩形 (x, y, w, h)，全部取偶数，相邻格子无缝。"""
    x1 = max(0, min(CANVAS_W, _ev(float(cell["x"]) * CANVAS_W)))
    y1 = max(0, min(CANVAS_H, _ev(float(cell["y"]) * CANVAS_H)))
    x2 = max(0, min(CANVAS_W, _ev((float(cell["x"]) + float(cell["w"])) * CANVAS_W)))
    y2 = max(0, min(CANVAS_H, _ev((float(cell["y"]) + float(cell["h"])) * CANVAS_H)))
    return x1, y1, max(2, x2 - x1), max(2, y2 - y1)


def ordered_cells(tpl: dict) -> list:
    """绘制顺序：普通格子在下，画中画小窗在上。返回 [(编号, cell), ...]"""
    cells = list(enumerate(tpl_cells(tpl)))
    return [x for x in cells if not x[1].get("pip")] + [x for x in cells if x[1].get("pip")]


def sources_used(tpl: dict) -> list:
    used = {c.get("src") for c in tpl_cells(tpl)}
    return [s for s in SOURCES if s in used]


def layout_split_y(tpl: dict) -> int:
    """卡片「吸附分割线」使用的 Y：第一条横向分界线；没有分界线（画中画）时用模板 split 或画面中间。"""
    ys = sorted({cell_rect_px(c)[1] + cell_rect_px(c)[3] for c in tpl_cells(tpl) if not c.get("pip")})
    ys = [y for y in ys if 0 < y < CANVAS_H]
    if ys:
        return ys[0]
    return int(round(CANVAS_H * float(tpl.get("split") or 0.5)))


def box_layout(tpl: dict) -> dict:
    return {"split_y": layout_split_y(tpl), "cells": tpl_cells(tpl)}


def place_in_cell(src_w: int, src_h: int, cw: int, ch: int, cell: dict, adj: dict = None) -> tuple:
    """视频在格子内的缩放尺寸与位置（相对格子左上角）。返回 (sw, sh, x, y)"""
    adj = adj or {}
    if src_w <= 0 or src_h <= 0:
        src_w, src_h = CANVAS_W, CANVAS_H
    fill = cell.get("fill", "cover")
    sx, sy = cw / src_w, ch / src_h
    s = {"width": sx, "height": sy, "contain": min(sx, sy)}.get(fill, max(sx, sy))
    s *= float(adj.get("scale", 100)) / 100.0
    sw, sh = _even(src_w * s), _even(src_h * s)
    x = (cw - sw) / 2 + int(cell.get("ox", 0)) + int(adj.get("dx", 0))
    y = (ch - sh) / 2 + int(cell.get("oy", 0)) + int(adj.get("dy", 0))
    return sw, sh, int(round(x)), int(round(y))


def _even(v: float) -> int:
    v = int(round(v))
    return max(2, v - (v % 2))


def task_source(task: dict, src: str):
    """返回 (路径, 宽, 高, 是否有声音)；任务里没有这一路视频时返回 None。"""
    if src == "viral":
        return task.get("viral"), task.get("v_w", 0), task.get("v_h", 0), bool(task.get("v_audio"))
    if src == "person":
        return task.get("cache"), task.get("p_w", 0), task.get("p_h", 0), bool(task.get("p_audio"))
    try:
        k = int(src.replace("person", "")) - 2
    except ValueError:
        return None
    ex = task.get("extra") or []
    if 0 <= k < len(ex) and ex[k].get("cache"):
        e = ex[k]
        return e["cache"], e.get("w", 0), e.get("h", 0), bool(e.get("audio"))
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


def build_render_cmd(task: dict, tpl: dict, out_path: str, *,
                     title_png: str = "", title_end: float = 0.0,
                     phone_png: str = "", phone_start: float = 0.0,
                     wm_png: str = "", global_speed: float = 1.0, max_3min: bool = False,
                     mute_viral: bool = False, volume: float = 1.0,
                     out_w: int = 1080, out_h: int = 1920,
                     quality: int = 23, enc_key: str = "cpu") -> list:
    """task 需包含：cache, viral, duration, p_w, p_h, v_w, v_h, p_audio, v_audio, adj（可选 extra）"""
    D = float(task["duration"])
    adj = task.get("adj", {}) or {}
    cells = [(i, cl) for i, cl in ordered_cells(tpl) if task_source(task, cl.get("src"))]

    cmd = [get_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error"]
    src_idx, src_info = {}, {}
    for _, cl in cells:
        sname = cl["src"]
        if sname not in src_idx:
            info = task_source(task, sname)
            src_idx[sname] = len(src_idx)
            src_info[sname] = info
            cmd += ["-i", info[0]]
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

    fc = [f"color=c=black:s={CANVAS_W}x{CANVAS_H}:r=30:d={D:.3f}[base]"]
    # 同一路视频用在多个格子里时需要 split
    labels = {}
    for sname, si in src_idx.items():
        n = sum(1 for _, cl in cells if cl["src"] == sname)
        if n == 1:
            labels[sname] = [f"{si}:v"]
        else:
            outs = [f"src{si}_{j}" for j in range(n)]
            fc.append(f"[{si}:v]split={n}" + "".join(f"[{o}]" for o in outs))
            labels[sname] = outs
    last = "base"
    for k, (ci, cl) in enumerate(cells):
        x, y, w, h = cell_rect_px(cl)
        info = src_info[cl["src"]]
        sw, sh, ox, oy = place_in_cell(info[1], info[2], w, h, cl, adj.get(cl["src"]))
        lab = labels[cl["src"]].pop(0)
        b = int(cl.get("border", 0) or 0)
        if b > 0:
            fc.append(f"color=c=white:s={w + 2 * b}x{h + 2 * b}:r=30:d={D:.3f}[bd{k}]")
            fc.append(f"[{last}][bd{k}]overlay={x - b}:{y - b}[lb{k}]")
            last = f"lb{k}"
        fc.append(f"color=c=black:s={w}x{h}:r=30:d={D:.3f}[box{k}]")
        fc.append(f"[{lab}]scale={sw}:{sh},setsar=1[sv{k}]")
        fc.append(f"[box{k}][sv{k}]overlay=x={ox}:y={oy}:eof_action=repeat[cb{k}]")
        fc.append(f"[{last}][cb{k}]overlay={x}:{y}[l{k}]")
        last = f"l{k}"
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
    for sname in src_idx:
        if sname != "viral" and src_info[sname][3]:
            audio_srcs.append(f"[{src_idx[sname]}:a]")
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
