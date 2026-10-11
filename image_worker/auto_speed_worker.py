"""
auto_speed_worker.py
自动调速：给视频加速；可选“保持在3分钟以内”，超长视频自动提速到 < 3 分钟。
"""
import os
import sys
import re
import subprocess

from PyQt6.QtCore import QThread, pyqtSignal

# 目标上限：2分58.5秒，留出编码误差，保证最终 < 3:00（不超过 2:59）
MAX_TARGET_SEC = 178.5


def calc_speed(duration: float, user_speed: float, keep_3min: bool) -> float:
    """根据时长、用户速度、是否限制 3 分钟，计算最终速度倍数。"""
    speed = max(0.1, float(user_speed))
    if keep_3min and duration > 0:
        if duration / speed > MAX_TARGET_SEC:
            speed = duration / MAX_TARGET_SEC
    return speed


def atempo_chain(speed: float) -> str:
    """atempo 单个滤镜范围 0.5~2.0，超出需要串联。"""
    parts = []
    s = speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.6f}")
    return ",".join(parts)


class AutoSpeedWorker(QThread):
    log_signal       = pyqtSignal(str)
    progress_signal  = pyqtSignal(int, int, str)     # (索引, 百分比, 文字)
    file_done_signal = pyqtSignal(int, bool, str)
    finished_signal  = pyqtSignal(bool, str)

    def __init__(self, input_files, output_dir, output_names, speed,
                 keep_3min, ffmpeg_dir=""):
        super().__init__()
        self.input_files = input_files
        self.output_dir = output_dir
        self.output_names = output_names
        self.speed = speed
        self.keep_3min = keep_3min
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

    def _bin(self, name):
        if self.ffmpeg_dir and os.path.isdir(self.ffmpeg_dir):
            p = os.path.join(self.ffmpeg_dir, name + ".exe")
            if os.path.exists(p):
                return p
        return name

    def _probe(self, path):
        """返回 (duration, has_audio)。"""
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        dur, has_audio = 0.0, False
        try:
            r = subprocess.run(
                [self._bin("ffprobe"), "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, creationflags=flags)
            dur = float(r.stdout.strip())
        except Exception:
            pass
        try:
            r = subprocess.run(
                [self._bin("ffprobe"), "-v", "error", "-select_streams", "a",
                 "-show_entries", "stream=index", "-of", "csv=p=0", path],
                capture_output=True, text=True, creationflags=flags)
            has_audio = bool(r.stdout.strip())
        except Exception:
            pass
        return dur, has_audio

    def run(self):
        total = len(self.input_files)
        ok_n = fail_n = 0
        os.makedirs(self.output_dir, exist_ok=True)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        for idx, (src, name) in enumerate(zip(self.input_files, self.output_names)):
            if self._stop:
                break
            self.log_signal.emit(f"\n[{idx+1}/{total}] 处理: {os.path.basename(src)}")
            dur, has_audio = self._probe(src)
            speed = calc_speed(dur, self.speed, self.keep_3min)
            out_dur = dur / speed if dur > 0 else 0
            self.log_signal.emit(
                f"  原时长 {dur:.1f}s，最终速度 {speed:.3f}x，预计输出 {out_dur:.1f}s")

            out_path = os.path.join(self.output_dir, name + ".mp4")
            cmd = [self._bin("ffmpeg"), "-y", "-i", src,
                   "-filter:v", f"setpts=PTS/{speed:.6f}"]
            if has_audio:
                cmd += ["-filter:a", atempo_chain(speed), "-c:a", "aac", "-b:a", "192k"]
            else:
                cmd += ["-an"]
            cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-movflags", "+faststart", out_path]

            try:
                self._proc = subprocess.Popen(
                    cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    text=True, encoding="utf-8", errors="replace", creationflags=flags)
                for line in self._proc.stderr:
                    if self._stop:
                        self._proc.terminate()
                        break
                    m = re.search(r"time=(\d+):(\d+):([\d.]+)", line)
                    if m and out_dur > 0:
                        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                        pct = min(int(t / out_dur * 100), 99)
                        self.progress_signal.emit(idx, pct, f"调速中 {pct}%")
                self._proc.wait()
                rc = self._proc.returncode
                if self._stop:
                    self.file_done_signal.emit(idx, False, "已停止")
                    break
                if rc == 0:
                    ok_n += 1
                    self.progress_signal.emit(idx, 100, "✅ 完成")
                    self.file_done_signal.emit(idx, True, f"✅ 完成 ({speed:.2f}x)")
                    self.log_signal.emit(f"  ✅ 完成 → {out_path}")
                else:
                    fail_n += 1
                    self.file_done_signal.emit(idx, False, f"❌ 失败 (code={rc})")
                    self.log_signal.emit(f"  ❌ 失败 code={rc}")
            except FileNotFoundError:
                fail_n += 1
                self.file_done_signal.emit(idx, False, "❌ 找不到 FFmpeg")
                self.log_signal.emit('  ❌ 找不到 FFmpeg，请在"下载必要组件"中安装')
                break
            except Exception as e:
                fail_n += 1
                self.file_done_signal.emit(idx, False, f"❌ 异常: {e}")
                self.log_signal.emit(f"  ❌ 异常: {e}")

        if self._stop:
            self.finished_signal.emit(False, f"已停止。完成 {ok_n} 个，失败 {fail_n} 个。")
        else:
            self.finished_signal.emit(fail_n == 0, f"全部完成！{ok_n} 个成功，{fail_n} 个失败。")
