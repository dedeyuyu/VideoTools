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
    以爆款视频时长为基准，将人物视频变速后循环至等长，并裁掉多余尾部。
    返回 {'cache': out_path, 'duration': viral_duration}
    """
    v_info = probe_info(viral_vid)
    p_info = probe_info(person_vid)
    viral_dur = v_info["duration"]
    person_dur = p_info["duration"]
    if viral_dur <= 0:
        raise ValueError(f"无法读取爆款视频时长：{os.path.basename(viral_vid)}")
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


def box_layout(tpl: dict) -> dict:
    """
    返回 {'split_y': int, 'person': (y, h, box_cfg), 'viral': (y, h, box_cfg)}
    """
    split_y = int(round(CANVAS_H * float(tpl.get("split", 0.5))))
    split_y = max(50, min(CANVAS_H - 50, split_y))
    top = (0, split_y, tpl.get("top", {}))
    bottom = (split_y, CANVAS_H - split_y, tpl.get("bottom", {}))
    if tpl.get("order", "person_top") == "person_top":
        return {"split_y": split_y, "person": top, "viral": bottom}
    return {"split_y": split_y, "person": bottom, "viral": top}


def _even(v: float) -> int:
    v = int(round(v))
    return max(2, v - (v % 2))


def place_in_box(src_w: int, src_h: int, box_h: int, box_cfg: dict, adj: dict = None) -> tuple:
    """
    计算视频在画框中的缩放尺寸与位置（相对画框左上角）。
    等宽对齐：宽度缩放至 1080；等高对齐：高度缩放至画框高度；超出部分由画框裁切。
    adj: 单任务微调 {'dx', 'dy', 'scale'(百分比)}
    返回 (sw, sh, x, y)
    """
    adj = adj or {}
    if src_w <= 0 or src_h <= 0:
        src_w, src_h = CANVAS_W, CANVAS_H
    if box_cfg.get("fill", "width") == "height":
        s = box_h / src_h
    else:
        s = CANVAS_W / src_w
    s *= float(adj.get("scale", 100)) / 100.0
    sw, sh = _even(src_w * s), _even(src_h * s)
    x = (CANVAS_W - sw) / 2 + int(box_cfg.get("ox", 0)) + int(adj.get("dx", 0))
    y = (box_h - sh) / 2 + int(box_cfg.get("oy", 0)) + int(adj.get("dy", 0))
    return sw, sh, int(round(x)), int(round(y))


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
    """task 需包含：cache, viral, duration, p_w, p_h, v_w, v_h, p_audio, v_audio, adj"""
    D = float(task["duration"])
    lay = box_layout(tpl)
    py, ph, pcfg = lay["person"]
    vy, vh, vcfg = lay["viral"]
    adj = task.get("adj", {})
    psw, psh, px, ppy = place_in_box(task["p_w"], task["p_h"], ph, pcfg, adj.get("person"))
    vsw, vsh, vx, vvy = place_in_box(task["v_w"], task["v_h"], vh, vcfg, adj.get("viral"))

    cmd = [get_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
           "-i", task["cache"], "-i", task["viral"]]
    idx = 2
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

    fc = [
        f"color=c=black:s={CANVAS_W}x{CANVAS_H}:r=30:d={D:.3f}[base]",
        f"color=c=black:s={CANVAS_W}x{ph}:r=30:d={D:.3f}[pbox]",
        f"color=c=black:s={CANVAS_W}x{vh}:r=30:d={D:.3f}[vbox]",
        f"[0:v]scale={psw}:{psh},setsar=1[pv]",
        f"[1:v]scale={vsw}:{vsh},setsar=1[vv]",
        f"[pbox][pv]overlay=x={px}:y={ppy}:eof_action=repeat[pb]",
        f"[vbox][vv]overlay=x={vx}:y={vvy}:eof_action=repeat[vb]",
        f"[base][pb]overlay=0:{py}[s1]",
        f"[s1][vb]overlay=0:{vy}[s2]",
    ]
    last = "s2"
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
    if task.get("p_audio"):
        audio_srcs.append("[0:a]")
    if task.get("v_audio") and not mute_viral:
        audio_srcs.append("[1:a]")
    amap = None
    if len(audio_srcs) == 2:
        fc.append(f"{audio_srcs[1]}{audio_srcs[0]}amix=inputs=2:duration=longest:normalize=0,volume={volume:.2f}[outa]")
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
