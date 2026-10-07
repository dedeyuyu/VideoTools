# screenshot_worker.py
"""
后台工作线程：链接批量下载 → 分帧截图
支持可选保存视频文件 / 提取并保存音频文件
支持 Cookie 登录（自动重试 / 始终使用）
"""

import os
import sys
import re
import shutil
import subprocess
import threading

from PyQt6.QtCore import QThread, pyqtSignal


class ScreenshotWorker(QThread):
    """
    信号：
      log_signal(str)              — 实时日志（追加到日志区）
      progress_signal(int, str)    — 总体进度百分比 + 状态文字
      finished_signal(bool, str)   — 完成：(success, message)
    """

    log_signal      = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(
        self,
        urls:            list,
        max_count:       int,
        interval:        float,
        base_path:       str,
        base_folder_name: str,
        save_video:      bool,
        save_audio:      bool,
        ffmpeg_dir:      str,
        cookie_file:     str = "",      # Cookie .txt 文件路径（Netscape 格式）
        cookie_mode:     str = "none",  # "none" / "auto" / "always"
    ):
        super().__init__()
        self.urls             = urls
        self.max_count        = max_count
        self.interval         = interval
        self.base_path        = base_path
        self.base_folder_name = base_folder_name
        self.save_video       = save_video
        self.save_audio       = save_audio
        self.ffmpeg_dir       = ffmpeg_dir          # 包含 ffmpeg.exe 的目录
        self.cookie_file      = cookie_file          # Cookie 文件路径
        self.cookie_mode      = cookie_mode          # Cookie 使用模式
        self._stop_event      = threading.Event()
        self._current_proc    = None                # 当前正在运行的子进程

    # ── 公共方法 ──────────────────────────────────────────────────────────

    def stop(self):
        """从主线程调用以请求停止"""
        self._stop_event.set()
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.terminate()
            except Exception:
                pass

    # ── 内部辅助 ──────────────────────────────────────────────────────────

    def _log(self, msg: str):
        self.log_signal.emit(msg)

    def _progress(self, pct: int, text: str):
        self.progress_signal.emit(pct, text)

    def _ffmpeg_exe(self) -> str:
        """返回 ffmpeg.exe 完整路径"""
        if self.ffmpeg_dir and os.path.isdir(self.ffmpeg_dir):
            candidate = os.path.join(self.ffmpeg_dir, "ffmpeg.exe")
            if os.path.exists(candidate):
                return candidate
        return "ffmpeg"  # 回退到系统 PATH

    def _creationflags(self) -> int:
        return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    # ── 下载 ──────────────────────────────────────────────────────────────

    def _ytdlp_exe(self) -> str:
        """返回 yt-dlp 可执行文件路径，优先使用项目根目录中的版本。"""
        # 本文件位于 image_worker/，项目根目录在上一级
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        local = os.path.join(root, "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp")
        if os.path.isfile(local):
            return local
        found = shutil.which("yt-dlp")
        return found or "yt-dlp"

    def _download_video(self, url: str, temp_dir: str, cookie_file: str = ""):
        """
        使用 yt-dlp CLI 下载视频，返回下载后的文件路径（字符串），失败返回 None。
        下载过程中实时发送日志（进度行）。
        可选传入 cookie_file 覆盖实例的 cookie_file。
        """
        out_template = os.path.join(temp_dir, "%(id)s.%(ext)s")
        args = [
            self._ytdlp_exe(),
            "--newline",
            "--no-playlist",
            "-f", "best",
            "-o", out_template,
        ]

        # 让 yt-dlp 使用项目内的 ffmpeg
        if self.ffmpeg_dir and os.path.isdir(self.ffmpeg_dir):
            args += ["--ffmpeg-location", self.ffmpeg_dir]

        # 加入 Cookie 参数
        effective_cookie = cookie_file or ""
        if effective_cookie and os.path.isfile(effective_cookie):
            args += ["--cookies", effective_cookie]

        args.append(url)

        try:
            self._current_proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=self._creationflags(),
            )

            filename = None
            for line in self._current_proc.stdout:
                if self._stop_event.is_set():
                    self._current_proc.terminate()
                    break
                line = line.strip()

                # 捕获进度行
                m = re.search(r"\[download\]\s+([\d.]+)%", line)
                if m:
                    pct = int(float(m.group(1)))
                    self._log(f"    ⏬ 下载进度 {pct}%")

                # 捕获目标文件路径
                dest_m = re.search(r"\[download\] Destination: (.+)$", line)
                if dest_m:
                    filename = dest_m.group(1).strip()

                merger_m = re.search(r"\[Merger\] Merging formats into \"(.+)\"", line)
                if merger_m:
                    filename = merger_m.group(1).strip()

            self._current_proc.wait()
            if self._current_proc.returncode != 0 or self._stop_event.is_set():
                return None

            # 如果捕获到路径就直接使用，否则扫描临时目录
            if filename and os.path.exists(filename):
                return filename

            # 兜底：扫描 temp_dir 找最新下载的文件
            video_exts = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".ts"}
            candidates = [
                os.path.join(temp_dir, f)
                for f in os.listdir(temp_dir)
                if os.path.splitext(f)[1].lower() in video_exts
            ]
            if candidates:
                return max(candidates, key=os.path.getmtime)

            return None

        except FileNotFoundError:
            self._log("    ❌ 找不到 yt-dlp，请确保已安装（pip install yt-dlp）")
            return None
        except Exception as e:
            self._log(f"    ❌ 下载出错: {e}")
            return None

    # ── 截图 ──────────────────────────────────────────────────────────────

    def _extract_frames(self, video_path: str, output_folder: str) -> bool:
        """使用 ffmpeg 对视频分帧截图，图片保存到 output_folder。"""
        try:
            fps = 1.0 / float(self.interval)
            output_pattern = os.path.join(output_folder, "%02d.jpg")

            cmd = [
                self._ffmpeg_exe(),
                "-ss", "0.3",
                "-i", video_path,
                "-vf", f"fps={fps}",
                "-vframes", str(self.max_count),
                output_pattern,
                "-y",
            ]

            self._current_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=self._creationflags(),
            )

            for line in self._current_proc.stdout:
                if self._stop_event.is_set():
                    self._current_proc.terminate()
                    break

            self._current_proc.wait()
            return self._current_proc.returncode == 0 and not self._stop_event.is_set()

        except Exception as e:
            self._log(f"    ❌ 截图出错: {e}")
            return False

    # ── 提取音频 ──────────────────────────────────────────────────────────

    def _extract_audio(self, video_path: str, output_folder: str, stem: str) -> bool:
        """使用 ffmpeg 从视频中提取音频，保存为 mp3。"""
        try:
            out_path = os.path.join(output_folder, f"{stem}_audio.mp3")
            cmd = [
                self._ffmpeg_exe(),
                "-i", video_path,
                "-vn",
                "-acodec", "libmp3lame",
                "-q:a", "2",
                out_path,
                "-y",
            ]
            self._current_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=self._creationflags(),
            )
            for line in self._current_proc.stdout:
                if self._stop_event.is_set():
                    self._current_proc.terminate()
                    break

            self._current_proc.wait()
            ok = self._current_proc.returncode == 0 and not self._stop_event.is_set()
            if ok:
                self._log(f"    🎵 音频已保存: {out_path}")
            return ok
        except Exception as e:
            self._log(f"    ❌ 提取音频出错: {e}")
            return False

    # ── 主流程 ────────────────────────────────────────────────────────────

    def run(self):
        total = len(self.urls)
        temp_dir = os.path.join(self.base_path, "_temp_screenshot_downloads")
        os.makedirs(temp_dir, exist_ok=True)

        success_count = 0
        failed_count  = 0

        for idx, url in enumerate(self.urls):
            if self._stop_event.is_set():
                self._log("🛑 收到停止指令，已中断任务。")
                break

            url = url.strip()
            if not url:
                continue

            # 更新总体进度
            overall_pct = int(idx / total * 100)
            self._progress(overall_pct, f"正在处理第 {idx + 1}/{total} 个链接...")
            self._log(f"\n{'─' * 50}")
            self._log(f"▶  [{idx + 1}/{total}]  {url}")

            # 输出文件夹（每个链接独立子目录）
            folder_name   = f"{self.base_folder_name}_{idx + 1:03d}"
            output_folder = os.path.join(self.base_path, folder_name)
            os.makedirs(output_folder, exist_ok=True)

            # ── 下载（含 Cookie 重试逻辑） ────────────────────────────
            self._log("    ⏬ 正在下载视频...")

            if self.cookie_mode == "always" and self.cookie_file:
                # 始终带 Cookie 下载
                self._log("    🍪 使用 Cookie 下载...")
                video_path = self._download_video(url, temp_dir, cookie_file=self.cookie_file)
            else:
                # 先不带 Cookie 尝试
                video_path = self._download_video(url, temp_dir)
                if video_path is None and self.cookie_mode == "auto" and self.cookie_file:
                    # 失败后用 Cookie 重试
                    self._log("    🍪 首次下载失败，正在使用 Cookie 重试...")
                    video_path = self._download_video(url, temp_dir, cookie_file=self.cookie_file)

            if self._stop_event.is_set():
                self._log("🛑 下载完成后检测到停止指令，中断。")
                if video_path and os.path.exists(video_path):
                    try:
                        os.remove(video_path)
                    except Exception:
                        pass
                break

            if not video_path:
                self._log("    ❌ 下载失败，跳过此链接。")
                failed_count += 1
                continue

            self._log("    ✅ 下载成功！")
            video_stem = os.path.splitext(os.path.basename(video_path))[0]

            # ── 保存视频（可选）──────────────────────────────────────
            if self.save_video:
                dest_video = os.path.join(
                    output_folder,
                    os.path.basename(video_path),
                )
                try:
                    shutil.copy2(video_path, dest_video)
                    self._log(f"    🎬 视频已保存: {dest_video}")
                except Exception as e:
                    self._log(f"    ⚠️  保存视频失败: {e}")

            # ── 提取并保存音频（可选）────────────────────────────────
            if self.save_audio:
                self._log("    🎵 正在提取音频...")
                self._extract_audio(video_path, output_folder, video_stem)
                if self._stop_event.is_set():
                    break

            # ── 分帧截图 ──────────────────────────────────────────────
            self._log(f"    📸 正在截图（数量={self.max_count}, 间隔={self.interval}s）...")
            ok = self._extract_frames(video_path, output_folder)

            # ── 清理临时视频（无论是否保存） ──────────────────────────
            try:
                os.remove(video_path)
            except Exception:
                pass

            if ok:
                success_count += 1
                self._log(f"    ✅ 截图完成  →  {output_folder}")
            else:
                failed_count += 1
                self._log("    ❌ 截图失败。")

        # ── 清理临时目录 ────────────────────────────────────────────────
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

        # ── 完成信号 ────────────────────────────────────────────────────
        self._progress(100, "全部完成！")
        summary = f"任务结束。✅ 成功 {success_count} 个 | ❌ 失败 {failed_count} 个"
        self._log(f"\n{'═' * 50}")
        self._log(f"🎉 {summary}")
        all_ok = (failed_count == 0) and not self._stop_event.is_set()
        self.finished_signal.emit(all_ok, summary)
