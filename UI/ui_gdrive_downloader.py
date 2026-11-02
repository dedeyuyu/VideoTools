"""
ui_gdrive_downloader.py
谷歌云端文件批量下载模块

功能：
  - 两列表格（链接 / 自定义命名），支持 Ctrl+V 从 Excel/表格工具粘贴
  - 右键菜单：插入行、删除选中行、清空表格
  - 输出目录选择，使用 QSettings 记住上次路径
  - 后台 yt-dlp 下载线程，实时进度日志
  - 支持任意文件类型：视频、图片、文档等
  - 支持谷歌云端文件夹链接：自动解析并下载文件夹中的所有视频，按「自定义命名+01、02…」编号区分
"""

import os
import sys
import re
import json
import subprocess
import threading
import requests

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QFrame, QProgressBar, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QScrollArea, QSizePolicy, QMessageBox, QMenu, QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QPoint
from PyQt6.QtGui import QFont, QColor, QKeySequence, QShortcut


# ─────────────────────────────────────────────────────────────────────────────
#  后台下载工作线程
# ─────────────────────────────────────────────────────────────────────────────

class GDriveWorker(QThread):
    """逐行读取表格中的（链接, 命名），调用 yt-dlp 下载（支持单文件链接和谷歌云端文件夹链接）。"""

    log_line         = pyqtSignal(str)             # 实时日志行
    item_done        = pyqtSignal(int, bool, str)  # (row_idx, ok, msg)
    overall_progress = pyqtSignal(int, str)        # (pct, text)
    all_done         = pyqtSignal(bool, str)       # (all_ok, summary)

    def __init__(self, tasks: list[tuple[str, str]], output_dir: str, ffmpeg_dir: str):
        """
        tasks: [(url, name), ...]
        output_dir: 输出目录
        ffmpeg_dir: ffmpeg 所在目录（可为空）
        """
        super().__init__()
        self.tasks      = tasks
        self.output_dir = output_dir
        self.ffmpeg_dir = ffmpeg_dir
        self._stop_flag    = False
        self._current_proc = None

    def stop(self):
        self._stop_flag = True
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.terminate()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _ytdlp_exe(self) -> str:
        """返回 yt-dlp 可执行文件路径，优先使用安装目录/项目根目录中的版本。"""
        from UI.ui_ffmpeg_downloader_mgr import get_ytdlp_exe
        return get_ytdlp_exe() or "yt-dlp"

    def _build_args(self, url: str, name: str) -> list[str]:
        """构建单条 yt-dlp 命令参数列表。支持任意文件类型（视频/图片/文档等）。"""
        args = [self._ytdlp_exe(), "--newline", "--no-playlist", "--no-update"]

        # ffmpeg 路径（仅视频合并时需要，其他文件类型不影响）
        if self.ffmpeg_dir and os.path.isdir(self.ffmpeg_dir):
            args += ["--ffmpeg-location", self.ffmpeg_dir]

        # 输出文件名模板：使用用户指定的命名，自动保留原始扩展名
        safe_name = _sanitize_filename(name) if name.strip() else "%(title)s"
        out_template = os.path.join(self.output_dir, f"{safe_name}.%(ext)s")
        args += ["-o", out_template]

        # 不指定 -f 格式选择器，让 yt-dlp 自动识别文件类型并以原始格式下载
        # 这样视频、图片、文档等任意 Google Drive 文件都能正常下载

        args.extend(['--', url])
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

    def _download_single_url(self, url: str, name: str, progress_cb=None) -> tuple[bool, str, bool]:
        """
        下载单个 Google Drive 文件链接。
        返回: (success, reason_msg, fatal_missing_ytdlp)
        """
        cmd = self._build_args(url, name)
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

            for line in self._current_proc.stdout:
                if self._stop_flag:
                    self._current_proc.terminate()
                    break
                line = line.strip()
                if not line:
                    continue
                self.log_line.emit(f"[OUT] {line}")

                m = re.search(r"\[download\]\s+([\d.]+)%", line)
                if m and progress_cb:
                    pct = min(int(float(m.group(1))), 100)
                    progress_cb(pct)

            t.join(timeout=5)
            self._current_proc.wait()
            retcode = self._current_proc.returncode

            if self._stop_flag:
                return False, "已停止", False
            elif retcode == 0:
                return True, "✅ 下载完成", False
            else:
                err_text = " ".join(stderr_lines)
                reason = _classify_error(err_text, retcode)
                self.log_line.emit(f"[FAIL] code={retcode} | {reason}")
                return False, reason, False

        except FileNotFoundError:
            self.log_line.emit("[FAIL] 找不到 yt-dlp，请先安装（pip install yt-dlp）")
            return False, "找不到 yt-dlp，请先安装", True
        except Exception as e:
            self.log_line.emit(f"[FAIL] 异常: {e}")
            return False, f"异常: {e}", False

    def run(self):
        total     = len(self.tasks)
        succeeded = failed = 0

        for idx, (url, name) in enumerate(self.tasks):
            if self._stop_flag:
                break

            display = name.strip() or url
            self.overall_progress.emit(
                int(idx / total * 100),
                f"正在处理第 {idx+1}/{total} 个：{display[:40]}"
            )
            self.log_line.emit(f"\n{'─'*60}")
            self.log_line.emit(f"[{idx+1}/{total}] 链接: {url}")
            self.log_line.emit(f"[{idx+1}/{total}] 命名: {name or '（使用原标题）'}")

            folder_info = _extract_folder_info(url)
            if folder_info is not None:
                folder_id, resource_key = folder_info
                self.log_line.emit(f"[{idx+1}/{total}] 📂 检测到谷歌云端文件夹链接 (ID: {folder_id})，正在获取视频列表...")
                self.overall_progress.emit(
                    int(idx / total * 100),
                    f"正在解析第 {idx+1}/{total} 个文件夹内容..."
                )

                try:
                    folder_title, videos = _fetch_gdrive_folder_videos(folder_id, resource_key)
                except Exception as e:
                    failed += 1
                    err_msg = f"解析文件夹失败: {e}"
                    self.item_done.emit(idx, False, f"❌ {err_msg}")
                    self.log_line.emit(f"[FAIL] {err_msg}")
                    continue

                if self._stop_flag:
                    self.item_done.emit(idx, False, "已停止")
                    break

                if not videos:
                    failed += 1
                    msg = "文件夹内未找到可下载的视频文件（请确认文件夹已公开分享且包含视频）"
                    self.item_done.emit(idx, False, f"❌ {msg}")
                    self.log_line.emit(f"[FAIL] {msg}")
                    continue

                vid_count = len(videos)
                folder_label = folder_title or folder_id
                self.log_line.emit(
                    f"[{idx+1}/{total}] 📂 文件夹「{folder_label}」共找到 {vid_count} 个视频，开始逐个下载..."
                )

                # 基础命名：优先取用户自定义命名（去掉可能误填的视频扩展名）
                user_base = _strip_video_ext(name.strip()) if name.strip() else ""
                folder_ok = 0
                folder_fail = 0
                fatal_abort = False

                for v_idx, v_item in enumerate(videos, start=1):
                    if self._stop_flag:
                        break

                    seq = f"{v_idx:02d}"
                    orig_title = v_item.get("title") or v_item["id"]
                    if user_base:
                        sub_name = f"{user_base}{seq}"
                    else:
                        orig_stem = _strip_video_ext(orig_title) or folder_title or "video"
                        sub_name = f"{orig_stem}{seq}"

                    file_url = f"https://drive.google.com/file/d/{v_item['id']}/view"
                    if v_item.get("resourceKey"):
                        file_url += f"?resourcekey={v_item['resourceKey']}"

                    self.log_line.emit(
                        f"\n  ▶ [{idx+1}/{total} · 视频 {v_idx}/{vid_count}] "
                        f"原文件: {orig_title}  →  保存命名: {sub_name}"
                    )

                    def _on_sub_progress(pct: int, _i=idx, _v=v_idx, _n=vid_count):
                        task_frac = ((_v - 1) + pct / 100.0) / _n
                        fine = (_i + task_frac) / total * 100
                        self.overall_progress.emit(
                            int(fine),
                            f"正在下载第 {_i+1}/{total} 项 [文件夹视频 {_v}/{_n}] ({pct}%)"
                        )

                    _on_sub_progress(0)
                    ok, reason, fatal = self._download_single_url(
                        file_url, sub_name, progress_cb=_on_sub_progress
                    )
                    if fatal:
                        self.item_done.emit(idx, False, f"❌ {reason}")
                        fatal_abort = True
                        break
                    if self._stop_flag:
                        break

                    if ok:
                        folder_ok += 1
                        self.log_line.emit(
                            f"  [OK] 文件夹视频 {v_idx}/{vid_count} 下载完成 ({sub_name})"
                        )
                    else:
                        folder_fail += 1
                        self.log_line.emit(
                            f"  [FAIL] 文件夹视频 {v_idx}/{vid_count} 下载失败: {reason}"
                        )

                if fatal_abort:
                    failed += 1
                    break
                if self._stop_flag:
                    self.item_done.emit(idx, False, "已停止")
                    break

                if folder_fail == 0:
                    succeeded += 1
                    self.item_done.emit(idx, True, f"✅ 文件夹下载完成 ({folder_ok} 个视频)")
                    self.log_line.emit(f"[OK] 第 {idx+1} 项文件夹全部下载完成（共 {folder_ok} 个视频）")
                else:
                    failed += 1
                    self.item_done.emit(
                        idx, False, f"❌ 文件夹成功 {folder_ok}/{vid_count}，失败 {folder_fail} 个"
                    )
                    self.log_line.emit(
                        f"[FAIL] 第 {idx+1} 项文件夹部分或全部失败（成功 {folder_ok}/{vid_count}，失败 {folder_fail} 个）"
                    )

            else:
                # ── 单文件链接下载 ───────────────────────────────────────────
                def _on_file_progress(pct: int, _i=idx):
                    fine = (_i + pct / 100.0) / total * 100
                    self.overall_progress.emit(
                        int(fine), f"正在下载第 {_i+1}/{total} 个 ({pct}%)"
                    )

                ok, reason, fatal = self._download_single_url(
                    url, name, progress_cb=_on_file_progress
                )
                if fatal:
                    failed += 1
                    self.item_done.emit(idx, False, f"❌ {reason}")
                    break
                if self._stop_flag:
                    self.item_done.emit(idx, False, "已停止")
                    break

                if ok:
                    succeeded += 1
                    self.item_done.emit(idx, True, "✅ 下载完成")
                    self.log_line.emit(f"[OK] 第 {idx+1} 个下载完成")
                else:
                    failed += 1
                    self.item_done.emit(idx, False, f"❌ {reason}")

        if self._stop_flag:
            self.all_done.emit(False, f"已停止。完成 {succeeded} 个，失败 {failed} 个。")
        else:
            self.overall_progress.emit(100, "全部完成！")
            self.all_done.emit(
                failed == 0,
                f"全部完成！{succeeded} 个成功，{failed} 个失败。"
            )


# ─────────────────────────────────────────────────────────────────────────────
#  工具函数
# ─────────────────────────────────────────────────────────────────────────────

_VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv", ".m4v",
    ".ts", ".mpg", ".mpeg", ".3gp", ".mts", ".m2ts", ".vob", ".ogv",
    ".rmvb", ".rm", ".asf", ".f4v",
}

_FOLDER_URL_RE = re.compile(
    r"https?://(?:docs|drive)\.google\.com/"
    r"(?:drive/(?:u/\d+/|mobile/)?folders/|folderview\?(?:[^#]*&)?id=)"
    r"([a-zA-Z0-9_-]{15,})",
    re.I,
)

_RESOURCE_KEY_RE = re.compile(r"[?&]resourcekey=([a-zA-Z0-9_-]+)", re.I)


def _extract_folder_info(url: str) -> tuple[str, str] | None:
    """
    若 url 是 Google Drive 文件夹链接，返回 (folder_id, resource_key)；
    否则返回 None。
    """
    m = _FOLDER_URL_RE.search(url)
    if not m:
        return None
    folder_id = m.group(1)
    rk_m = _RESOURCE_KEY_RE.search(url)
    resource_key = rk_m.group(1) if rk_m else ""
    return folder_id, resource_key


def _strip_video_ext(name: str) -> str:
    """若文件名末尾带有常见视频扩展名则去除，方便追加 01、02 序号。"""
    base, ext = os.path.splitext(name)
    if ext.lower() in _VIDEO_EXTENSIONS and base.strip():
        return base.strip()
    return name.strip()


def _is_video_item(item: dict) -> bool:
    """判断 Google Drive 文件夹条目是否为视频文件。"""
    mime = (item.get("mimeType") or "").lower()
    if mime == "application/vnd.google-apps.folder":
        return False
    if mime.startswith("video/"):
        return True
    ext = (item.get("fileExtension") or "").lower().lstrip(".")
    if ext and f".{ext}" in _VIDEO_EXTENSIONS:
        return True
    title = (item.get("title") or "").lower()
    for vext in _VIDEO_EXTENSIONS:
        if title.endswith(vext):
            return True
    return False


def _natural_sort_key(item: dict):
    """按文件标题进行自然排序（如 1, 2, ..., 10），与 Google Drive 默认顺序一致。"""
    title = item.get("title") or ""
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r"(\d+)", title)]


def _fetch_gdrive_folder_videos(folder_id: str, resource_key: str = "") -> tuple[str, list[dict]]:
    """
    解析公开分享的 Google Drive 文件夹，返回 (folder_title, video_items)。
    每个 video_item 包含: {"id": str, "title": str, "mimeType": str, "resourceKey": str}
    按文件名自然排序。
    """
    session = requests.Session()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
    params = {}
    if resource_key:
        params["resourcekey"] = resource_key

    resp = session.get(folder_url, params=params, headers=headers, timeout=25)
    if resp.status_code == 404:
        raise RuntimeError("文件夹不存在或链接已失效 (404)")
    if resp.status_code in (401, 403):
        raise RuntimeError("无权访问该文件夹（请确认文件夹已设为「知道链接的任何人可查看」）")
    resp.raise_for_status()
    html = resp.text

    # 提取文件夹标题
    folder_title = ""
    title_m = re.search(r"<title>(.*?)</title>", html, re.S)
    if title_m:
        t = title_m.group(1).strip()
        t = re.sub(r"\s*-\s*Google\s*(Drive|云端硬盘).*$", "", t, flags=re.I).strip()
        folder_title = t

    items: list[dict] = []

    # ── 方式 1：从网页内置的 window['_DRIVE_ivd'] 提取 ──────────────────────
    ivd_m = re.search(r"window\['_DRIVE_ivd'\]\s*=\s*'([^']+)'", html)
    has_more_pages = False
    if ivd_m:
        try:
            raw = re.sub(
                r"\\x([0-9a-fA-F]{2})",
                lambda m: chr(int(m.group(1), 16)),
                ivd_m.group(1),
            )
            data = json.loads(raw)
            if data and isinstance(data[0], list):
                for entry in data[0]:
                    if isinstance(entry, list) and len(entry) >= 4 and entry[0]:
                        items.append({
                            "id": str(entry[0]),
                            "title": str(entry[2] or ""),
                            "mimeType": str(entry[3] or ""),
                            "fileExtension": "",
                            "resourceKey": "",
                        })
            if len(data) > 1 and data[1]:
                has_more_pages = True
        except Exception:
            items = []

    # ── 方式 2：调用 Google Drive v2beta API（支持翻页及完整字段）───────────
    if not items or has_more_pages:
        keys = list(dict.fromkeys(re.findall(r'"(AIza[0-9A-Za-z_-]{35})"', html)))
        api_headers = {
            **headers,
            "Origin": "https://drive.google.com",
            "Referer": "https://drive.google.com/",
        }
        if resource_key:
            api_headers["X-Goog-Drive-Resource-Keys"] = f"{folder_id}/{resource_key}"

        for key in keys:
            api_items: list[dict] = []
            page_token = ""
            api_ok = False
            while True:
                api_params = {
                    "openDrive": "true",
                    "reason": "102",
                    "syncType": "0",
                    "errorRecovery": "false",
                    "q": f"trashed = false and '{folder_id}' in parents",
                    "fields": (
                        "kind,nextPageToken,"
                        "items(id,title,mimeType,fileExtension,resourceKey,"
                        "shortcutDetails(targetId,targetMimeType))"
                    ),
                    "appDataFilter": "NO_APP_DATA",
                    "spaces": "drive",
                    "maxResults": "500",
                    "supportsTeamDrives": "true",
                    "includeItemsFromAllDrives": "true",
                    "corpora": "default",
                    "orderBy": "folder,title_natural asc",
                    "retryCount": "0",
                    "key": key,
                }
                if page_token:
                    api_params["pageToken"] = page_token
                try:
                    r_api = session.get(
                        "https://clients6.google.com/drive/v2beta/files",
                        params=api_params,
                        headers=api_headers,
                        timeout=20,
                    )
                except Exception:
                    break
                if r_api.status_code != 200:
                    break
                api_ok = True
                j = r_api.json()
                for it in j.get("items", []):
                    mime = it.get("mimeType") or ""
                    file_id = it.get("id") or ""
                    if mime == "application/vnd.google-apps.shortcut":
                        sd = it.get("shortcutDetails") or {}
                        file_id = sd.get("targetId") or file_id
                        mime = sd.get("targetMimeType") or mime
                    if file_id:
                        api_items.append({
                            "id": file_id,
                            "title": it.get("title") or "",
                            "mimeType": mime,
                            "fileExtension": it.get("fileExtension") or "",
                            "resourceKey": it.get("resourceKey") or "",
                        })
                page_token = j.get("nextPageToken")
                if not page_token:
                    break
            if api_ok and api_items:
                items = api_items
                break

    # ── 方式 3：embeddedfolderview 兜底解析 ─────────────────────────────────
    if not items:
        emb_url = f"https://drive.google.com/embeddedfolderview?id={folder_id}#list"
        r_emb = session.get(emb_url, params=params, headers=headers, timeout=20)
        if r_emb.status_code == 200:
            for m in re.finditer(
                r'<div class="flip-entry"[^>]*id="entry-([a-zA-Z0-9_-]+)"[^>]*>(.*?)</div>\s*</div>\s*</div>',
                r_emb.text,
                re.S,
            ):
                entry_id = m.group(1)
                block = m.group(2)
                if "/drive/folders/" in block:
                    continue
                t_m = re.search(r'<div class="flip-entry-title">(.*?)</div>', block, re.S)
                entry_title = t_m.group(1).strip() if t_m else entry_id
                items.append({
                    "id": entry_id,
                    "title": entry_title,
                    "mimeType": "video/*" if any(entry_title.lower().endswith(ext) for ext in _VIDEO_EXTENSIONS) else "",
                    "fileExtension": "",
                    "resourceKey": "",
                })

    videos = [it for it in items if _is_video_item(it)]
    videos.sort(key=_natural_sort_key)
    return folder_title, videos


def _sanitize_filename(name: str) -> str:
    """去掉 Windows 文件名非法字符。"""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def _classify_error(err_text: str, code: int) -> str:
    """将 yt-dlp 错误翻译为简洁中文。"""
    t = err_text.lower()
    if "no such file" in t or "access denied" in t or "permission" in t:
        return "权限不足或文件已被占用"
    if "private" in t:
        return "私人文件，无法下载"
    if "sign in" in t or "login" in t or "authenticate" in t:
        return "需要登录/授权（文件可能未公开分享）"
    if "not found" in t or "404" in t:
        return "文件不存在或链接已失效（404）"
    if "quota" in t or "download quota" in t:
        return "Google Drive 下载配额已超限，请稍后再试"
    if "no video formats" in t or "no formats" in t:
        return "找不到可下载的格式（尝试更新 yt-dlp）"
    if "http error 429" in t:
        return "请求过于频繁（HTTP 429），请稍后再试"
    if "http error 403" in t:
        return "访问被拒绝（HTTP 403）"
    if "network" in t or "connection" in t or "timed out" in t:
        return "网络连接失败，请检查网络"
    if "unable to extract" in t or "unsupported url" in t:
        return "无法解析该链接（请检查链接格式或更新 yt-dlp）"
    lines = [l.strip() for l in err_text.splitlines() if l.strip()]
    last = lines[-1] if lines else f"未知错误 (code {code})"
    return last[:120]


# ─────────────────────────────────────────────────────────────────────────────
#  主 UI 类
# ─────────────────────────────────────────────────────────────────────────────

class GDriveDownloaderUI(QWidget):

    def __init__(self):
        super().__init__()
        self.worker: GDriveWorker | None = None
        self.output_dir = ""
        self.settings = QSettings("MyCompany", "VideoToolbox")

        self._setup_ui()
        self._bind_events()
        self.load_settings()

    # ── 设置持久化 ─────────────────────────────────────────────────────────

    def load_settings(self):
        saved_dir = self.settings.value("gdrive_output_dir", "")
        if saved_dir and os.path.isdir(saved_dir):
            self.output_dir = saved_dir
            self.lbl_out_path.setText(f"已选择: {saved_dir}")
            self.lbl_out_path.setStyleSheet("")

    def save_settings(self):
        self.settings.setValue("gdrive_output_dir", self.output_dir)

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

        # ── 说明卡 ─────────────────────────────────────────────────────────
        card_hint, lay_hint = self._create_card("☁️ 谷歌云端文件批量下载")

        hint_text = QLabel(
            "在下方表格中粘贴或输入下载任务。"
            "第一列为 Google Drive 链接，第二列为自定义命名（不含扩展名）。\n"
            "支持 <b>单文件链接</b>（视频、图片、PDF、文档等）以及 <b>谷歌云端文件夹链接</b>（自动下载文件夹中的所有视频，命名自动按 自定义命名+01、02… 依次编号）。\n"
            "支持直接从 Excel / 表格工具复制后 <b>Ctrl+V</b> 粘贴到表格；"
            "也可右键插入行手动填写。命名留空将使用原文件标题。"
        )
        hint_text.setWordWrap(True)
        hint_text.setStyleSheet("color: #9ca3af; font-size: 9pt; line-height: 1.5;")
        lay_hint.addWidget(hint_text)

        # 链接格式说明
        fmt_label = QLabel(
            "📌 支持的 Google Drive 链接格式：\n"
            "  • https://drive.google.com/file/d/{FILE_ID}/view\n"
            "  • https://drive.google.com/open?id={FILE_ID}\n"
            "  • https://drive.google.com/uc?id={FILE_ID}\n"
            "  • https://drive.google.com/drive/folders/{FOLDER_ID}  （文件夹链接：自动下载内部所有视频并追加 01、02 序号）"
        )
        fmt_label.setStyleSheet(
            "color: #6b7280; font-size: 8.5pt; font-family: Consolas, monospace;"
        )
        lay_hint.addWidget(fmt_label)

        main.addWidget(card_hint)

        # ── 表格输入卡 ─────────────────────────────────────────────────────
        card_table, lay_table = self._create_card("📋 下载任务列表")

        # 操作提示行
        tbl_hint_row = QHBoxLayout()
        tbl_hint = QLabel(
            "✂️ 从 Excel 复制后在表格内按 Ctrl+V 粘贴  ·  右键可插入/删除行"
        )
        tbl_hint.setStyleSheet("color: #6b7280; font-size: 9pt;")
        tbl_hint_row.addWidget(tbl_hint)
        tbl_hint_row.addStretch()

        # 快捷按钮
        self.btn_add_row = QPushButton("＋ 添加行")
        self.btn_add_row.setFixedWidth(90)
        self.btn_del_row = QPushButton("－ 删除行")
        self.btn_del_row.setFixedWidth(90)
        self.btn_clear_table = QPushButton("🗑 清空")
        self.btn_clear_table.setFixedWidth(80)
        tbl_hint_row.addWidget(self.btn_add_row)
        tbl_hint_row.addWidget(self.btn_del_row)
        tbl_hint_row.addWidget(self.btn_clear_table)
        lay_table.addLayout(tbl_hint_row)

        # 表格
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Google Drive 文件/文件夹链接", "自定义命名（文件夹自动+01、02）"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(280)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            "QTableWidget { gridline-color: #2b303b; }"
            "QTableWidget::item { padding: 4px 6px; }"
            "QHeaderView::section { background-color: #1e222d; color: #d1d5db;"
            "  border: none; border-bottom: 1px solid #2b303b; padding: 6px; font-weight: bold; }"
        )
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # 预填 5 行空行方便用户看到结构
        for _ in range(5):
            self._append_empty_row()

        lay_table.addWidget(self.table)
        main.addWidget(card_table)

        # ── 输出目录卡 ────────────────────────────────────────────────────
        card_out, lay_out = self._create_card("📁 输出设置")

        out_row = QHBoxLayout()
        self.btn_out_path = QPushButton("📁 选择输出目录")
        self.btn_out_path.setFixedWidth(160)
        self.lbl_out_path = QLabel("尚未选择输出目录（上次选择将自动记住）")
        self.lbl_out_path.setStyleSheet("color: #6b7280;")
        out_row.addWidget(self.btn_out_path)
        out_row.addWidget(self.lbl_out_path, 1)
        lay_out.addLayout(out_row)
        main.addWidget(card_out)

        # ── 下载进度卡 ────────────────────────────────────────────────────
        card_prog, lay_prog = self._create_card("📊 下载进度")

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        lay_prog.addWidget(self.progress_bar)

        self.lbl_status = QLabel("就绪 — 请填写表格并点击「开始下载」")
        self.lbl_status.setStyleSheet("color: #6b7280; font-size: 9pt;")
        lay_prog.addWidget(self.lbl_status)

        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("🚀 开始下载")
        self.btn_start.setObjectName("PrimaryBtn")
        self.btn_start.setFixedHeight(46)
        self.btn_stop = QPushButton("🛑 停止下载")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setFixedHeight(46)
        btn_row.addWidget(self.btn_start, stretch=3)
        btn_row.addWidget(self.btn_stop, stretch=1)
        lay_prog.addLayout(btn_row)

        main.addWidget(card_prog)

        # ── 进度日志卡 ────────────────────────────────────────────────────
        card_log, lay_log = self._create_card("🔍 进度日志")

        log_btn_row = QHBoxLayout()
        log_btn_row.addStretch()
        self.btn_clear_log = QPushButton("🗑 清空日志")
        self.btn_clear_log.setFixedWidth(100)
        log_btn_row.addWidget(self.btn_clear_log)
        lay_log.addLayout(log_btn_row)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(220)
        self.log_view.setFont(QFont("Consolas", 9))
        self.log_view.setPlaceholderText("下载日志将在这里实时显示...")
        self.log_view.setStyleSheet(
            "QPlainTextEdit { background-color: #0d1117; color: #c9d1d9;"
            " border: 1px solid #30363d; border-radius: 6px; padding: 8px; }"
        )
        lay_log.addWidget(self.log_view)
        main.addWidget(card_log)
        main.addStretch()

    # ── 事件绑定 ──────────────────────────────────────────────────────────

    def _bind_events(self):
        self.btn_out_path.clicked.connect(self._select_output_dir)
        self.btn_start.clicked.connect(self._start_download)
        self.btn_stop.clicked.connect(self._stop_download)
        self.btn_clear_log.clicked.connect(self.log_view.clear)
        self.btn_add_row.clicked.connect(self._add_row)
        self.btn_del_row.clicked.connect(self._delete_selected_rows)
        self.btn_clear_table.clicked.connect(self._clear_table)

        # 表格右键菜单
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        # Ctrl+V 粘贴支持
        paste_shortcut = QShortcut(QKeySequence("Ctrl+V"), self.table)
        paste_shortcut.activated.connect(self._paste_from_clipboard)

    # ── 表格辅助方法 ──────────────────────────────────────────────────────

    def _append_empty_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(""))
        self.table.setItem(row, 1, QTableWidgetItem(""))

    def _add_row(self):
        """在当前选中行之后插入一行，若无选中则追加到末尾。"""
        selected = self.table.selectedItems()
        if selected:
            row = self.table.currentRow() + 1
        else:
            row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(""))
        self.table.setItem(row, 1, QTableWidgetItem(""))
        self.table.selectRow(row)

    def _delete_selected_rows(self):
        rows = sorted(set(i.row() for i in self.table.selectedItems()), reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def _clear_table(self):
        reply = QMessageBox.question(
            self, "确认清空", "确定要清空所有下载任务吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.table.setRowCount(0)
            for _ in range(5):
                self._append_empty_row()

    def _show_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        act_insert_above = menu.addAction("⬆ 在上方插入行")
        act_insert_below = menu.addAction("⬇ 在下方插入行")
        menu.addSeparator()
        act_delete = menu.addAction("🗑 删除选中行")
        menu.addSeparator()
        act_clear = menu.addAction("⚠ 清空全部")
        menu.addSeparator()
        act_paste = menu.addAction("📋 粘贴 (Ctrl+V)")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == act_insert_above:
            row = self.table.currentRow()
            if row < 0:
                row = 0
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(""))
            self.table.setItem(row, 1, QTableWidgetItem(""))
        elif action == act_insert_below:
            row = self.table.currentRow() + 1
            if row <= 0:
                row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(""))
            self.table.setItem(row, 1, QTableWidgetItem(""))
        elif action == act_delete:
            self._delete_selected_rows()
        elif action == act_clear:
            self._clear_table()
        elif action == act_paste:
            self._paste_from_clipboard()

    def _paste_from_clipboard(self):
        """
        将剪贴板中的 TSV（Tab 分隔，Excel 复制格式）数据粘贴到表格。
        - 每行对应一条任务
        - 第1列 → 链接，第2列 → 命名
        - 若剪贴板只有一列，则全部放到链接列
        - 在当前选中行之后插入；若无选中则追加到末尾第一个空行或末尾
        """
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if not text:
            return

        lines = text.splitlines()
        if not lines:
            return

        # 确定插入起始行
        current = self.table.currentRow()
        if current < 0:
            insert_at = self._find_first_empty_row()
        else:
            insert_at = current + 1

        for offset, line in enumerate(lines):
            cols = line.split("\t")
            url  = cols[0].strip() if len(cols) > 0 else ""
            name = cols[1].strip() if len(cols) > 1 else ""

            target_row = insert_at + offset
            # 如果目标行超出范围，插入新行
            if target_row >= self.table.rowCount():
                self.table.insertRow(self.table.rowCount())
                self.table.setItem(self.table.rowCount() - 1, 0, QTableWidgetItem(""))
                self.table.setItem(self.table.rowCount() - 1, 1, QTableWidgetItem(""))
                target_row = self.table.rowCount() - 1

            # 如果目标行是空行，直接填写；否则插入新行
            existing_url = self.table.item(target_row, 0)
            if existing_url and existing_url.text().strip():
                self.table.insertRow(target_row)
                self.table.setItem(target_row, 0, QTableWidgetItem(""))
                self.table.setItem(target_row, 1, QTableWidgetItem(""))

            self.table.setItem(target_row, 0, QTableWidgetItem(url))
            self.table.setItem(target_row, 1, QTableWidgetItem(name))

    def _find_first_empty_row(self) -> int:
        """返回第一个链接列为空的行下标，没有则返回 rowCount（追加）。"""
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if not item or not item.text().strip():
                return r
        return self.table.rowCount()

    def _get_tasks(self) -> list[tuple[str, str]]:
        """提取所有有效任务（链接不为空）。"""
        tasks = []
        for r in range(self.table.rowCount()):
            url_item  = self.table.item(r, 0)
            name_item = self.table.item(r, 1)
            url  = url_item.text().strip()  if url_item  else ""
            name = name_item.text().strip() if name_item else ""
            if url:
                tasks.append((url, name))
        return tasks

    # ── 输出目录 ──────────────────────────────────────────────────────────

    def _select_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.output_dir = d
            self.lbl_out_path.setText(f"已选择: {d}")
            self.lbl_out_path.setStyleSheet("")
            # 立即持久化，重启后自动恢复
            self.settings.setValue("gdrive_output_dir", d)

    # ── 下载控制 ──────────────────────────────────────────────────────────

    def _start_download(self):
        tasks = self._get_tasks()
        if not tasks:
            QMessageBox.warning(self, "提示", "请先在表格中填写至少一条下载链接！")
            return
        if not self.output_dir:
            QMessageBox.warning(self, "提示", "请先选择输出目录！")
            return

        self.log_view.clear()
        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"准备处理 {len(tasks)} 条下载任务...")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        # 高亮正在下载的行（重置颜色）
        for r in range(self.table.rowCount()):
            for c in range(2):
                item = self.table.item(r, c)
                if item:
                    item.setForeground(QColor("#d1d5db"))

        # 查找 ffmpeg 路径
        if getattr(sys, 'frozen', False):
            _root = os.path.dirname(sys.executable)
        else:
            _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ffmpeg_dir = os.path.join(_root, "ffmpeg")
        if not os.path.isdir(ffmpeg_dir):
            ffmpeg_dir = ""

        self.worker = GDriveWorker(
            tasks=tasks,
            output_dir=self.output_dir,
            ffmpeg_dir=ffmpeg_dir,
        )
        self.worker.log_line.connect(self._on_log_line)
        self.worker.item_done.connect(self._on_item_done)
        self.worker.overall_progress.connect(self._on_overall_progress)
        self.worker.all_done.connect(self._on_all_done)
        self.worker.start()

        self._log(f"🚀 开始批量下载，共 {len(tasks)} 条任务")
        self._log(f"📁 输出目录：{self.output_dir}")

    def _stop_download(self):
        if self.worker:
            self.worker.stop()
            self.lbl_status.setText("正在停止，请稍候...")
            self.btn_stop.setEnabled(False)

    # ── Worker 信号槽 ─────────────────────────────────────────────────────

    def _on_log_line(self, line: str):
        self.log_view.appendPlainText(line)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_item_done(self, idx: int, success: bool, msg: str):
        """根据任务列表下标，更新对应表格行的颜色。"""
        # 找到第 idx 个有效任务对应的实际表格行
        valid_row = self._get_valid_row_index(idx)
        if valid_row >= 0:
            color = QColor("#22c55e") if success else QColor("#ef4444")
            for c in range(2):
                item = self.table.item(valid_row, c)
                if item:
                    item.setForeground(color)

    def _on_overall_progress(self, pct: int, text: str):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(text)

    def _on_all_done(self, success: bool, message: str):
        self.progress_bar.setValue(100 if success else self.progress_bar.value())
        self.lbl_status.setText(message)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._log(f"\n{'═'*60}")
        self._log(f"🏁 {message}")
        if success:
            QMessageBox.information(self, "下载完成", message)
        else:
            QMessageBox.warning(self, "下载结束", message)

    # ── 辅助 ──────────────────────────────────────────────────────────────

    def _log(self, text: str):
        self.log_view.appendPlainText(text)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _get_valid_row_index(self, task_idx: int) -> int:
        """将任务序号（仅计有效行）转换为实际表格行号。"""
        count = 0
        for r in range(self.table.rowCount()):
            url_item = self.table.item(r, 0)
            if url_item and url_item.text().strip():
                if count == task_idx:
                    return r
                count += 1
        return -1
