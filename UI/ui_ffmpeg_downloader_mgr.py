import os
import sys
import subprocess
import zipfile
import urllib.request
import urllib.error
import ssl

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QScrollArea, QWidget
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt


# ── 下载源（FFmpeg）──────────────────────────────────────────────────────────

_FFMPEG_SOURCES = [
    {
        "name": "GitHub (BtbN)",
        "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        "verify_ssl": True,
    },
    {
        "name": "gyan.dev (fallback)",
        "url": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "verify_ssl": False,
    },
]


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def _get_install_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_ffmpeg_status() -> dict:
    root    = _get_install_root()
    ffmpeg  = os.path.join(root, "ffmpeg", "ffmpeg.exe")
    ffprobe = os.path.join(root, "ffmpeg", "ffprobe.exe")
    return {
        "installed":   os.path.isfile(ffmpeg) and os.path.isfile(ffprobe),
        "ffmpeg":      ffmpeg,
        "ffprobe":     ffprobe,
        "ffmpeg_dir":  os.path.join(root, "ffmpeg"),
    }


def get_ytdlp_exe() -> str:
    """查找本地或系统中的 yt-dlp 可执行文件。"""
    import shutil
    exe_name = "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"
    root = _get_install_root()
    candidates = [
        os.path.join(root, exe_name),
        os.path.join(root, "ffmpeg", exe_name),
    ]
    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, exe_name))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return shutil.which("yt-dlp") or ""


def get_opencv_status() -> dict:
    """检测 opencv-python 是否已安装且功能完整（含 CascadeClassifier）。"""
    try:
        import cv2
        _ = cv2.CascadeClassifier
        ver = getattr(cv2, "__version__", "installed")
        return {"installed": True, "version": str(ver)}
    except Exception:
        return {"installed": False, "version": ""}


def get_ytdlp_status() -> dict:
    """检测 yt-dlp.exe（或 Python 模块 yt_dlp）是否已安装。"""
    exe = get_ytdlp_exe()
    if exe and os.path.isfile(exe):
        ver = "已就绪"
        try:
            r = subprocess.run(
                [exe, "--version"],
                capture_output=True, text=True, timeout=6,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if r.returncode == 0 and r.stdout.strip():
                ver = r.stdout.strip()
        except Exception:
            pass
        return {"installed": True, "version": ver, "path": exe}
    if not getattr(sys, "frozen", False):
        try:
            import yt_dlp
            ver = getattr(yt_dlp.version, "__version__", "installed")
            return {"installed": True, "version": str(ver), "path": "python -m yt_dlp"}
        except Exception:
            pass
    target = os.path.join(_get_install_root(), "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp")
    return {"installed": False, "version": "", "path": target}


def get_mediapipe_status() -> dict:
    """检测 mediapipe 是否已安装（用于人脸检测）。"""
    try:
        import mediapipe as mp
        ver = getattr(mp, "__version__", "installed")
        return {"installed": True, "version": str(ver)}
    except Exception:
        return {"installed": False, "version": ""}


def get_face_detection_status() -> dict:
    """
    检测人脸检测引擎是否可用（mediapipe 或 能正常工作的 cv2）。
    优先 mediapipe，备用 cv2（需含 CascadeClassifier）。
    """
    mp = get_mediapipe_status()
    if mp["installed"]:
        return {"installed": True, "version": mp["version"], "via": "mediapipe"}
    cv = get_opencv_status()
    if cv["installed"]:
        return {"installed": True, "version": cv["version"], "via": "opencv"}
    return {"installed": False, "version": "", "via": ""}


# ── FFmpeg 下载线程 ───────────────────────────────────────────────────────────

class DownloadThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, target_dir: str, parent=None):
        super().__init__(parent)
        self.target_dir = target_dir
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        import tempfile, shutil
        tmp_zip = None
        try:
            resp        = None
            used_source = None

            for source in _FFMPEG_SOURCES:
                if self._stop:
                    self.finished.emit(False, "用户已取消下载。")
                    return
                self.progress.emit(0, f"正在连接 {source['name']}...")
                try:
                    req = urllib.request.Request(
                        source["url"],
                        headers={"User-Agent": "Mozilla/5.0 VideoTools/1.3.0"}
                    )
                    ctx = ssl.create_default_context()
                    if not source["verify_ssl"]:
                        ctx.check_hostname = False
                        ctx.verify_mode    = ssl.CERT_NONE
                    resp = urllib.request.urlopen(req, timeout=60, context=ctx)
                    used_source = source
                    self.progress.emit(2, f"已连接到 {source['name']}，准备下载...")
                    break
                except Exception:
                    self.progress.emit(0, f"{source['name']} 连接失败，尝试下一个源...")
                    continue

            if resp is None:
                self.finished.emit(
                    False,
                    "所有下载源均连接失败，请检查网络连接。\n\n"
                    "如果网络正常但仍失败，可手动下载 ffmpeg.exe 和 ffprobe.exe\n"
                    "并放入软件安装目录的 ffmpeg\\ 子文件夹中。"
                )
                return

            total      = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            tmp_fd, tmp_zip = tempfile.mkstemp(suffix=".zip", prefix="ffmpeg_dl_")

            with os.fdopen(tmp_fd, "wb") as f:
                chunk_size = 65536
                while True:
                    if self._stop:
                        self.finished.emit(False, "用户已取消下载。")
                        return
                    data = resp.read(chunk_size)
                    if not data:
                        break
                    f.write(data)
                    downloaded += len(data)
                    if total > 0:
                        pct = min(80, int(downloaded / total * 80))
                        mb  = downloaded / (1024 * 1024)
                        total_mb = total / (1024 * 1024)
                        self.progress.emit(pct, f"正在下载... {mb:.1f} / {total_mb:.1f} MB")
                    else:
                        mb = downloaded / (1024 * 1024)
                        self.progress.emit(40, f"正在下载... {mb:.1f} MB")

            self.progress.emit(82, "正在解压 FFmpeg 文件...")
            os.makedirs(self.target_dir, exist_ok=True)

            extracted = 0
            try:
                with zipfile.ZipFile(tmp_zip, "r") as zf:
                    names   = zf.namelist()
                    targets = [n for n in names if n.endswith(("ffmpeg.exe", "ffprobe.exe"))]
                    if not targets:
                        self.finished.emit(False, "压缩包中未找到 ffmpeg.exe / ffprobe.exe，\n下载包可能已损坏，请重试。")
                        return
                    for member in targets:
                        basename = os.path.basename(member)
                        dst = os.path.join(self.target_dir, basename)
                        with zf.open(member) as src, open(dst, "wb") as out:
                            shutil.copyfileobj(src, out)
                        extracted += 1
                        self.progress.emit(82 + extracted * 8, f"已解压: {basename}")
            except zipfile.BadZipFile:
                self.finished.emit(False, "下载的文件已损坏，请重试。")
                return

            self.progress.emit(100, "安装完成！")
            self.finished.emit(True, "FFmpeg 已成功安装！\n现在可以使用视频合并和图片合并功能了。")

        except Exception as e:
            self.finished.emit(False, f"发生意外错误：\n{e}")
        finally:
            if tmp_zip and os.path.exists(tmp_zip):
                try:
                    os.remove(tmp_zip)
                except Exception:
                    pass


# ── yt-dlp 独立可执行文件下载线程 ────────────────────────────────────────────

_YTDLP_URLS = [
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
    "https://ghfast.top/https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
]


class YtdlpDownloadThread(QThread):
    """下载官方独立版 yt-dlp.exe 到软件根目录，无需依赖系统 Python/pip。"""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, target_path: str = "", parent=None):
        super().__init__(parent)
        self.target_path = target_path or os.path.join(
            _get_install_root(), "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"
        )
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        part_path = self.target_path + ".part"
        try:
            os.makedirs(os.path.dirname(self.target_path), exist_ok=True)
            resp = None
            for idx, url in enumerate(_YTDLP_URLS):
                if self._stop:
                    self.finished.emit(False, "用户已取消下载。")
                    return
                src_name = "GitHub 官方源" if idx == 0 else "备用加速源"
                self.progress.emit(2, f"正在连接 {src_name} 下载 yt-dlp.exe...")
                try:
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "Mozilla/5.0 VideoTools/1.5"}
                    )
                    ctx = ssl.create_default_context()
                    resp = urllib.request.urlopen(req, timeout=30, context=ctx)
                    break
                except Exception:
                    continue

            if resp is None:
                self.finished.emit(False, "无法连接到 GitHub 下载 yt-dlp.exe，请检查网络连接后重试。")
                return

            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(part_path, "wb") as f:
                while True:
                    if self._stop:
                        self.finished.emit(False, "用户已取消下载。")
                        return
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    mb = downloaded / (1024 * 1024)
                    if total > 0:
                        pct = min(95, max(5, int(downloaded * 95 / total)))
                        total_mb = total / (1024 * 1024)
                        self.progress.emit(pct, f"正在下载 yt-dlp.exe... {mb:.1f} / {total_mb:.1f} MB")
                    else:
                        self.progress.emit(50, f"正在下载 yt-dlp.exe... {mb:.1f} MB")

            if not os.path.isfile(part_path) or os.path.getsize(part_path) < 1024 * 1024:
                self.finished.emit(False, "下载的 yt-dlp.exe 文件不完整，请重试。")
                return

            if os.path.exists(self.target_path):
                try:
                    os.remove(self.target_path)
                except Exception:
                    pass
            os.replace(part_path, self.target_path)
            self.progress.emit(100, "安装成功！")
            self.finished.emit(True, f"yt-dlp 已成功安装到：\n{self.target_path}")
        except Exception as e:
            self.finished.emit(False, f"下载安装 yt-dlp 时出错：\n{e}")
        finally:
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except Exception:
                    pass


# ── 主对话框：下载必要组件 ────────────────────────────────────────────────────

class FFmpegDownloaderDialog(QDialog):
    """「下载必要组件」对话框，管理 FFmpeg 和 yt-dlp。
    opencv-python 和 mediapipe 已作为标准依赖内置，无需手动安装。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📦 下载必要组件")
        self.setMinimumWidth(580)
        self.setMinimumHeight(500)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._ffmpeg_thread = None
        self._ytdlp_thread  = None
        self._apply_style()
        self._setup_ui()
        self._refresh_all_status()

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1d27;
                color: #d1d5db;
                font-family: "Microsoft YaHei", "Segoe UI";
            }
            QLabel { color: #d1d5db; }
            QLabel#Title { font-size: 15pt; font-weight: bold; color: #ffffff; }
            QLabel#SubTitle { font-size: 10pt; color: #9ca3af; }
            QLabel#SectionTitle { font-size: 11pt; font-weight: bold; color: #e5e7eb; }
            QFrame#ComponentCard {
                background-color: #0f1117;
                border: 1px solid #2b303b;
                border-radius: 10px;
            }
            QLabel#StatusIcon { font-size: 22pt; }
            QLabel#StatusText { font-size: 10pt; font-weight: bold; }
            QLabel#PathText { color: #6b7280; font-size: 9pt; }
            QLabel#LogText  { color: #6b7280; font-size: 9pt; }
            QPushButton#BtnDownload {
                background-color: #f43f5e; color: white; border: none;
                border-radius: 7px; padding: 9px 20px;
                font-size: 10pt; font-weight: bold;
            }
            QPushButton#BtnDownload:hover { background-color: #e11d48; }
            QPushButton#BtnDownload:disabled { background-color: #4b5563; color: #9ca3af; }
            QPushButton#BtnInstallPy {
                background-color: #3b82f6; color: white; border: none;
                border-radius: 7px; padding: 9px 20px;
                font-size: 10pt; font-weight: bold;
            }
            QPushButton#BtnInstallPy:hover { background-color: #2563eb; }
            QPushButton#BtnInstallPy:disabled { background-color: #4b5563; color: #9ca3af; }
            QPushButton#BtnClose {
                background-color: #1f2937; color: #9ca3af;
                border: 1px solid #374151; border-radius: 7px;
                padding: 9px 24px; font-size: 10pt;
            }
            QPushButton#BtnClose:hover { background-color: #374151; color: #ffffff; }
            QProgressBar {
                border: 1px solid #374151; border-radius: 5px;
                background-color: #0f1117; text-align: center;
                color: #ffffff; font-size: 9pt; max-height: 18px;
            }
            QProgressBar::chunk { background-color: #f43f5e; border-radius: 4px; }
        """)

    def _make_component_card(self, icon_attr, text_attr, path_attr, btn, progress_attr, log_attr):
        """构建单个组件卡片，返回 QFrame。"""
        card = QFrame()
        card.setObjectName("ComponentCard")
        card_lo = QVBoxLayout(card)
        card_lo.setContentsMargins(18, 14, 18, 14)
        card_lo.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        icon_lbl = QLabel("...")
        icon_lbl.setObjectName("StatusIcon")
        icon_lbl.setFixedWidth(36)
        top_row.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        status_lbl = QLabel("正在检测...")
        status_lbl.setObjectName("StatusText")
        path_lbl = QLabel("")
        path_lbl.setObjectName("PathText")
        path_lbl.setWordWrap(True)
        text_col.addWidget(status_lbl)
        text_col.addWidget(path_lbl)
        top_row.addLayout(text_col, 1)
        top_row.addWidget(btn)
        card_lo.addLayout(top_row)

        prog = QProgressBar()
        prog.setValue(0)
        prog.setVisible(False)
        card_lo.addWidget(prog)

        log_lbl = QLabel("")
        log_lbl.setObjectName("LogText")
        log_lbl.setWordWrap(True)
        card_lo.addWidget(log_lbl)

        setattr(self, icon_attr,     icon_lbl)
        setattr(self, text_attr,     status_lbl)
        setattr(self, path_attr,     path_lbl)
        setattr(self, progress_attr, prog)
        setattr(self, log_attr,      log_lbl)

        return card

    def _setup_ui(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(28, 24, 28, 24)
        lo.setSpacing(12)

        # 标题
        title = QLabel("📦  下载必要组件")
        title.setObjectName("Title")
        lo.addWidget(title)

        sub = QLabel(
            "软件各功能模块依赖以下组件，请确保已全部安装。\n"
            "可点击对应按钮一键下载或安装。"
        )
        sub.setObjectName("SubTitle")
        sub.setWordWrap(True)
        lo.addWidget(sub)

        # ── FFmpeg ────────────────────────────────────────────────────────
        ffmpeg_title = QLabel("🎬  FFmpeg  —  视频合并 / 图片合成 / 截图功能")
        ffmpeg_title.setObjectName("SectionTitle")
        lo.addWidget(ffmpeg_title)

        self.btn_ffmpeg_dl = QPushButton("⬇️  下载并安装 FFmpeg")
        self.btn_ffmpeg_dl.setObjectName("BtnDownload")
        self.btn_ffmpeg_dl.clicked.connect(self._start_ffmpeg_download)

        lo.addWidget(self._make_component_card(
            "lbl_ffmpeg_icon", "lbl_ffmpeg_text", "lbl_ffmpeg_path",
            self.btn_ffmpeg_dl,
            "prog_ffmpeg", "lbl_ffmpeg_log"
        ))
        src_lbl = QLabel("下载源：GitHub (BtbN) / gyan.dev (SSL bypass 备用)")
        src_lbl.setStyleSheet("color: #4b5563; font-size: 8pt;")
        lo.addWidget(src_lbl)

        # ── yt-dlp ────────────────────────────────────────────────────────
        yt_title = QLabel("📥  yt-dlp  —  YouTube下载 / 链接截图 / 云盘下载")
        yt_title.setObjectName("SectionTitle")
        lo.addWidget(yt_title)

        self.btn_ytdlp_install = QPushButton("⬇️  安装 yt-dlp")
        self.btn_ytdlp_install.setObjectName("BtnInstallPy")
        self.btn_ytdlp_install.clicked.connect(self._start_ytdlp_install)

        lo.addWidget(self._make_component_card(
            "lbl_yt_icon", "lbl_yt_text", "lbl_yt_path",
            self.btn_ytdlp_install,
            "prog_yt", "lbl_yt_log"
        ))
        yt_note = QLabel("通过 pip install yt-dlp 安装，支持 YouTube / Instagram / Facebook 等平台")
        yt_note.setStyleSheet("color: #4b5563; font-size: 8pt;")
        lo.addWidget(yt_note)

        # ── 内置库说明 ────────────────────────────────────────────────────
        bundled_title = QLabel("✅  opencv-python & mediapipe  —  已内置，无需手动安装")
        bundled_title.setObjectName("SectionTitle")
        lo.addWidget(bundled_title)

        bundled_note = QLabel(
            "opencv-python 和 mediapipe 已作为软件标准依赖内置，\n"
            "安装软件时会自动配置，无需手动下载安装。"
        )
        bundled_note.setStyleSheet(
            "color: #10b981; font-size: 9pt; padding: 10px 14px; "
            "background: rgba(16,185,129,0.08); border-radius: 6px; border: 1px solid rgba(16,185,129,0.3);"
        )
        bundled_note.setWordWrap(True)
        lo.addWidget(bundled_note)

        lo.addStretch()

        # 关闭按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_close = QPushButton("关 闭")
        self.btn_close.setObjectName("BtnClose")
        self.btn_close.clicked.connect(self._on_close)
        btn_row.addWidget(self.btn_close)
        lo.addLayout(btn_row)

    # ── 状态刷新 ──────────────────────────────────────────────────────────────

    def _refresh_all_status(self):
        self._refresh_ffmpeg_status()
        self._refresh_ytdlp_status()

    def _refresh_ffmpeg_status(self):
        status = get_ffmpeg_status()
        if status["installed"]:
            self.lbl_ffmpeg_icon.setText("✅")
            self.lbl_ffmpeg_text.setText("FFmpeg 已安装")
            self.lbl_ffmpeg_text.setStyleSheet("font-size: 10pt; font-weight: bold; color: #10b981;")
            self.lbl_ffmpeg_path.setText(f"路径：{status['ffmpeg_dir']}")
            self.btn_ffmpeg_dl.setText("🔄  重新下载（覆盖安装）")
        else:
            self.lbl_ffmpeg_icon.setText("❌")
            self.lbl_ffmpeg_text.setText("未检测到 FFmpeg — 视频功能不可用")
            self.lbl_ffmpeg_text.setStyleSheet("font-size: 10pt; font-weight: bold; color: #f43f5e;")
            self.lbl_ffmpeg_path.setText(f"将安装到：{status['ffmpeg_dir']}")
            self.btn_ffmpeg_dl.setText("⬇️  下载并安装 FFmpeg")


    def _refresh_ytdlp_status(self):
        status = get_ytdlp_status()
        if status["installed"]:
            self.lbl_yt_icon.setText("✅")
            self.lbl_yt_text.setText(f"yt-dlp 已安装  (v{status['version']})")
            self.lbl_yt_text.setStyleSheet("font-size: 10pt; font-weight: bold; color: #10b981;")
            self.lbl_yt_path.setText(f"路径：{status.get('path', '')}")
            self.btn_ytdlp_install.setText("🔄  重新下载 / 更新 yt-dlp")
        else:
            self.lbl_yt_icon.setText("❌")
            self.lbl_yt_text.setText("未安装 yt-dlp — 下载功能不可用")
            self.lbl_yt_text.setStyleSheet("font-size: 10pt; font-weight: bold; color: #f87171;")
            self.lbl_yt_path.setText(f"将安装到：{status.get('path', '')}")
            self.btn_ytdlp_install.setText("⬇️  安装 yt-dlp")

    # ── FFmpeg 下载 ───────────────────────────────────────────────────────────

    def _start_ffmpeg_download(self):
        ffmpeg_dir = get_ffmpeg_status()["ffmpeg_dir"]
        self.btn_ffmpeg_dl.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.prog_ffmpeg.setVisible(True)
        self.prog_ffmpeg.setValue(0)
        self._ffmpeg_thread = DownloadThread(ffmpeg_dir, parent=self)
        self._ffmpeg_thread.progress.connect(self._on_ffmpeg_progress)
        self._ffmpeg_thread.finished.connect(self._on_ffmpeg_finished)
        self._ffmpeg_thread.start()

    def _on_ffmpeg_progress(self, pct: int, msg: str):
        self.prog_ffmpeg.setValue(pct)
        self.lbl_ffmpeg_log.setText(msg)

    def _on_ffmpeg_finished(self, success: bool, msg: str):
        self.btn_ffmpeg_dl.setEnabled(True)
        self.btn_close.setEnabled(True)
        if success:
            self.prog_ffmpeg.setValue(100)
            self.lbl_ffmpeg_log.setText("✅ 安装完成")
            self._refresh_ffmpeg_status()
        else:
            self.prog_ffmpeg.setValue(0)
            self.lbl_ffmpeg_log.setText("⚠️ 安装失败，请重试")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "下载失败", msg)

    # ── yt-dlp 安装 ───────────────────────────────────────────────────────────

    def _start_ytdlp_install(self):
        self.btn_ytdlp_install.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.prog_yt.setVisible(True)
        self.prog_yt.setValue(0)
        self._ytdlp_thread = YtdlpDownloadThread(parent=self)
        self._ytdlp_thread.progress.connect(self._on_yt_progress)
        self._ytdlp_thread.finished.connect(self._on_yt_finished)
        self._ytdlp_thread.start()

    def _on_yt_progress(self, pct: int, msg: str):
        self.prog_yt.setValue(pct)
        self.lbl_yt_log.setText(msg[:100])

    def _on_yt_finished(self, success: bool, msg: str):
        self.btn_ytdlp_install.setEnabled(True)
        self.btn_close.setEnabled(True)
        if success:
            self.prog_yt.setValue(100)
            self.lbl_yt_log.setText("✅ 安装完成")
            self._refresh_ytdlp_status()
        else:
            self.prog_yt.setValue(0)
            self.lbl_yt_log.setText("⚠️ 安装失败，请重试")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "安装失败", msg)

    # ── 关闭处理 ──────────────────────────────────────────────────────────────

    def _on_close(self):
        for thread in (self._ffmpeg_thread, self._ytdlp_thread):
            if thread and thread.isRunning():
                if hasattr(thread, "stop"):
                    thread.stop()
                thread.wait(2000)
        self.reject()

    def closeEvent(self, event):
        for thread in (self._ffmpeg_thread, self._ytdlp_thread):
            if thread and thread.isRunning():
                if hasattr(thread, "stop"):
                    thread.stop()
                thread.wait(2000)
        super().closeEvent(event)

