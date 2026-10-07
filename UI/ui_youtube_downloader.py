import os
import sys
import subprocess
import re
import shutil
import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QComboBox, QSpinBox, QFileDialog, QFrame,
    QProgressBar, QListWidget, QListWidgetItem, QAbstractSpinBox,
    QScrollArea, QSizePolicy, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QFont, QColor


# ─────────────────────────────────────────────────────────────────────────────
#  工具函数：探测 Node.js / Deno / yt-dlp 路径
# ─────────────────────────────────────────────────────────────────────────────

def _find_exe(name: str) -> str:
    """返回可执行文件的完整路径，优先查找项目根目录，找不到再回退系统 PATH。"""
    # 优先：项目根目录（本文件位于 UI/，根目录在上一级）
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local = os.path.join(root, name + (".exe" if sys.platform == "win32" else ""))
    if os.path.isfile(local):
        return local
    return shutil.which(name) or ""


def _ytdlp_version() -> str:
    exe = _find_exe("yt-dlp")
    if not exe:
        return ""
    try:
        r = subprocess.run(
            [exe, "--version"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def _node_path() -> str:
    """返回 node 可执行文件路径，找不到返回空字符串。"""
    return _find_exe("node")


# ─────────────────────────────────────────────────────────────────────────────
#  yt-dlp 更新线程
# ─────────────────────────────────────────────────────────────────────────────

class UpdateWorker(QThread):
    """在后台线程中执行 pip install --upgrade yt-dlp。"""
    log_line  = pyqtSignal(str)
    finished  = pyqtSignal(bool, str)   # (success, new_version)

    def run(self):
        self.log_line.emit("[UPDATE] 正在升级 yt-dlp，请稍候...")
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            for line in proc.stdout:
                self.log_line.emit(f"[pip] {line.rstrip()}")
            proc.wait()
            if proc.returncode == 0:
                ver = _ytdlp_version()
                self.finished.emit(True, ver)
            else:
                self.finished.emit(False, "")
        except Exception as e:
            self.finished.emit(False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
#  下载工作线程
# ─────────────────────────────────────────────────────────────────────────────

class YtdlpWorker(QThread):
    """在后台线程中逐条下载 YouTube 链接，实时回报进度。"""

    item_progress   = pyqtSignal(int, str, int)   # (idx, text, pct)
    item_done       = pyqtSignal(int, bool, str)  # (idx, ok, msg)
    overall_progress= pyqtSignal(int, str)         # (pct, text)
    all_done        = pyqtSignal(bool, str)        # (ok, msg)
    log_line        = pyqtSignal(str)              # raw log

    def __init__(self, urls: list[str], fmt: str, quality: str,
                 threads: int, output_dir: str, ffmpeg_dir: str,
                 node_path: str):
        super().__init__()
        self.urls       = urls
        self.fmt        = fmt
        self.quality    = quality
        self.threads    = threads
        self.output_dir = output_dir
        self.ffmpeg_dir = ffmpeg_dir
        self.node_path  = node_path
        self._stop_flag   = False
        self._current_proc= None

    def stop(self):
        self._stop_flag = True
        if self._current_proc and self._current_proc.poll() is None:
            self._current_proc.terminate()

    # ------------------------------------------------------------------
    def _build_args(self) -> list[str]:
        args = [_find_exe("yt-dlp") or "yt-dlp", "--newline", "--no-playlist", "--no-update"]

        # ffmpeg 路径
        if self.ffmpeg_dir and os.path.isdir(self.ffmpeg_dir):
            args += ["--ffmpeg-location", self.ffmpeg_dir]

        # Node.js JS 运行时（避免 "No supported JavaScript runtime" 警告）
        if self.node_path:
            args += ["--js-runtimes", f"node:{self.node_path}"]

        # 并发片段数
        args += ["--concurrent-fragments", str(self.threads)]

        # 输出模板
        out_template = os.path.join(self.output_dir, "%(title)s.%(ext)s")
        args += ["-o", out_template]

        if self.fmt == "MP3（仅音频）":
            args += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
        else:
            height_map = {
                "480p": "480", "720p": "720", "1080p": "1080",
                "2K (1440p)": "1440", "4K (2160p)": "2160",
            }
            h = height_map.get(self.quality, "1080")
            # 不在视频流上限定 ext，让 ffmpeg 负责格式转换
            fmt_sel = (
                f"bestvideo[height<={h}]+bestaudio[ext=m4a]/"
                f"bestvideo[height<={h}]+bestaudio/"
                f"best[height<={h}]/best"
            )
            args += ["-f", fmt_sel, "--merge-output-format", self.fmt]

        return args

    def _read_stderr(self, proc, stderr_lines: list):
        try:
            for line in proc.stderr:
                line = line.strip()
                if line:
                    stderr_lines.append(line)
                    self.log_line.emit(f"[ERR] {line}")
        except Exception:
            pass

    def run(self):
        total = len(self.urls)
        base_args = self._build_args()
        succeeded = failed = 0

        for idx, url in enumerate(self.urls):
            if self._stop_flag:
                break

            self.item_progress.emit(idx, "⏳ 正在连接...", 0)
            self.overall_progress.emit(int(idx / total * 100),
                                       f"正在下载第 {idx+1}/{total} 个...")
            self.log_line.emit(f"\n{'─'*60}")
            self.log_line.emit(f"[{idx+1}/{total}] 开始下载: {url}")

            cmd = base_args + [url]
            self.log_line.emit(f"[CMD] {' '.join(cmd)}")

            try:
                self._current_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )

                stderr_lines: list[str] = []
                t = threading.Thread(
                    target=self._read_stderr,
                    args=(self._current_proc, stderr_lines),
                    daemon=True,
                )
                t.start()

                last_pct = 0
                for line in self._current_proc.stdout:
                    if self._stop_flag:
                        self._current_proc.terminate()
                        break
                    line = line.strip()
                    if not line:
                        continue
                    self.log_line.emit(f"[OUT] {line}")

                    m = re.search(r"\[download\]\s+([\d.]+)%", line)
                    if m:
                        pct = min(int(float(m.group(1))), 100)
                        last_pct = pct
                        self.item_progress.emit(idx, f"⏳ 下载中 {pct}%", pct)
                        fine = (idx + pct / 100) / total * 100
                        self.overall_progress.emit(int(fine),
                            f"正在下载第 {idx+1}/{total} 个 ({pct}%)")
                    elif "[Merger]" in line or "Merging" in line:
                        self.item_progress.emit(idx, "🔧 合并中...", last_pct)
                    elif "[ExtractAudio]" in line or "Destination:" in line:
                        self.item_progress.emit(idx, "🎵 转码中...", last_pct)

                t.join(timeout=5)
                self._current_proc.wait()
                retcode = self._current_proc.returncode

                if self._stop_flag:
                    self.item_done.emit(idx, False, "已停止")
                    break
                elif retcode == 0:
                    succeeded += 1
                    self.item_done.emit(idx, True, "✅ 下载完成")
                else:
                    failed += 1
                    # 智能错误摘要：识别常见错误类型给出中文提示
                    err_text = " ".join(stderr_lines)
                    reason = _classify_error(err_text, retcode)
                    self.item_done.emit(idx, False, f"❌ {reason}")
                    self.log_line.emit(f"[FAIL] code={retcode} | {reason}")

            except FileNotFoundError:
                failed += 1
                self.item_done.emit(idx, False, "❌ 找不到 yt-dlp，请先安装")
                self.log_line.emit("[FAIL] 找不到 yt-dlp")
                break
            except Exception as e:
                failed += 1
                self.item_done.emit(idx, False, f"❌ 异常: {e}")
                self.log_line.emit(f"[FAIL] 异常: {e}")

        if self._stop_flag:
            self.all_done.emit(False, f"已停止。完成 {succeeded} 个，失败 {failed} 个。")
        else:
            self.overall_progress.emit(100, "全部完成！")
            self.all_done.emit(failed == 0,
                f"全部完成！{succeeded} 个成功，{failed} 个失败。")


def _classify_error(err_text: str, code: int) -> str:
    """将 yt-dlp 错误信息翻译为简洁的中文原因。"""
    t = err_text.lower()
    if "this video is not available" in t:
        return "视频不可用（可能地区限制或已下架）"
    if "private video" in t:
        return "私人视频，无法下载"
    if "sign in" in t or "login" in t:
        return "需要登录账号才能下载（年龄限制或会员内容）"
    if "copyright" in t:
        return "版权限制，该视频无法下载"
    if "no video formats" in t or "no formats" in t:
        return "找不到可用的视频格式（尝试更新 yt-dlp）"
    if "http error 429" in t:
        return "请求过于频繁（HTTP 429），请稍后再试"
    if "http error 403" in t:
        return "访问被拒绝（HTTP 403），可能需要 Cookie"
    if "network" in t or "connection" in t:
        return "网络连接失败"
    if "javascript" in t or "js runtime" in t:
        return "缺少 JS 运行时（Node.js），请安装后重试"
    if "unable to extract" in t:
        return "无法解析视频信息（请更新 yt-dlp）"
    # 兜底：返回最后一条错误行
    lines = [l.strip() for l in err_text.splitlines() if l.strip()]
    last = lines[-1] if lines else f"未知错误 (code {code})"
    return last[:100]


# ─────────────────────────────────────────────────────────────────────────────
#  主 UI 类
# ─────────────────────────────────────────────────────────────────────────────

class YouTubeDownloaderUI(QWidget):

    # 后台线程检测完毕后，通过此信号安全地更新主线程 UI
    _env_ready = pyqtSignal(str, str)   # (ytdlp_ver, node_path)

    def __init__(self):
        super().__init__()
        self.worker: YtdlpWorker | None = None
        self.update_worker: UpdateWorker | None = None
        self.output_dir = ""
        self.settings = QSettings("MyCompany", "VideoToolbox")
        self._item_widgets: dict[int, QListWidgetItem] = {}

        self._setup_ui()
        self._bind_events()
        self.load_settings()
        # 将信号连接到 UI 更新槽
        self._env_ready.connect(self._apply_env_labels)
        # 在后台守护线程中运行耗时的环境检测，主线程不阻塞
        import threading
        threading.Thread(target=self._refresh_env_status, daemon=True).start()

    # ── 设置持久化 ────────────────────────────────────────────────────────

    def load_settings(self):
        self.combo_format.setCurrentText(self.settings.value("yt_format", "mp4"))
        self.combo_quality.setCurrentText(self.settings.value("yt_quality", "1080p"))
        self.spin_threads.setValue(self.settings.value("yt_threads", 4, type=int))
        saved_dir = self.settings.value("yt_output_dir", "")
        if saved_dir and os.path.isdir(saved_dir):
            self.output_dir = saved_dir
            self.lbl_out_path.setText(f"已选择: {saved_dir}")
        self._on_format_changed()

    def save_settings(self):
        self.settings.setValue("yt_format",     self.combo_format.currentText())
        self.settings.setValue("yt_quality",    self.combo_quality.currentText())
        self.settings.setValue("yt_threads",    self.spin_threads.value())
        self.settings.setValue("yt_output_dir", self.output_dir)

    # ── 运行环境检测（在后台线程中运行，绝不阻塞主线程）────────────────────

    def _refresh_env_status(self):
        """在后台守护线程中检测 yt-dlp 版本和 Node.js，完成后通过信号更新 UI。"""
        ver  = _ytdlp_version()   # 可能耗时数秒，但不在主线程
        node = _node_path()       # shutil.which，极快
        self._env_ready.emit(ver, node)   # 安全地通知主线程更新 UI

    def _apply_env_labels(self, ver: str, node: str):
        """（主线程）收到信号后更新状态栏标签。"""
        if ver:
            self.lbl_ytdlp_ver.setText(f"yt-dlp {ver}")
            self.lbl_ytdlp_ver.setStyleSheet("color: #22c55e; font-size: 9pt; font-weight: bold;")
        else:
            self.lbl_ytdlp_ver.setText("yt-dlp 未安装")
            self.lbl_ytdlp_ver.setStyleSheet("color: #ef4444; font-size: 9pt; font-weight: bold;")

        if node:
            self.lbl_node_status.setText(f"✅ Node.js: {node}")
            self.lbl_node_status.setStyleSheet("color: #22c55e; font-size: 9pt;")
        else:
            self.lbl_node_status.setText("⚠️ Node.js 未安装（部分视频可能无法下载）")
            self.lbl_node_status.setStyleSheet("color: #f59e0b; font-size: 9pt;")

    # ── UI 构建 ───────────────────────────────────────────────────────────

    def _create_card(self, title: str):
        card = QFrame()
        card.setProperty("class", "Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        lbl = QLabel(title)
        lbl.setProperty("class", "CardTitle")
        layout.addWidget(lbl)
        return card, layout

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setAutoFillBackground(False)
        outer.addWidget(scroll)

        inner = QWidget()
        inner.setAutoFillBackground(False)
        scroll.setWidget(inner)
        main = QVBoxLayout(inner)
        main.setContentsMargins(0, 0, 1, 0)
        main.setSpacing(10)

        # ── 环境状态栏 ────────────────────────────────────────────────────
        env_card, env_lay = self._create_card("🛠 运行环境状态")
        env_row = QHBoxLayout()

        self.lbl_ytdlp_ver = QLabel("检测中...")
        self.lbl_ytdlp_ver.setStyleSheet("color: #6b7280; font-size: 9pt;")
        env_row.addWidget(self.lbl_ytdlp_ver)

        self.btn_update_ytdlp = QPushButton("⬆ 一键更新 yt-dlp")
        self.btn_update_ytdlp.setFixedWidth(160)
        self.btn_update_ytdlp.setToolTip("yt-dlp 版本超过 30 天建议更新，以支持最新 YouTube API")
        env_row.addWidget(self.btn_update_ytdlp)

        env_row.addSpacing(20)
        self.lbl_node_status = QLabel("检测中...")
        env_row.addWidget(self.lbl_node_status)

        env_row.addStretch()
        env_lay.addLayout(env_row)
        main.addWidget(env_card)

        # ── 板块一：链接输入 ──────────────────────────────────────────────
        card1, lay1 = self._create_card("🔗 板块一 · 输入 YouTube 链接（每行一个）")

        hint = QLabel("支持批量粘贴，每行一个链接。含播放列表参数（&list=...）的链接自动只下载单个视频。")
        hint.setStyleSheet("color: #6b7280; font-size: 9pt;")
        hint.setWordWrap(True)
        lay1.addWidget(hint)

        self.text_urls = QPlainTextEdit()
        self.text_urls.setPlaceholderText(
            "https://www.youtube.com/watch?v=xxxxxxx\n"
            "https://www.youtube.com/watch?v=yyyyyyy\n"
            "..."
        )
        self.text_urls.setMinimumHeight(140)
        self.text_urls.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay1.addWidget(self.text_urls)

        url_btn_row = QHBoxLayout()
        url_btn_row.addStretch()
        self.btn_clear_urls = QPushButton("🗑 清空链接")
        url_btn_row.addWidget(self.btn_clear_urls)
        lay1.addLayout(url_btn_row)
        main.addWidget(card1)

        # ── 板块二：参数设置 ──────────────────────────────────────────────
        card2, lay2 = self._create_card("⚙️ 板块二 · 下载参数设置")

        params_row1 = QHBoxLayout()
        params_row1.setSpacing(20)

        fmt_col = QVBoxLayout()
        fmt_col.setSpacing(4)
        fmt_col.addWidget(QLabel("输出格式："))
        self.combo_format = QComboBox()
        self.combo_format.addItems(["mp4", "mkv", "webm", "MP3（仅音频）"])
        self.combo_format.setMinimumWidth(160)
        fmt_col.addWidget(self.combo_format)
        params_row1.addLayout(fmt_col)

        qual_col = QVBoxLayout()
        qual_col.setSpacing(4)
        self.lbl_quality = QLabel("视频画质：")
        qual_col.addWidget(self.lbl_quality)
        self.combo_quality = QComboBox()
        self.combo_quality.addItems(["480p", "720p", "1080p", "2K (1440p)", "4K (2160p)"])
        self.combo_quality.setMinimumWidth(160)
        qual_col.addWidget(self.combo_quality)
        params_row1.addLayout(qual_col)

        thread_col = QVBoxLayout()
        thread_col.setSpacing(4)
        thread_col.addWidget(QLabel("并发线程数："))
        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 32)
        self.spin_threads.setValue(4)
        self.spin_threads.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.spin_threads.setMinimumWidth(100)
        thread_col.addWidget(self.spin_threads)
        params_row1.addLayout(thread_col)

        params_row1.addStretch()
        lay2.addLayout(params_row1)

        out_row = QHBoxLayout()
        self.btn_out_path = QPushButton("📁 选择输出目录")
        self.btn_out_path.setFixedWidth(150)
        self.lbl_out_path = QLabel("尚未选择输出目录")
        self.lbl_out_path.setStyleSheet("color: #6b7280;")
        out_row.addWidget(self.btn_out_path)
        out_row.addWidget(self.lbl_out_path, 1)
        lay2.addLayout(out_row)
        main.addWidget(card2)

        # ── 板块三：进度面板 ──────────────────────────────────────────────
        card3, lay3 = self._create_card("📊 板块三 · 下载进度")

        self.list_progress = QListWidget()
        self.list_progress.setMinimumHeight(160)
        self.list_progress.setAlternatingRowColors(False)
        self.list_progress.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list_progress.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lay3.addWidget(self.list_progress)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        lay3.addWidget(self.progress_bar)

        self.lbl_status = QLabel("就绪 — 请输入链接并点击「开始下载」")
        self.lbl_status.setStyleSheet("color: #6b7280; font-size: 9pt;")
        lay3.addWidget(self.lbl_status)

        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("🚀 开始下载")
        self.btn_start.setObjectName("PrimaryBtn")
        self.btn_start.setFixedHeight(46)
        self.btn_stop = QPushButton("🛑 停止下载")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setFixedHeight(46)
        self.btn_clear_log = QPushButton("🗑 清空日志")
        self.btn_clear_log.setFixedHeight(46)
        self.btn_clear_log.setFixedWidth(110)
        btn_row.addWidget(self.btn_start, stretch=3)
        btn_row.addWidget(self.btn_stop, stretch=1)
        btn_row.addWidget(self.btn_clear_log)
        lay3.addLayout(btn_row)
        main.addWidget(card3)

        # ── 板块四：详细日志 ──────────────────────────────────────────────
        card4, lay4 = self._create_card("🔍 板块四 · 详细日志（失败时可查看原因）")

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(180)
        self.log_view.setFont(QFont("Consolas", 9))
        self.log_view.setPlaceholderText("日志将在下载开始后显示...")
        self.log_view.setStyleSheet(
            "QPlainTextEdit { background-color: #0d1117; color: #c9d1d9; "
            "border: 1px solid #30363d; border-radius: 6px; padding: 6px; }"
        )
        lay4.addWidget(self.log_view)
        main.addWidget(card4)
        main.addStretch()

    # ── 事件绑定 ──────────────────────────────────────────────────────────

    def _bind_events(self):
        self.btn_clear_urls.clicked.connect(self.text_urls.clear)
        self.btn_out_path.clicked.connect(self._select_output_dir)
        self.btn_start.clicked.connect(self._start_download)
        self.btn_stop.clicked.connect(self._stop_download)
        self.btn_clear_log.clicked.connect(self.log_view.clear)
        self.combo_format.currentTextChanged.connect(self._on_format_changed)
        self.btn_update_ytdlp.clicked.connect(self._update_ytdlp)

    # ── 槽函数 ────────────────────────────────────────────────────────────

    def _on_format_changed(self, _=None):
        is_audio = self.combo_format.currentText() == "MP3（仅音频）"
        self.combo_quality.setEnabled(not is_audio)
        self.lbl_quality.setEnabled(not is_audio)

    def _select_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.output_dir = d
            self.lbl_out_path.setText(f"已选择: {d}")
            self.lbl_out_path.setStyleSheet("")

    def _get_urls(self) -> list[str]:
        raw = self.text_urls.toPlainText().strip()
        return [u.strip() for u in raw.splitlines() if u.strip()]

    # ── 更新 yt-dlp ───────────────────────────────────────────────────────

    def _update_ytdlp(self):
        self.btn_update_ytdlp.setEnabled(False)
        self.btn_update_ytdlp.setText("更新中...")
        self.log_view.clear()
        self.update_worker = UpdateWorker()
        self.update_worker.log_line.connect(self._on_log_line)
        self.update_worker.finished.connect(self._on_update_done)
        self.update_worker.start()

    def _on_update_done(self, success: bool, version: str):
        self.btn_update_ytdlp.setEnabled(True)
        self.btn_update_ytdlp.setText("⬆ 一键更新 yt-dlp")
        self._refresh_env_status()
        if success:
            self._on_log_line(f"[UPDATE] ✅ 更新成功，当前版本：{version}")
            QMessageBox.information(self, "更新完成", f"yt-dlp 已更新至 {version}")
        else:
            self._on_log_line("[UPDATE] ❌ 更新失败，请查看日志")

    # ── 开始下载 ──────────────────────────────────────────────────────────

    def _start_download(self):
        urls = self._get_urls()
        if not urls:
            QMessageBox.warning(self, "提示", "请先输入至少一个 YouTube 链接！")
            return
        if not self.output_dir:
            QMessageBox.warning(self, "提示", "请先选择输出目录！")
            return

        self.list_progress.clear()
        self._item_widgets.clear()
        self.log_view.clear()

        for idx, url in enumerate(urls):
            short = url if len(url) <= 60 else url[:57] + "..."
            item = QListWidgetItem(f"  [{idx+1:02d}]  {short}  —  ⏳ 等待中")
            item.setFont(QFont("Consolas", 9))
            self.list_progress.addItem(item)
            self._item_widgets[idx] = item

        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"准备下载 {len(urls)} 个视频...")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        if getattr(sys, 'frozen', False):
            _root = os.path.dirname(sys.executable)
        else:
            _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ffmpeg_dir = os.path.join(_root, "ffmpeg")
        if not os.path.isdir(ffmpeg_dir):
            ffmpeg_dir = ""

        self.worker = YtdlpWorker(
            urls=urls,
            fmt=self.combo_format.currentText(),
            quality=self.combo_quality.currentText(),
            threads=self.spin_threads.value(),
            output_dir=self.output_dir,
            ffmpeg_dir=ffmpeg_dir,
            node_path=_node_path(),
        )
        self.worker.item_progress.connect(self._on_item_progress)
        self.worker.item_done.connect(self._on_item_done)
        self.worker.overall_progress.connect(self._on_overall_progress)
        self.worker.all_done.connect(self._on_all_done)
        self.worker.log_line.connect(self._on_log_line)
        self.worker.start()

    def _stop_download(self):
        if self.worker:
            self.worker.stop()
            self.lbl_status.setText("正在停止，请稍候...")
            self.btn_stop.setEnabled(False)

    # ── Worker 信号槽 ─────────────────────────────────────────────────────

    def _on_item_progress(self, idx: int, text: str, pct: int):
        item = self._item_widgets.get(idx)
        if not item:
            return
        urls = self._get_urls()
        url = urls[idx] if idx < len(urls) else ""
        short = url if len(url) <= 55 else url[:52] + "..."
        item.setText(f"  [{idx+1:02d}]  {short}  —  {text}")

    def _on_item_done(self, idx: int, success: bool, msg: str):
        item = self._item_widgets.get(idx)
        if not item:
            return
        urls = self._get_urls()
        url = urls[idx] if idx < len(urls) else ""
        short = url if len(url) <= 55 else url[:52] + "..."
        item.setText(f"  [{idx+1:02d}]  {short}  —  {msg}")
        item.setForeground(Qt.GlobalColor.green if success else Qt.GlobalColor.red)
        self.list_progress.scrollToItem(item)

    def _on_overall_progress(self, pct: int, text: str):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(text)

    def _on_log_line(self, line: str):
        self.log_view.appendPlainText(line)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_all_done(self, success: bool, message: str):
        self.progress_bar.setValue(100 if success else self.progress_bar.value())
        self.lbl_status.setText(message)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if success:
            QMessageBox.information(self, "完成", message)
        else:
            QMessageBox.warning(self, "下载结束", message)
