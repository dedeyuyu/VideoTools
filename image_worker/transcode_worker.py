# -*- coding: utf-8 -*-
"""
transcode_worker.py
视频批量转码 Worker：
将各种不兼容的视频（如 HEVC/H.265、10-bit、AV1、VP9、VFR 可变帧率、时间戳异常、奇数分辨率、特殊音频编码、无音轨等）
批量转码为全平台/全软件通用的标准 H.264 (yuv420p) + AAC + 恒定帧率 (CFR) + faststart 视频，
输出文件严格保持原视频文件名。
"""
import os
import sys
import re
import json
import shutil
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal

VIDEO_EXTS = {
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm",
    ".ts", ".m4v", ".mpg", ".mpeg", ".3gp", ".f4v", ".mts", ".m2ts", ".vob", ".ogv"
}


def probe_video_info(ffprobe_bin: str, path: str) -> dict:
    """探测视频时长、分辨率、视频编码、像素格式、帧率、是否有音频及音频编码。"""
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    info = {
        "duration": 0.0,
        "width": 0,
        "height": 0,
        "vcodec": "",
        "pix_fmt": "",
        "fps": 0.0,
        "has_audio": False,
        "acodec": "",
    }
    try:
        r = subprocess.run(
            [
                ffprobe_bin, "-v", "error",
                "-show_entries", "format=duration:stream=index,codec_type,codec_name,width,height,pix_fmt,r_frame_rate,avg_frame_rate",
                "-of", "json", path
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=flags, timeout=15
        )
        data = json.loads(r.stdout or "{}")
        fmt = data.get("format") or {}
        if fmt.get("duration"):
            try:
                info["duration"] = float(fmt["duration"])
            except Exception:
                pass
        for st in data.get("streams") or []:
            ctype = st.get("codec_type")
            if ctype == "video" and not info["vcodec"]:
                info["vcodec"] = st.get("codec_name", "")
                info["width"] = int(st.get("width") or 0)
                info["height"] = int(st.get("height") or 0)
                info["pix_fmt"] = st.get("pix_fmt", "")
                fps_raw = st.get("avg_frame_rate") or st.get("r_frame_rate") or ""
                if "/" in fps_raw:
                    num, den = fps_raw.split("/", 1)
                    try:
                        if float(den) > 0:
                            info["fps"] = round(float(num) / float(den), 3)
                    except Exception:
                        pass
            elif ctype == "audio" and not info["has_audio"]:
                info["has_audio"] = True
                info["acodec"] = st.get("codec_name", "")
    except Exception:
        pass
    return info


class TranscodeWorker(QThread):
    log_signal       = pyqtSignal(str)
    progress_signal  = pyqtSignal(int, int, str)     # (索引, 百分比, 状态文字)
    file_done_signal = pyqtSignal(int, bool, str)    # (索引, 成功与否, 状态描述)
    finished_signal  = pyqtSignal(bool, str)         # (全部成功与否, 汇总信息)

    def __init__(self, input_files: list[str], output_dir: str, options: dict, ffmpeg_dir: str = ""):
        super().__init__()
        self.input_files = input_files
        self.output_dir = output_dir
        self.options = options or {}
        self.ffmpeg_dir = ffmpeg_dir
        self._stop = False
        self._proc = None

    def stop(self):
        self._stop = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def _bin(self, name: str) -> str:
        if self.ffmpeg_dir and os.path.isdir(self.ffmpeg_dir):
            p = os.path.join(self.ffmpeg_dir, name + ".exe")
            if os.path.exists(p):
                return p
        return name

    def _detect_gpu_encoder(self) -> str:
        """检测可用的 H.264 硬件编码器，无则返回 libx264。"""
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        ffmpeg = self._bin("ffmpeg")
        for enc in ("h264_nvenc", "h264_qsv", "h264_amf"):
            try:
                r = subprocess.run(
                    [ffmpeg, "-hide_banner", "-loglevel", "error",
                     "-f", "lavfi", "-i", "nullsrc=s=256x256:d=0.1",
                     "-c:v", enc, "-f", "null", "-"],
                    capture_output=True, text=True, creationflags=flags, timeout=8
                )
                if r.returncode == 0:
                    return enc
            except Exception:
                pass
        return "libx264"

    def _build_vf(self, target_res: int) -> str:
        """构建视频滤镜链：可选缩放 + 强制偶数宽高 + 标准 yuv420p 像素格式。"""
        filters = []
        if target_res and target_res > 0:
            # 仅当长边超过目标分辨率或需要统一长边时按比例缩放，且保证偶数宽高
            filters.append(
                f"scale='if(gt(iw,ih),min(iw,{target_res}),-2)':'if(gt(iw,ih),-2,min(ih,{target_res}))'"
            )
        filters.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
        filters.append("format=yuv420p")
        return ",".join(filters)

    def _build_cmd(self, src: str, dst: str, info: dict, v_encoder: str, force_reencode: bool = False) -> list[str]:
        mode = self.options.get("mode", "compat")            # compat | hq | compress | remux
        target_res = int(self.options.get("target_res", 0))  # 0=原分辨率, 1920, 1280, 2560, 3840
        target_fps = int(self.options.get("target_fps", 0))  # 0=保持原帧率(CFR), 24, 25, 30, 60
        audio_mode = self.options.get("audio_mode", "aac")   # aac | copy | mute
        ensure_audio = bool(self.options.get("ensure_audio", True))
        out_ext = self.options.get("out_ext", ".mp4").lower()

        ffmpeg = self._bin("ffmpeg")
        has_audio = info.get("has_audio", False)

        # 极速重封装模式：仅当原视频已经是 h264 + yuv420p + 偶数宽高 + 不缩放不改帧率时才直接 copy
        can_remux = (
            mode == "remux"
            and not force_reencode
            and info.get("vcodec") == "h264"
            and info.get("pix_fmt") in ("yuv420p", "yuvj420p")
            and info.get("width", 0) % 2 == 0
            and info.get("height", 0) % 2 == 0
            and target_res == 0
            and target_fps == 0
        )

        cmd = [
            ffmpeg, "-y", "-hide_banner",
            "-fflags", "+genpts+igndts",
            "-i", src
        ]

        need_silent_audio = (not has_audio) and ensure_audio and (audio_mode != "mute")
        if need_silent_audio:
            cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

        if can_remux:
            cmd += ["-map", "0:v:0", "-c:v", "copy"]
        else:
            cmd += ["-map", "0:v:0"]
            vf = self._build_vf(target_res)
            cmd += ["-vf", vf]

            # 恒定帧率与时间戳修复
            cmd += ["-fps_mode", "cfr", "-avoid_negative_ts", "make_zero"]
            if target_fps > 0:
                cmd += ["-r", str(target_fps)]

            # 质量档位
            if mode == "hq":
                crf, br = "15", "12M"
            elif mode == "compress":
                crf, br = "24", "4M"
            else:
                crf, br = "18", "8M"

            if v_encoder == "h264_nvenc":
                cmd += ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", crf, "-b:v", "0", "-pix_fmt", "yuv420p"]
            elif v_encoder == "h264_qsv":
                cmd += ["-c:v", "h264_qsv", "-global_quality", crf, "-pix_fmt", "yuv420p"]
            elif v_encoder == "h264_amf":
                cmd += ["-c:v", "h264_amf", "-rc", "cqp", "-qp_i", crf, "-qp_p", crf, "-pix_fmt", "yuv420p"]
            else:
                cmd += [
                    "-c:v", "libx264", "-preset", "fast", "-crf", crf,
                    "-profile:v", "high", "-pix_fmt", "yuv420p"
                ]

        # 音频流处理
        if audio_mode == "mute":
            cmd += ["-an"]
        elif need_silent_audio:
            cmd += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", "-shortest"]
        elif has_audio:
            cmd += ["-map", "0:a:0"]
            if audio_mode == "copy" and info.get("acodec") == "aac":
                cmd += ["-c:a", "copy"]
            else:
                cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]
        else:
            cmd += ["-an"]

        if out_ext in (".mp4", ".mov", ".m4v"):
            cmd += ["-movflags", "+faststart"]

        cmd.append(dst)
        return cmd

    def _run_ffmpeg(self, cmd: list[str], idx: int, dur: float, flags: int) -> tuple[int, str]:
        err_lines = []
        self._proc = subprocess.Popen(
            cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", creationflags=flags
        )
        for line in self._proc.stderr:
            if self._stop:
                self._proc.terminate()
                break
            err_lines.append(line.rstrip())
            if len(err_lines) > 30:
                err_lines.pop(0)
            m = re.search(r"time=(\d+):(\d+):([\d.]+)", line)
            if m and dur > 0:
                t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                pct = min(int(t / dur * 100), 99)
                self.progress_signal.emit(idx, pct, f"转码中 {pct}%")
        self._proc.wait()
        return self._proc.returncode, "\n".join(err_lines[-8:])

    def run(self):
        total = len(self.input_files)
        ok_n = fail_n = 0
        os.makedirs(self.output_dir, exist_ok=True)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        use_gpu = bool(self.options.get("use_gpu", False))
        v_encoder = "libx264"
        if use_gpu:
            self.log_signal.emit("🔍 正在检测 GPU 硬件编码器...")
            v_encoder = self._detect_gpu_encoder()
            if v_encoder != "libx264":
                self.log_signal.emit(f"  ✅ 已启用 GPU 硬件加速: {v_encoder}")
            else:
                self.log_signal.emit("  ℹ️ 未检测到可用 GPU 编码器，使用标准 CPU (libx264) 编码")

        out_ext = self.options.get("out_ext", ".mp4").lower()
        if not out_ext.startswith("."):
            out_ext = "." + out_ext

        for idx, src in enumerate(self.input_files):
            if self._stop:
                break

            base_name = os.path.basename(src)
            stem = os.path.splitext(base_name)[0]
            final_out = os.path.join(self.output_dir, stem + out_ext)

            # 若输出路径与源文件路径完全一致，先写入临时文件，成功后替换原文件
            same_file = os.path.normcase(os.path.abspath(final_out)) == os.path.normcase(os.path.abspath(src))
            work_out = os.path.join(self.output_dir, f".transcode_tmp_{idx}_{stem}{out_ext}") if same_file else final_out

            self.log_signal.emit(f"\n[{idx + 1}/{total}] 正在转码: {base_name}")
            info = probe_video_info(self._bin("ffprobe"), src)
            dur = info.get("duration", 0.0)
            v_desc = f"{info.get('width', 0)}×{info.get('height', 0)} | {info.get('vcodec') or '未知'} ({info.get('pix_fmt') or '未知'}) | {info.get('fps') or '?'}fps"
            a_desc = f"音频: {info.get('acodec') or '有'}" if info.get("has_audio") else "无音轨"
            self.log_signal.emit(f"  📋 原视频信息: {v_desc} | {a_desc} | 时长 {dur:.1f}s")
            self.progress_signal.emit(idx, 1, "准备转码...")

            try:
                cmd = self._build_cmd(src, work_out, info, v_encoder, force_reencode=False)
                rc, err_tail = self._run_ffmpeg(cmd, idx, dur, flags)

                # 若 GPU 编码或极速重封装失败，自动回退到标准 libx264 重编码
                if not self._stop and rc != 0 and (v_encoder != "libx264" or self.options.get("mode") == "remux"):
                    self.log_signal.emit("  ⚠️ 首次尝试未通过，自动回退至标准 CPU (libx264) 兼容转码...")
                    cmd_fallback = self._build_cmd(src, work_out, info, "libx264", force_reencode=True)
                    rc, err_tail = self._run_ffmpeg(cmd_fallback, idx, dur, flags)

                if self._stop:
                    if same_file and os.path.exists(work_out):
                        try:
                            os.remove(work_out)
                        except Exception:
                            pass
                    self.file_done_signal.emit(idx, False, "⏹ 已停止")
                    break

                if rc == 0 and os.path.isfile(work_out) and os.path.getsize(work_out) > 0:
                    if same_file:
                        os.replace(work_out, final_out)
                    ok_n += 1
                    self.progress_signal.emit(idx, 100, "✅ 完成")
                    self.file_done_signal.emit(idx, True, f"✅ 转码完成 → {os.path.basename(final_out)}")
                    self.log_signal.emit(f"  ✅ 完成 → {final_out}")
                else:
                    if same_file and os.path.exists(work_out):
                        try:
                            os.remove(work_out)
                        except Exception:
                            pass
                    fail_n += 1
                    self.file_done_signal.emit(idx, False, f"❌ 失败 (code={rc})")
                    self.log_signal.emit(f"  ❌ 失败 (code={rc}):\n{err_tail}")
            except FileNotFoundError:
                fail_n += 1
                self.file_done_signal.emit(idx, False, "❌ 找不到 FFmpeg")
                self.log_signal.emit('  ❌ 找不到 FFmpeg，请在左下角「📦 下载必要组件」中安装')
                break
            except Exception as e:
                fail_n += 1
                self.file_done_signal.emit(idx, False, f"❌ 异常: {e}")
                self.log_signal.emit(f"  ❌ 异常: {e}")

        if self._stop:
            self.finished_signal.emit(False, f"已停止。成功 {ok_n} 个，失败 {fail_n} 个。")
        else:
            self.finished_signal.emit(fail_n == 0, f"全部转码完成！成功 {ok_n} 个，失败 {fail_n} 个。")
