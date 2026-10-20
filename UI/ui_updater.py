# -*- coding: utf-8 -*-
"""
ui_updater.py — 软件在线检查更新与一键下载安装（基于 GitHub Releases）
"""
import os
import re
import sys
import time
import tempfile
import subprocess
import requests

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QPlainTextEdit, QMessageBox, QApplication, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices

GITHUB_OWNER = "dedeyuyu"
GITHUB_REPO = "VideoTools"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
RELEASES_LIST_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"


def parse_version(v_str: str) -> tuple:
    """将版本字符串（如 'v1.5.13' 或 '1.5.13'）解析为整数元组 (1, 5, 13) 以便比较大小。"""
    nums = re.findall(r"\d+", str(v_str or ""))
    return tuple(int(n) for n in nums) if nums else (0,)


def is_newer_version(remote_ver: str, local_ver: str) -> bool:
    return parse_version(remote_ver) > parse_version(local_ver)


def _format_size(num_bytes: int) -> str:
    if num_bytes <= 0:
        return "未知大小"
    mb = num_bytes / (1024 * 1024)
    if mb >= 1.0:
        return f"{mb:.1f} MB"
    kb = num_bytes / 1024
    return f"{kb:.1f} KB"


def fetch_latest_release(timeout: int = 12) -> dict:
    """
    向 GitHub API 查询最新发布版本信息。
    返回字典：
      {
        "tag_name": "v1.5.13",
        "version": "1.5.13",
        "name": "VideoTools Release v1.5.13",
        "body": "...",
        "html_url": "https://github.com/...",
        "published_at": "2026-10-12",
        "asset_name": "VideoTools_v1.5.13_Setup.exe",
        "download_url": "https://github.com/.../VideoTools_v1.5.13_Setup.exe",
        "asset_size": 123456789,
      }
    """
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "VideoTools-Updater/1.0",
    }
    resp = requests.get(RELEASES_LATEST_URL, headers=headers, timeout=timeout)
    data = None
    if resp.status_code == 200:
        data = resp.json()
    else:
        # 备选：获取 releases 列表的第一项
        resp2 = requests.get(RELEASES_LIST_URL, headers=headers, timeout=timeout)
        if resp2.status_code == 200:
            rels = resp2.json()
            if isinstance(rels, list):
                for r in rels:
                    if not r.get("draft"):
                        data = r
                        break
        if data is None:
            resp.raise_for_status()

    tag = str(data.get("tag_name") or "").strip()
    ver = tag.lstrip("vV").strip() or tag
    assets = data.get("assets") or []
    chosen = None
    for a in assets:
        nm = str(a.get("name") or "")
        if nm.lower().endswith(".exe") and "setup" in nm.lower():
            chosen = a
            break
    if chosen is None:
        for a in assets:
            nm = str(a.get("name") or "")
            if nm.lower().endswith(".exe"):
                chosen = a
                break
    if chosen is None and assets:
        chosen = assets[0]

    pub = str(data.get("published_at") or "")[:10]
    return {
        "tag_name": tag,
        "version": ver,
        "name": str(data.get("name") or tag),
        "body": str(data.get("body") or "暂无更新说明。"),
        "html_url": str(data.get("html_url") or RELEASES_PAGE_URL),
        "published_at": pub,
        "asset_name": str(chosen.get("name") or "") if chosen else "",
        "download_url": str(chosen.get("browser_download_url") or "") if chosen else "",
        "asset_size": int(chosen.get("size") or 0) if chosen else 0,
    }


class UpdateCheckThread(QThread):
    """后台线程：检查 GitHub 最新版本。"""
    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def run(self):
        try:
            info = fetch_latest_release(timeout=12)
            self.result_ready.emit(info)
        except Exception as e:
            self.error_occurred.emit(str(e))


class UpdateDownloadThread(QThread):
    """后台线程：下载安装包并报告进度。"""
    progress = pyqtSignal(int, int, float)   # downloaded_bytes, total_bytes, speed_bytes_per_sec
    finished_ok = pyqtSignal(str)            # local_exe_path
    failed = pyqtSignal(str)                 # error_message

    def __init__(self, url: str, dest_path: str, expected_size: int = 0, parent=None):
        super().__init__(parent)
        self.url = url
        self.dest_path = dest_path
        self.expected_size = expected_size
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        part_path = self.dest_path + ".part"
        try:
            os.makedirs(os.path.dirname(self.dest_path), exist_ok=True)
            headers = {"User-Agent": "VideoTools-Updater/1.0"}
            with requests.get(self.url, headers=headers, stream=True, timeout=30) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length") or self.expected_size or 0)
                downloaded = 0
                t0 = time.time()
                last_emit = 0.0
                with open(part_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if self._cancelled:
                            raise RuntimeError("已取消下载")
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if now - last_emit >= 0.08 or (total > 0 and downloaded >= total):
                            elapsed = max(0.001, now - t0)
                            speed = downloaded / elapsed
                            self.progress.emit(downloaded, total, speed)
                            last_emit = now

            if self._cancelled:
                raise RuntimeError("已取消下载")
            if not os.path.isfile(part_path) or os.path.getsize(part_path) < 1024:
                raise RuntimeError("下载的文件不完整")
            if os.path.exists(self.dest_path):
                try:
                    os.remove(self.dest_path)
                except Exception:
                    pass
            os.replace(part_path, self.dest_path)
            self.finished_ok.emit(self.dest_path)
        except Exception as e:
            try:
                if os.path.exists(part_path):
                    os.remove(part_path)
            except Exception:
                pass
            self.failed.emit(str(e))


class UpdaterDialog(QDialog):
    """检查更新与一键下载安装对话框。"""

    def __init__(self, parent=None, current_version: str = "1.0.0", preloaded_info: dict = None):
        super().__init__(parent)
        self.setWindowTitle("检查软件更新")
        self.setMinimumSize(520, 380)
        self.current_version = current_version
        self.release_info = preloaded_info
        self._check_thread = None
        self._dl_thread = None

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 20, 20, 20)

        # ── 顶部状态卡片 ──
        info_frame = QFrame()
        info_frame.setProperty("class", "Card")
        info_lay = QVBoxLayout(info_frame)
        info_lay.setSpacing(6)

        self.lbl_cur = QLabel(f"当前版本: v{self.current_version}")
        self.lbl_cur.setStyleSheet("color: #A0AEC0; font-size: 10pt;")
        info_lay.addWidget(self.lbl_cur)

        self.lbl_status = QLabel("🔄 正在连接 GitHub 检查最新版本...")
        self.lbl_status.setStyleSheet("font-size: 12pt; font-weight: bold;")
        self.lbl_status.setWordWrap(True)
        info_lay.addWidget(self.lbl_status)

        self.lbl_meta = QLabel("")
        self.lbl_meta.setStyleSheet("color: #A0AEC0; font-size: 9.5pt;")
        self.lbl_meta.setVisible(False)
        info_lay.addWidget(self.lbl_meta)

        root.addWidget(info_frame)

        # ── 更新说明 ──
        lbl_notes = QLabel("版本更新说明:")
        root.addWidget(lbl_notes)

        self.txt_notes = QPlainTextEdit()
        self.txt_notes.setReadOnly(True)
        self.txt_notes.setPlaceholderText("正在获取版本信息...")
        root.addWidget(self.txt_notes, 1)

        # ── 下载进度区 ──
        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setVisible(False)
        root.addWidget(self.prog_bar)

        self.lbl_dl = QLabel("")
        self.lbl_dl.setStyleSheet("color: #63B3ED; font-size: 9.5pt;")
        self.lbl_dl.setVisible(False)
        root.addWidget(self.lbl_dl)

        # ── 底部按钮栏 ──
        btns = QHBoxLayout()
        self.btn_recheck = QPushButton("🔄 重新检查")
        self.btn_recheck.clicked.connect(self.start_check)
        btns.addWidget(self.btn_recheck)

        self.btn_web = QPushButton("🌐 打开 GitHub 发布页")
        self.btn_web.clicked.connect(self._open_release_page)
        btns.addWidget(self.btn_web)

        btns.addStretch()

        self.btn_update = QPushButton("⬇️ 立即下载并更新")
        self.btn_update.setProperty("class", "ActionBtn")
        self.btn_update.setEnabled(False)
        self.btn_update.clicked.connect(self.start_download)
        btns.addWidget(self.btn_update)

        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self._on_close_clicked)
        btns.addWidget(self.btn_close)

        root.addLayout(btns)

        if self.release_info:
            self._on_check_success(self.release_info)
        else:
            self.start_check()

    def start_check(self):
        if self._check_thread and self._check_thread.isRunning():
            return
        self.btn_recheck.setEnabled(False)
        self.btn_update.setEnabled(False)
        self.lbl_status.setText("🔄 正在连接 GitHub 检查最新版本...")
        self.lbl_status.setStyleSheet("font-size: 12pt; font-weight: bold;")
        self.lbl_meta.setVisible(False)
        self.txt_notes.setPlainText("")

        self._check_thread = UpdateCheckThread(self)
        self._check_thread.result_ready.connect(self._on_check_success)
        self._check_thread.error_occurred.connect(self._on_check_error)
        self._check_thread.start()

    def _on_check_success(self, info: dict):
        self.release_info = info
        self.btn_recheck.setEnabled(True)
        remote_ver = info.get("version", "")
        has_new = is_newer_version(remote_ver, self.current_version)

        size_str = _format_size(info.get("asset_size", 0))
        pub_str = info.get("published_at") or "未知日期"
        asset_name = info.get("asset_name") or "无安装包附件"
        self.lbl_meta.setText(f"发布日期: {pub_str}    安装包: {asset_name} ({size_str})")
        self.lbl_meta.setVisible(True)

        notes = info.get("body") or "暂无更新说明。"
        self.txt_notes.setPlainText(f"【{info.get('name', info.get('tag_name', ''))}】\n\n{notes}")

        has_dl = bool(info.get("download_url"))
        if has_new:
            self.lbl_status.setText(f"🎉 发现新版本: v{remote_ver}")
            self.lbl_status.setStyleSheet("font-size: 12pt; font-weight: bold; color: #48BB78;")
            self.btn_update.setText("⬇️ 立即下载并更新")
            self.btn_update.setEnabled(has_dl)
        else:
            self.lbl_status.setText(f"✅ 当前已是最新版本 (v{self.current_version})")
            self.lbl_status.setStyleSheet("font-size: 12pt; font-weight: bold; color: #63B3ED;")
            self.btn_update.setText("⬇️ 重新下载并安装")
            self.btn_update.setEnabled(has_dl)

    def _on_check_error(self, err: str):
        self.btn_recheck.setEnabled(True)
        self.lbl_status.setText("❌ 检查更新失败，请检查网络连接")
        self.lbl_status.setStyleSheet("font-size: 12pt; font-weight: bold; color: #F56565;")
        self.txt_notes.setPlainText(
            f"无法连接到 GitHub 获取版本信息：\n{err}\n\n"
            f"您可以点击下方「🌐 打开 GitHub 发布页」通过浏览器查看或下载最新版本。"
        )

    def _open_release_page(self):
        url = (self.release_info or {}).get("html_url") or RELEASES_PAGE_URL
        QDesktopServices.openUrl(QUrl(url))

    def start_download(self):
        if not self.release_info or not self.release_info.get("download_url"):
            return
        if self._dl_thread and self._dl_thread.isRunning():
            return

        url = self.release_info["download_url"]
        asset_name = self.release_info.get("asset_name") or f"VideoTools_v{self.release_info['version']}_Setup.exe"
        expected_size = int(self.release_info.get("asset_size") or 0)
        dest_dir = os.path.join(tempfile.gettempdir(), "VideoTools_Update")
        dest_path = os.path.join(dest_dir, asset_name)

        self.btn_update.setEnabled(False)
        self.btn_recheck.setEnabled(False)
        self.btn_close.setText("取消下载")
        self.prog_bar.setValue(0)
        self.prog_bar.setVisible(True)
        self.lbl_dl.setText("正在准备下载...")
        self.lbl_dl.setVisible(True)

        self._dl_thread = UpdateDownloadThread(url, dest_path, expected_size, self)
        self._dl_thread.progress.connect(self._on_dl_progress)
        self._dl_thread.finished_ok.connect(self._on_dl_finished)
        self._dl_thread.failed.connect(self._on_dl_failed)
        self._dl_thread.start()

    def _on_dl_progress(self, downloaded: int, total: int, speed: float):
        if total > 0:
            pct = min(100, int(downloaded * 100 / total))
            self.prog_bar.setRange(0, 100)
            self.prog_bar.setValue(pct)
            dl_str = f"{downloaded / (1024 * 1024):.1f} MB / {total / (1024 * 1024):.1f} MB"
        else:
            self.prog_bar.setRange(0, 0)
            dl_str = f"{downloaded / (1024 * 1024):.1f} MB"
        spd_str = f"{speed / (1024 * 1024):.2f} MB/s" if speed >= 1024 * 1024 else f"{speed / 1024:.0f} KB/s"
        self.lbl_dl.setText(f"正在下载更新包: {dl_str}  ({spd_str})")

    def _on_dl_finished(self, exe_path: str):
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(100)
        self.lbl_dl.setText(f"✅ 下载完成：{os.path.basename(exe_path)}")
        self.btn_close.setText("关闭")

        r = QMessageBox.question(
            self,
            "下载完成",
            "新版本安装包已下载完成！\n\n是否立即关闭当前软件并自动完成安装更新？\n（您的所有设置与当前工程进度会自动保存）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if r == QMessageBox.StandardButton.Yes:
            self._launch_installer_and_exit(exe_path)
        else:
            self.btn_update.setEnabled(True)
            self.btn_recheck.setEnabled(True)

    def _on_dl_failed(self, err: str):
        self.prog_bar.setVisible(False)
        self.lbl_dl.setText(f"❌ 下载未完成: {err}")
        self.btn_update.setEnabled(True)
        self.btn_recheck.setEnabled(True)
        self.btn_close.setText("关闭")

    def _on_close_clicked(self):
        if self._dl_thread and self._dl_thread.isRunning():
            self._dl_thread.cancel()
            return
        self.reject()

    def _launch_installer_and_exit(self, installer_exe: str):
        """启动独立的更新批处理（等待主程序退出后执行安装并自动重启），然后安全退出当前程序。"""
        try:
            bat_dir = os.path.dirname(installer_exe)
            bat_path = os.path.join(bat_dir, "apply_update.bat")
            if getattr(sys, "frozen", False):
                install_dir = os.path.dirname(sys.executable)
                app_exe = sys.executable
                bat_content = (
                    "@echo off\r\n"
                    "chcp 65001 >nul\r\n"
                    "timeout /t 2 /nobreak >nul\r\n"
                    f'"{installer_exe}" /SILENT /CLOSEAPPLICATIONS /DIR="{install_dir}"\r\n'
                    f'start "" "{app_exe}"\r\n'
                )
            else:
                # 源码模式下运行安装程序
                bat_content = (
                    "@echo off\r\n"
                    "chcp 65001 >nul\r\n"
                    "timeout /t 2 /nobreak >nul\r\n"
                    f'start "" "{installer_exe}"\r\n'
                )
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)

            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.Popen(["cmd.exe", "/c", bat_path], creationflags=creationflags, close_fds=True)
        except Exception as e:
            QMessageBox.warning(self, "启动安装失败", f"无法自动启动安装程序，请手动运行：\n{installer_exe}\n\n错误：{e}")
            return

        main_win = self.parent()
        self.accept()
        if main_win is not None:
            main_win.close()
        QApplication.instance().quit()
