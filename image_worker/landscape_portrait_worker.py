"""
landscape_portrait_worker.py
将 16:9 横屏视频转换为 9:16 竖屏视频的后台工作线程
"""
import os
import sys
import re
import subprocess

from PyQt6.QtCore import QThread, pyqtSignal


# ── 分辨率对照表 ──────────────────────────────────────────────────────────────
RESOLUTION_MAP = {
    "540P (低)":    (540,  960),
    "720P (中)":    (720,  1280),
    "1K (默认)":   (1080, 1920),
    "2K":          (1440, 2560),
    "4K":          (2160, 3840),
}


class LandscapePortraitWorker(QThread):
    """
    信号：
      log_signal(str)                  — 实时日志
      progress_signal(int, int, str)   — (当前索引, 百分比, 状态文字)
      file_done_signal(int, bool, str) — (索引, 成功?, 消息)
      finished_signal(bool, str)       — (全部成功?, 汇总消息)
    """
    log_signal       = pyqtSignal(str)
    progress_signal  = pyqtSignal(int, int, str)
    file_done_signal = pyqtSignal(int, bool, str)
    finished_signal  = pyqtSignal(bool, str)

    def __init__(
        self,
        input_files:   list,
        output_dir:    str,
        output_names:  list,
        resolution:    str,
        y_offset:      int,
        bg_color1:     str,
        use_gradient:  bool,
        bg_color2:     str,
        ffmpeg_dir:    str,
    ):
        super().__init__()
        self.input_files  = input_files
        self.output_dir   = output_dir
        self.output_names = output_names
        self.resolution   = resolution
        self.y_offset     = y_offset
        self.bg_color1    = bg_color1
        self.use_gradient = use_gradient
        self.bg_color2    = bg_color2
        self.ffmpeg_dir   = ffmpeg_dir
        self._stop        = False
        self._proc        = None

    def stop(self):
        self._stop = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def _ffmpeg(self):
        if self.ffmpeg_dir and os.path.isdir(self.ffmpeg_dir):
            p = os.path.join(self.ffmpeg_dir, "ffmpeg.exe")
            if os.path.exists(p):
                return p
        return "ffmpeg"

    def _ffprobe(self):
        if self.ffmpeg_dir and os.path.isdir(self.ffmpeg_dir):
            p = os.path.join(self.ffmpeg_dir, "ffprobe.exe")
            if os.path.exists(p):
                return p
        return "ffprobe"

    def _get_duration(self, path):
        try:
            cmd = [
                self._ffprobe(), "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ]
            r = subprocess.run(
                cmd, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            return float(r.stdout.strip())
        except Exception:
            return 0.0

    def _build_cmd(self, in_path, out_path, out_w, out_h):
        scale_w = out_w
        scale_h = -2
        pad_x = "(ow-iw)/2"
        pad_y = f"(oh-ih)/2-({self.y_offset})"

        def to_ffmpeg_color(hex_str):
            return hex_str.replace("#", "0x")

        ffmpeg = self._ffmpeg()

        if not self.use_gradient:
            color = to_ffmpeg_color(self.bg_color1)
            vf = (
                f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=decrease,"
                f"pad={out_w}:{out_h}:{pad_x}:{pad_y}:color={color},"
                f"setsar=1"
            )
            cmd = [
                ffmpeg, "-y", "-i", in_path,
                "-vf", vf,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                out_path,
            ]
        else:
            c1 = to_ffmpeg_color(self.bg_color1)
            c2 = to_ffmpeg_color(self.bg_color2)
            grad_src = (
                f"gradients=s={out_w}x{out_h}"
                f":c0={c1}:c1={c2}"
                f":x0=0:y0=0:x1=0:y1={out_h}"
                f":nb_colors=2"
                f",format=yuv420p"
            )
            overlay_y = f"(H-h)/2-({self.y_offset})"
            filter_complex = (
                f"[0:v]scale={scale_w}:{scale_h}:force_original_aspect_ratio=decrease[scaled];"
                f"[1:v][scaled]overlay=(W-w)/2:{overlay_y}[out]"
            )
            cmd = [
                ffmpeg, "-y",
                "-i", in_path,
                "-f", "lavfi", "-i", grad_src,
                "-filter_complex", filter_complex,
                "-map", "[out]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                "-movflags", "+faststart",
                out_path,
            ]
        return cmd

    def run(self):
        total     = len(self.input_files)
        succeeded = 0
        failed    = 0

        out_w, out_h = RESOLUTION_MAP.get(self.resolution, (1080, 1920))
        os.makedirs(self.output_dir, exist_ok=True)

        for idx, (in_path, out_name) in enumerate(zip(self.input_files, self.output_names)):
            if self._stop:
                break

            self.log_signal.emit(f"\n[{idx+1}/{total}] 处理: {os.path.basename(in_path)}")
            self.progress_signal.emit(idx, 0, f"处理第 {idx+1}/{total} 个...")

            out_path = os.path.join(self.output_dir, out_name + ".mp4")
            duration = self._get_duration(in_path)
            if duration <= 0:
                duration = 60.0

            cmd = self._build_cmd(in_path, out_path, out_w, out_h)
            self.log_signal.emit(f"  命令: {' '.join(cmd)}")

            try:
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                self._proc = subprocess.Popen(
                    cmd,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=flags,
                )

                for line in self._proc.stderr:
                    if self._stop:
                        self._proc.terminate()
                        break
                    line = line.strip()
                    m = re.search(r"time=(\d+):(\d+):([\d.]+)", line)
                    if m and duration > 0:
                        h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                        elapsed = h * 3600 + mn * 60 + s
                        pct = min(int(elapsed / duration * 100), 99)
                        self.progress_signal.emit(idx, pct, f"转换中 {pct}%")

                self._proc.wait()
                retcode = self._proc.returncode

                if self._stop:
                    self.file_done_signal.emit(idx, False, "已停止")
                    break
                elif retcode == 0:
                    succeeded += 1
                    self.progress_signal.emit(idx, 100, "✅ 完成")
                    self.file_done_signal.emit(idx, True, "✅ 转换完成")
                    self.log_signal.emit(f"  ✅ 完成 → {out_path}")
                else:
                    failed += 1
                    self.file_done_signal.emit(idx, False, f"❌ 转换失败 (code={retcode})")
                    self.log_signal.emit(f"  ❌ 失败 code={retcode}")

            except FileNotFoundError:
                failed += 1
                self.file_done_signal.emit(idx, False, "❌ 找不到 FFmpeg")
                self.log_signal.emit('  ❌ 找不到 FFmpeg，请在"下载必要组件"中安装')
                break
            except Exception as e:
                failed += 1
                self.file_done_signal.emit(idx, False, f"❌ 异常: {e}")
                self.log_signal.emit(f"  ❌ 异常: {e}")

        if self._stop:
            self.finished_signal.emit(False, f"已停止。完成 {succeeded} 个，失败 {failed} 个。")
        else:
            ok = (failed == 0)
            self.finished_signal.emit(ok, f"全部完成！{succeeded} 个成功，{failed} 个失败。")
