import os
import sys
import zipfile
import urllib.request
import urllib.error

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt


_FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def _get_install_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_ffmpeg_status() -> dict:
    root = _get_install_root()
    ffmpeg = os.path.join(root, "ffmpeg", "ffmpeg.exe")
    ffprobe = os.path.join(root, "ffmpeg", "ffprobe.exe")
    return {
        "installed": os.path.isfile(ffmpeg) and os.path.isfile(ffprobe),
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "ffmpeg_dir": os.path.join(root, "ffmpeg"),
    }


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
            self.progress.emit(0, "正在连接下载服务器...")
            try:
                req = urllib.request.Request(
                    _FFMPEG_URL,
                    headers={"User-Agent": "Mozilla/5.0 VideoTools/1.3.0"}
                )
                resp = urllib.request.urlopen(req, timeout=30)
            except urllib.error.URLError as e:
                self.finished.emit(False, f"无法连接下载服务器：\n{e}\n\n请检查网络连接后重试。")
                return

            total = int(resp.headers.get("Content-Length", 0))
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
                        mb = downloaded / (1024 * 1024)
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
                    names = zf.namelist()
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


class FFmpegDownloaderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FFmpeg 管理")
        self.setFixedSize(520, 360)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._thread = None
        self._apply_style()
        self._setup_ui()
        self._refresh_status()

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
            QFrame#StatusCard {
                background-color: #0f1117;
                border: 1px solid #2b303b;
                border-radius: 10px;
            }
            QLabel#StatusIcon { font-size: 24pt; }
            QLabel#StatusText { font-size: 11pt; font-weight: bold; }
            QLabel#PathText { color: #6b7280; font-size: 9pt; }
            QPushButton#BtnDownload {
                background-color: #f43f5e; color: white; border: none;
                border-radius: 8px; padding: 11px 28px;
                font-size: 11pt; font-weight: bold;
            }
            QPushButton#BtnDownload:hover { background-color: #e11d48; }
            QPushButton#BtnDownload:disabled { background-color: #4b5563; color: #9ca3af; }
            QPushButton#BtnClose {
                background-color: #1f2937; color: #9ca3af;
                border: 1px solid #374151; border-radius: 8px;
                padding: 11px 24px; font-size: 11pt;
            }
            QPushButton#BtnClose:hover { background-color: #374151; color: #ffffff; }
            QProgressBar {
                border: 1px solid #374151; border-radius: 6px;
                background-color: #0f1117; text-align: center;
                color: #ffffff; font-size: 9pt;
            }
            QProgressBar::chunk { background-color: #f43f5e; border-radius: 5px; }
        """)

    def _setup_ui(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(28, 24, 28, 24)
        lo.setSpacing(16)

        title = QLabel("⚙️  FFmpeg 管理")
        title.setObjectName("Title")
        lo.addWidget(title)

        sub = QLabel("FFmpeg 是视频处理的核心引擎，视频合并和图片合成功能依赖于它。")
        sub.setObjectName("SubTitle")
        sub.setWordWrap(True)
        lo.addWidget(sub)

        self.status_card = QFrame()
        self.status_card.setObjectName("StatusCard")
        card_lo = QHBoxLayout(self.status_card)
        card_lo.setContentsMargins(20, 16, 20, 16)
        card_lo.setSpacing(16)

        self.lbl_status_icon = QLabel("...")
        self.lbl_status_icon.setObjectName("StatusIcon")
        self.lbl_status_icon.setFixedWidth(44)
        card_lo.addWidget(self.lbl_status_icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        self.lbl_status_text = QLabel("正在检测...")
        self.lbl_status_text.setObjectName("StatusText")
        self.lbl_status_path = QLabel("")
        self.lbl_status_path.setObjectName("PathText")
        self.lbl_status_path.setWordWrap(True)
        text_col.addWidget(self.lbl_status_text)
        text_col.addWidget(self.lbl_status_path)
        card_lo.addLayout(text_col, 1)
        lo.addWidget(self.status_card)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(22)
        self.progress_bar.setVisible(False)
        lo.addWidget(self.progress_bar)

        self.lbl_log = QLabel("")
        self.lbl_log.setStyleSheet("color: #6b7280; font-size: 9pt;")
        self.lbl_log.setWordWrap(True)
        lo.addWidget(self.lbl_log)

        lo.addStretch()

        src_lbl = QLabel("下载源：gyan.dev（FFmpeg 官网推荐的 Windows 构建，约 90 MB）")
        src_lbl.setStyleSheet("color: #4b5563; font-size: 9pt;")
        lo.addWidget(src_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.btn_download = QPushButton("⬇️  下载并安装 FFmpeg")
        self.btn_download.setObjectName("BtnDownload")
        self.btn_close = QPushButton("关 闭")
        self.btn_close.setObjectName("BtnClose")
        self.btn_close.clicked.connect(self._on_close)
        self.btn_download.clicked.connect(self._start_download)
        btn_row.addWidget(self.btn_download)
        btn_row.addWidget(self.btn_close)
        lo.addLayout(btn_row)

    def _refresh_status(self):
        status = get_ffmpeg_status()
        if status["installed"]:
            self.lbl_status_icon.setText("✅")
            self.lbl_status_text.setText("FFmpeg 已安装")
            self.lbl_status_text.setStyleSheet("font-size: 11pt; font-weight: bold; color: #10b981;")
            self.lbl_status_path.setText(f"路径：{status['ffmpeg_dir']}")
            self.btn_download.setText("🔄  重新下载（覆盖安装）")
        else:
            self.lbl_status_icon.setText("❌")
            self.lbl_status_text.setText("未检测到 FFmpeg — 视频功能不可用")
            self.lbl_status_text.setStyleSheet("font-size: 11pt; font-weight: bold; color: #f43f5e;")
            self.lbl_status_path.setText(f"将安装到：{status['ffmpeg_dir']}")
            self.btn_download.setText("⬇️  下载并安装 FFmpeg")

    def _start_download(self):
        status = get_ffmpeg_status()
        ffmpeg_dir = status["ffmpeg_dir"]
        self.btn_download.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self._thread = DownloadThread(ffmpeg_dir, parent=self)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished.connect(self._on_finished)
        self._thread.start()

    def _on_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.lbl_log.setText(msg)

    def _on_finished(self, success: bool, msg: str):
        self.btn_download.setEnabled(True)
        self.btn_close.setEnabled(True)
        if success:
            self.progress_bar.setValue(100)
            self.lbl_log.setText("✅ " + msg.split("\n")[0])
            self._refresh_status()
        else:
            self.progress_bar.setValue(0)
            self.lbl_log.setText("⚠️ 安装失败，请重试")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "下载失败", msg)

    def _on_close(self):
        if self._thread and self._thread.isRunning():
            self._thread.stop()
            self._thread.wait(2000)
        self.reject()

    def closeEvent(self, event):
        if self._thread and self._thread.isRunning():
            self._thread.stop()
            self._thread.wait(2000)
        super().closeEvent(event)
