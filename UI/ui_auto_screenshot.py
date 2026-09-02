# ui_auto_screenshot.py
"""
「📸 链接截图」标签页 UI
功能：批量输入视频链接 → 下载 → 分帧截图
可选：保存视频 / 保存音频
支持 Cookie 管理（Share Your Cookies 插件格式 / Netscape 格式）
"""

import base64
import json
import os
import re
import sys
import uuid

from PyQt6.QtCore import Qt, QSettings, QUrl
from PyQt6.QtGui import QFont, QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QSpinBox, QDoubleSpinBox, QLineEdit,
    QFileDialog, QFrame, QProgressBar, QAbstractSpinBox,
    QScrollArea, QSizePolicy, QMessageBox, QCheckBox,
    QGridLayout, QDialog, QComboBox, QListWidget, QListWidgetItem,
)

from image_worker.screenshot_worker import ScreenshotWorker


# ══════════════════════════════════════════════════════════════════════════════
#  Cookie 格式转换工具
# ══════════════════════════════════════════════════════════════════════════════

def _convert_to_netscape(raw_text: str) -> str:
    """
    将「Share Your Cookies」插件导出的 Base64-JSON 格式，
    以及标准 JSON 格式，统一转换为 yt-dlp 支持的 Netscape 文本格式。
    若输入已经是 Netscape 格式（以 # 开头），则原样返回。
    """
    raw_text = raw_text.strip()
    if not raw_text:
        raise ValueError("Cookie 内容不能为空")

    # 已是 Netscape 格式
    if raw_text.startswith("#"):
        return raw_text

    cookies = []

    # ── 尝试 Base64 解码（Share Your Cookies 插件格式） ──────────────────
    try:
        # 补全 Base64 填充
        padded = raw_text + "=" * ((4 - len(raw_text) % 4) % 4)
        decoded = base64.b64decode(padded).decode("utf-8", errors="replace")

        # 格式：{JSON};{JSON};...
        # 用正则按 };{ 分割，保留括号
        parts = re.split(r"\}\s*;\s*\{", decoded)
        for i, part in enumerate(parts):
            # 修复首尾括号
            if len(parts) == 1:
                obj_str = part
            elif i == 0:
                obj_str = part + "}"
            elif i == len(parts) - 1:
                obj_str = "{" + part
            else:
                obj_str = "{" + part + "}"
            cookies.append(json.loads(obj_str.strip()))
    except Exception:
        pass

    # ── 尝试直接解析 JSON ──────────────────────────────────────────────
    if not cookies:
        try:
            data = json.loads(raw_text)
            if isinstance(data, list):
                cookies = data
            elif isinstance(data, dict):
                cookies = [data]
        except Exception:
            pass

    if not cookies:
        raise ValueError(
            "无法识别 Cookie 格式。\n\n"
            "支持的格式：\n"
            "① Share Your Cookies 插件导出的 Base64 字符串\n"
            "② JSON 数组 / 对象\n"
            "③ Netscape 格式（以 # 开头的文本）"
        )

    # ── 转换为 Netscape 格式 ─────────────────────────────────────────────
    lines = [
        "# Netscape HTTP Cookie File",
        "# Converted by VideoTools from Share Your Cookies format",
    ]
    for c in cookies:
        domain      = c.get("domain", "")
        include_sub = "TRUE" if domain.startswith(".") else "FALSE"
        path        = c.get("path", "/")
        secure      = "TRUE" if c.get("secure", False) else "FALSE"
        expiry      = str(int(c.get("expirationDate", 0)))
        name        = c.get("name", "")
        value       = c.get("value", "")
        lines.append(f"{domain}\t{include_sub}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  Cookie 管理器
# ══════════════════════════════════════════════════════════════════════════════

class CookieManager:
    """
    管理截图工具的 Cookie 条目。
    元数据存在 QSettings，Cookie 文件（Netscape .txt）存在磁盘。
    """

    # Cookie 文件目录：%APPDATA%\MyCompany\VideoToolbox\cookies\
    COOKIE_DIR = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "MyCompany", "VideoToolbox", "cookies"
    )

    def __init__(self, settings: QSettings):
        self._settings = settings
        os.makedirs(self.COOKIE_DIR, exist_ok=True)
        self._entries: list[dict] = self._load()

    # ── 持久化 ────────────────────────────────────────────────────────────

    def _load(self) -> list[dict]:
        try:
            raw = self._settings.value("ss_cookies", "[]")
            entries = json.loads(raw) if raw else []
            # 过滤掉文件不存在的条目
            return [e for e in entries if os.path.isfile(e.get("file_path", ""))]
        except Exception:
            return []

    def _save(self):
        self._settings.setValue("ss_cookies", json.dumps(self._entries))

    # ── 公共接口 ──────────────────────────────────────────────────────────

    def get_all(self) -> list[dict]:
        return list(self._entries)

    def get_by_id(self, entry_id: str) -> dict | None:
        for e in self._entries:
            if e["id"] == entry_id:
                return e
        return None

    def add(self, label: str, platform: str, cookie_text: str) -> dict:
        """新增一条 Cookie。将内容转换为 Netscape 格式并写入文件。"""
        netscape = _convert_to_netscape(cookie_text)

        entry_id  = uuid.uuid4().hex[:10]
        file_name = f"cookie_{entry_id}.txt"
        file_path = os.path.join(self.COOKIE_DIR, file_name)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(netscape)

        entry = {
            "id":        entry_id,
            "label":     label,
            "platform":  platform,
            "file_path": file_path,
        }
        self._entries.append(entry)
        self._save()
        return entry

    def delete(self, entry_id: str):
        """删除一条 Cookie（同时删除磁盘文件）。"""
        entry = self.get_by_id(entry_id)
        if entry:
            try:
                os.remove(entry["file_path"])
            except Exception:
                pass
        self._entries = [e for e in self._entries if e["id"] != entry_id]
        self._save()


# ══════════════════════════════════════════════════════════════════════════════
#  添加 Cookie 弹窗
# ══════════════════════════════════════════════════════════════════════════════

class AddCookieDialog(QDialog):
    """弹出对话框，让用户输入 Cookie 信息并保存。"""

    PLUGIN_URL = (
        "https://chromewebstore.google.com/detail/"
        "share-your-cookies/poijkganimmndbhghgkmnfgpiejmlpke"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🍪 添加 Cookie")
        self.setMinimumWidth(540)
        self.setMinimumHeight(460)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── 插件说明 ─────────────────────────────────────────────────────
        tip = QLabel(
            "请使用「<b>Share Your Cookies</b>」Chrome 插件获取 Cookie，"
            "然后将复制的内容粘贴到下方文本框中。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #6b7280; font-size: 9pt;")
        layout.addWidget(tip)

        btn_plugin = QPushButton("🔗 前往 Chrome 网上应用店安装插件")
        btn_plugin.setToolTip(self.PLUGIN_URL)
        btn_plugin.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(self.PLUGIN_URL))
        )
        layout.addWidget(btn_plugin)

        # ── 表单：备注 / 平台 ────────────────────────────────────────────
        form = QGridLayout()
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(14)
        form.setColumnStretch(1, 1)

        form.addWidget(QLabel("备注名称:"), 0, 0)
        self.edit_label = QLineEdit()
        self.edit_label.setPlaceholderText("例如：Instagram 主账号")
        form.addWidget(self.edit_label, 0, 1)

        form.addWidget(QLabel("平台:"), 1, 0)
        self.combo_platform = QComboBox()
        self.combo_platform.addItems(["Instagram", "Facebook", "通用"])
        form.addWidget(self.combo_platform, 1, 1)

        layout.addLayout(form)

        # ── Cookie 粘贴区 ─────────────────────────────────────────────────
        layout.addWidget(QLabel("Cookie 内容（粘贴从插件复制的字符串）:"))
        self.text_cookie = QPlainTextEdit()
        self.text_cookie.setPlaceholderText(
            "粘贴「Share Your Cookies」插件导出的 Base64 字符串，\n"
            "或 Netscape 格式（以 # 开头的文本）...\n\n"
            "支持格式：\n"
            "① Share Your Cookies 插件 Base64 字符串\n"
            "② JSON 数组\n"
            "③ Netscape cookie.txt 文件内容"
        )
        self.text_cookie.setMinimumHeight(180)
        self.text_cookie.setFont(QFont("Consolas", 9))
        layout.addWidget(self.text_cookie)

        # ── 操作按钮 ──────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_save   = QPushButton("💾 保存")
        self.btn_cancel = QPushButton("取消")
        self.btn_save.setFixedWidth(100)
        self.btn_cancel.setFixedWidth(80)
        btn_row.addWidget(self.btn_save)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel.clicked.connect(self.reject)

    def _on_save(self):
        if not self.edit_label.text().strip():
            QMessageBox.warning(self, "提示", "请填写备注名称！")
            return
        if not self.text_cookie.toPlainText().strip():
            QMessageBox.warning(self, "提示", "请粘贴 Cookie 内容！")
            return
        # 预先做一次格式校验，给用户即时反馈
        try:
            _convert_to_netscape(self.text_cookie.toPlainText().strip())
        except ValueError as e:
            QMessageBox.warning(self, "Cookie 格式错误", str(e))
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "label":       self.edit_label.text().strip(),
            "platform":    self.combo_platform.currentText(),
            "cookie_text": self.text_cookie.toPlainText().strip(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  链接截图主界面
# ══════════════════════════════════════════════════════════════════════════════

class AutoScreenshotUI(QWidget):
    """链接批量截图页面"""

    PLUGIN_URL = (
        "https://chromewebstore.google.com/detail/"
        "share-your-cookies/poijkganimmndbhghgkmnfgpiejmlpke"
    )

    def __init__(self):
        super().__init__()
        self.worker: ScreenshotWorker | None = None
        self.output_dir = ""
        self.settings = QSettings("MyCompany", "VideoToolbox")
        self.cookie_manager = CookieManager(self.settings)

        self._setup_ui()
        self._bind_events()
        self.load_settings()

    # ── 持久化设置 ────────────────────────────────────────────────────────

    def load_settings(self):
        self.spin_count.setValue(
            self.settings.value("ss_count", 10, type=int))
        self.spin_interval.setValue(
            self.settings.value("ss_interval", 0.5, type=float))
        self.edit_name.setText(
            self.settings.value("ss_name", "截图项目", type=str))
        self.chk_save_video.setChecked(
            self.settings.value("ss_save_video", False, type=bool))
        self.chk_save_audio.setChecked(
            self.settings.value("ss_save_audio", False, type=bool))
        saved_dir = self.settings.value("ss_output_dir", "")
        if saved_dir and os.path.isdir(saved_dir):
            self.output_dir = saved_dir
            self.lbl_out_path.setText(f"已选择: {saved_dir}")

        # Cookie 设置
        self._refresh_cookie_ui()
        saved_mode = self.settings.value("ss_cookie_mode", "不使用")
        idx = self.combo_cookie_mode.findText(saved_mode)
        if idx >= 0:
            self.combo_cookie_mode.setCurrentIndex(idx)
        saved_cookie_id = self.settings.value("ss_cookie_id", "")
        if saved_cookie_id:
            sel_idx = self.combo_cookie_select.findData(saved_cookie_id)
            if sel_idx >= 0:
                self.combo_cookie_select.setCurrentIndex(sel_idx)
        self._on_cookie_mode_changed()

    def save_settings(self):
        self.settings.setValue("ss_count",      self.spin_count.value())
        self.settings.setValue("ss_interval",   self.spin_interval.value())
        self.settings.setValue("ss_name",       self.edit_name.text().strip())
        self.settings.setValue("ss_save_video", self.chk_save_video.isChecked())
        self.settings.setValue("ss_save_audio", self.chk_save_audio.isChecked())
        self.settings.setValue("ss_output_dir", self.output_dir)
        self.settings.setValue("ss_cookie_mode", self.combo_cookie_mode.currentText())
        self.settings.setValue("ss_cookie_id",   self.combo_cookie_select.currentData() or "")

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
        # 外层滚动容器（与其他标签页完全一致）
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

        # ═══════════════════════════════════════════════════════════════════
        # 板块一：链接输入
        # ═══════════════════════════════════════════════════════════════════
        card1, lay1 = self._create_card("🔗 板块一 · 输入视频链接（每行一个）")

        hint1 = QLabel(
            "支持 YouTube、B站、抖音、Instagram、Facebook 等主流平台链接，批量粘贴，每行一个"
        )
        hint1.setStyleSheet("color: #6b7280; font-size: 9pt;")
        lay1.addWidget(hint1)

        self.text_urls = QPlainTextEdit()
        self.text_urls.setPlaceholderText(
            "https://www.youtube.com/watch?v=xxxxxxx\n"
            "https://www.instagram.com/reel/xxxxxxx/\n"
            "https://www.facebook.com/reel/xxxxxxx\n"
            "..."
        )
        self.text_urls.setMinimumHeight(140)
        self.text_urls.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        lay1.addWidget(self.text_urls)

        url_btn_row = QHBoxLayout()
        url_btn_row.addStretch()
        self.btn_clear_urls = QPushButton("🗑 清空链接")
        url_btn_row.addWidget(self.btn_clear_urls)
        lay1.addLayout(url_btn_row)

        main.addWidget(card1)

        # ═══════════════════════════════════════════════════════════════════
        # 板块二：参数设置
        # ═══════════════════════════════════════════════════════════════════
        card2, lay2 = self._create_card("⚙️ 板块二 · 截图参数设置")

        # 参数网格
        grid = QGridLayout()
        grid.setVerticalSpacing(14)
        grid.setHorizontalSpacing(20)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)
        _W = 200   # 输入控件最大宽度

        # Row 0 — 截取数量 / 间隔秒数
        grid.addWidget(QLabel("截取数量（张）:"), 0, 0)
        self.spin_count = QSpinBox()
        self.spin_count.setRange(1, 9999)
        self.spin_count.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_count.setMaximumWidth(_W)
        self.spin_count.setToolTip("每个视频最多截取多少帧图片")
        grid.addWidget(self.spin_count, 0, 1)

        grid.addWidget(QLabel("截图间隔（秒）:"), 0, 2)
        self.spin_interval = QDoubleSpinBox()
        self.spin_interval.setRange(0.1, 60.0)
        self.spin_interval.setSingleStep(0.1)
        self.spin_interval.setDecimals(1)
        self.spin_interval.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_interval.setMaximumWidth(_W)
        self.spin_interval.setToolTip("相邻两帧之间的时间间隔（秒）")
        grid.addWidget(self.spin_interval, 0, 3)

        # Row 1 — 项目名称
        grid.addWidget(QLabel("项目名称:"), 1, 0)
        self.edit_name = QLineEdit()
        self.edit_name.setMaximumWidth(_W)
        self.edit_name.setToolTip('生成的输出文件夹前缀，如"截图项目_001"')
        grid.addWidget(self.edit_name, 1, 1)

        lay2.addLayout(grid)

        # 输出目录
        out_row = QHBoxLayout()
        out_row.setSpacing(10)
        self.btn_out_path = QPushButton("📁 选择输出目录")
        self.btn_out_path.setFixedWidth(150)
        self.lbl_out_path = QLabel("尚未选择输出目录")
        self.lbl_out_path.setStyleSheet("color: #6b7280;")
        out_row.addWidget(self.btn_out_path)
        out_row.addWidget(self.lbl_out_path, 1)
        lay2.addLayout(out_row)

        # ── 保存开关 ────────────────────────────────────────────────────
        save_row = QHBoxLayout()
        save_row.setSpacing(30)

        self.chk_save_video = QCheckBox("🎬  保存视频")
        self.chk_save_video.setToolTip(
            "勾选后：下载的视频文件将一并保存到对应输出目录中"
        )
        save_row.addWidget(self.chk_save_video)

        self.chk_save_audio = QCheckBox("🎵  保存音频")
        self.chk_save_audio.setToolTip(
            "勾选后：从视频中提取音频（mp3），保存到对应输出目录中"
        )
        save_row.addWidget(self.chk_save_audio)
        save_row.addStretch()

        save_frame = QFrame()
        save_frame.setObjectName("SaveToggleFrame")
        save_frame.setStyleSheet("""
            QFrame#SaveToggleFrame {
                border: 1px dashed #374151;
                border-radius: 8px;
                padding: 4px 8px;
            }
        """)
        save_frame.setLayout(save_row)
        lay2.addWidget(save_frame)

        main.addWidget(card2)

        # ═══════════════════════════════════════════════════════════════════
        # 板块三：Cookie 管理
        # ═══════════════════════════════════════════════════════════════════
        card3, lay3 = self._create_card("🍪 板块三 · Cookie 管理（Instagram / Facebook 等平台）")

        # 说明文字
        hint_ck = QLabel(
            "部分平台（如 Instagram、Facebook）需要登录 Cookie 才能下载私密视频。\n"
            "请安装「Share Your Cookies」插件，在浏览器中登录对应平台后导出 Cookie，\n"
            "再点击「➕ 添加 Cookie」粘贴到软件中。"
        )
        hint_ck.setStyleSheet("color: #6b7280; font-size: 9pt;")
        hint_ck.setWordWrap(True)
        lay3.addWidget(hint_ck)

        # 安装插件按钮
        plugin_row = QHBoxLayout()
        self.btn_install_plugin = QPushButton("🔗 安装「Share Your Cookies」插件（Chrome）")
        self.btn_install_plugin.setToolTip(self.PLUGIN_URL)
        plugin_row.addWidget(self.btn_install_plugin)
        plugin_row.addStretch()
        lay3.addLayout(plugin_row)

        # Cookie 列表
        self.cookie_list = QListWidget()
        self.cookie_list.setMinimumHeight(90)
        self.cookie_list.setMaximumHeight(160)
        self.cookie_list.setToolTip("已保存的 Cookie 列表，选中后可删除")
        lay3.addWidget(self.cookie_list)

        # 添加 / 删除按钮
        ck_btn_row = QHBoxLayout()
        ck_btn_row.setSpacing(10)
        self.btn_add_cookie = QPushButton("➕ 添加 Cookie")
        self.btn_del_cookie = QPushButton("🗑 删除选中")
        self.btn_del_cookie.setEnabled(False)
        ck_btn_row.addWidget(self.btn_add_cookie)
        ck_btn_row.addWidget(self.btn_del_cookie)
        ck_btn_row.addStretch()
        lay3.addLayout(ck_btn_row)

        # 使用模式
        mode_frame = QFrame()
        mode_frame.setObjectName("CookieModeFrame")
        mode_frame.setStyleSheet("""
            QFrame#CookieModeFrame {
                border: 1px dashed #374151;
                border-radius: 8px;
                padding: 6px 10px;
            }
        """)
        mode_layout = QHBoxLayout(mode_frame)
        mode_layout.setSpacing(12)
        mode_layout.setContentsMargins(0, 0, 0, 0)

        mode_layout.addWidget(QLabel("下载时使用 Cookie："))
        self.combo_cookie_mode = QComboBox()
        self.combo_cookie_mode.addItems(["不使用", "自动（失败时重试）", "始终使用"])
        self.combo_cookie_mode.setToolTip(
            "不使用：不携带 Cookie\n"
            "自动（失败时重试）：先不用 Cookie 下载，失败后再用 Cookie 重试（推荐 Instagram）\n"
            "始终使用：每次都携带 Cookie"
        )
        self.combo_cookie_mode.setMinimumWidth(180)
        mode_layout.addWidget(self.combo_cookie_mode)

        mode_layout.addWidget(QLabel("使用哪条："))
        self.combo_cookie_select = QComboBox()
        self.combo_cookie_select.setMinimumWidth(200)
        self.combo_cookie_select.setEnabled(False)
        mode_layout.addWidget(self.combo_cookie_select)
        mode_layout.addStretch()

        lay3.addWidget(mode_frame)
        main.addWidget(card3)

        # ═══════════════════════════════════════════════════════════════════
        # 板块四：进度与日志
        # ═══════════════════════════════════════════════════════════════════
        card4, lay4 = self._create_card("📊 板块四 · 进度与运行日志")

        # 总进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setTextVisible(True)
        lay4.addWidget(self.progress_bar)

        # 状态文字
        self.lbl_status = QLabel("就绪 — 请输入链接并点击「开始执行」")
        self.lbl_status.setStyleSheet("color: #6b7280; font-size: 9pt;")
        lay4.addWidget(self.lbl_status)

        # 实时日志区
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(220)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setPlaceholderText("运行日志将在此处实时显示...")
        lay4.addWidget(self.log_text)

        # 操作按钮
        btn_row = QHBoxLayout()
        self.btn_clear_log = QPushButton("🗑 清空日志")
        self.btn_clear_log.setFixedWidth(110)
        btn_row.addWidget(self.btn_clear_log)
        btn_row.addStretch()

        self.btn_start = QPushButton("🚀 开始执行任务")
        self.btn_start.setObjectName("PrimaryBtn")
        self.btn_start.setFixedHeight(46)

        self.btn_stop = QPushButton("🛑 停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setFixedHeight(46)

        btn_row.addWidget(self.btn_start, stretch=3)
        btn_row.addWidget(self.btn_stop, stretch=1)
        lay4.addLayout(btn_row)

        main.addWidget(card4)
        main.addStretch()

    # ── 事件绑定 ──────────────────────────────────────────────────────────

    def _bind_events(self):
        self.btn_clear_urls.clicked.connect(self.text_urls.clear)
        self.btn_clear_log.clicked.connect(self.log_text.clear)
        self.btn_out_path.clicked.connect(self._select_output_dir)
        self.btn_start.clicked.connect(self._start_task)
        self.btn_stop.clicked.connect(self._stop_task)
        # Cookie
        self.btn_install_plugin.clicked.connect(self._on_install_plugin)
        self.btn_add_cookie.clicked.connect(self._on_add_cookie)
        self.btn_del_cookie.clicked.connect(self._on_del_cookie)
        self.combo_cookie_mode.currentTextChanged.connect(self._on_cookie_mode_changed)
        self.cookie_list.currentRowChanged.connect(self._on_cookie_list_selection)

    # ── Cookie 槽函数 ─────────────────────────────────────────────────────

    def _on_install_plugin(self):
        """打开 Chrome 网上应用店安装 Share Your Cookies 插件。"""
        QDesktopServices.openUrl(QUrl(self.PLUGIN_URL))

    def _on_add_cookie(self):
        dlg = AddCookieDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                self.cookie_manager.add(data["label"], data["platform"], data["cookie_text"])
                self._refresh_cookie_ui()
                QMessageBox.information(
                    self, "✅ 已保存",
                    f"Cookie「{data['label']}」已保存！\n\n"
                    "可在下方选择此 Cookie 进行下载。"
                )
            except ValueError as e:
                QMessageBox.warning(self, "Cookie 格式错误", str(e))
            except Exception as e:
                QMessageBox.warning(self, "保存失败", f"保存 Cookie 时出错：{e}")

    def _on_del_cookie(self):
        item = self.cookie_list.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请先在列表中选择要删除的 Cookie！")
            return
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        entry = self.cookie_manager.get_by_id(entry_id)
        if not entry:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 Cookie「{entry['label']}」吗？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.cookie_manager.delete(entry_id)
            self._refresh_cookie_ui()

    def _on_cookie_mode_changed(self):
        mode = self.combo_cookie_mode.currentText()
        has_cookies = self.combo_cookie_select.count() > 0
        use_cookie  = (mode != "不使用")
        self.combo_cookie_select.setEnabled(use_cookie and has_cookies)

    def _on_cookie_list_selection(self):
        self.btn_del_cookie.setEnabled(self.cookie_list.currentRow() >= 0)

    def _refresh_cookie_ui(self):
        """刷新 Cookie 列表 Widget 和选择下拉框。"""
        # ── 列表 ──────────────────────────────────────────────────────────
        self.cookie_list.clear()
        entries = self.cookie_manager.get_all()
        for e in entries:
            platform_icons = {"Instagram": "📸", "Facebook": "👤"}
            icon = platform_icons.get(e["platform"], "🌐")
            text = f"{icon}  {e['label']}  [{e['platform']}]"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, e["id"])
            self.cookie_list.addItem(item)

        # ── 选择下拉框 ────────────────────────────────────────────────────
        prev_id = self.combo_cookie_select.currentData()
        self.combo_cookie_select.clear()
        for e in entries:
            self.combo_cookie_select.addItem(
                f"{e['label']}  [{e['platform']}]", e["id"]
            )
        # 尽量保留之前选中的条目
        if prev_id:
            idx = self.combo_cookie_select.findData(prev_id)
            if idx >= 0:
                self.combo_cookie_select.setCurrentIndex(idx)

        has_cookies = len(entries) > 0
        self.btn_del_cookie.setEnabled(False)  # 重置（需重新点选）
        self._on_cookie_mode_changed()

    # ── 普通槽函数 ────────────────────────────────────────────────────────

    def _select_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.output_dir = d
            self.lbl_out_path.setText(f"已选择: {d}")
            self.lbl_out_path.setStyleSheet("")

    def _get_urls(self) -> list:
        raw = self.text_urls.toPlainText().strip()
        return [u.strip() for u in raw.splitlines() if u.strip()]

    def _append_log(self, msg: str):
        self.log_text.appendPlainText(msg)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── 开始任务 ──────────────────────────────────────────────────────────

    def _start_task(self):
        urls = self._get_urls()
        if not urls:
            QMessageBox.warning(self, "提示", "请先输入至少一个视频链接！")
            return
        if not self.output_dir:
            QMessageBox.warning(self, "提示", "请先选择输出目录！")
            return
        if not self.edit_name.text().strip():
            QMessageBox.warning(self, "提示", "请填写项目名称！")
            return

        # 定位 ffmpeg 目录
        if getattr(sys, "frozen", False):
            _root = os.path.dirname(sys.executable)
        else:
            _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ffmpeg_dir = os.path.join(_root, "ffmpeg")
        if not os.path.isdir(ffmpeg_dir):
            ffmpeg_dir = ""

        # ── Cookie 参数 ────────────────────────────────────────────────
        cookie_file = ""
        cookie_mode = "none"
        mode_text = self.combo_cookie_mode.currentText()
        if mode_text == "自动（失败时重试）":
            cookie_mode = "auto"
        elif mode_text == "始终使用":
            cookie_mode = "always"

        if cookie_mode != "none":
            entry_id = self.combo_cookie_select.currentData()
            if entry_id:
                entry = self.cookie_manager.get_by_id(entry_id)
                if entry and os.path.isfile(entry["file_path"]):
                    cookie_file = entry["file_path"]
                else:
                    QMessageBox.warning(
                        self, "Cookie 丢失",
                        "所选 Cookie 文件不存在，请重新添加。\n将以「不使用」模式运行。"
                    )
                    cookie_mode = "none"
            else:
                QMessageBox.warning(
                    self, "未选择 Cookie",
                    "请在「使用哪条」下拉框中选择一条 Cookie，\n或将模式改为「不使用」。"
                )
                return

        # 初始化 UI 状态
        self.log_text.clear()
        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"准备处理 {len(urls)} 个链接...")
        if cookie_mode != "none":
            entry = self.cookie_manager.get_by_id(self.combo_cookie_select.currentData())
            self._append_log(
                f"🍪 Cookie 模式：{mode_text}  |  使用：{entry['label']} [{entry['platform']}]"
            )
        self._set_running(True)

        self.worker = ScreenshotWorker(
            urls             = urls,
            max_count        = self.spin_count.value(),
            interval         = self.spin_interval.value(),
            base_path        = self.output_dir,
            base_folder_name = self.edit_name.text().strip(),
            save_video       = self.chk_save_video.isChecked(),
            save_audio       = self.chk_save_audio.isChecked(),
            ffmpeg_dir       = ffmpeg_dir,
            cookie_file      = cookie_file,
            cookie_mode      = cookie_mode,
        )
        self.worker.log_signal.connect(self._append_log)
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _stop_task(self):
        if self.worker:
            self.worker.stop()
            self.lbl_status.setText("正在停止，请稍候...")
            self.btn_stop.setEnabled(False)

    def _set_running(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)

    # ── Worker 信号槽 ─────────────────────────────────────────────────────

    def _on_progress(self, pct: int, text: str):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(text)

    def _on_finished(self, success: bool, message: str):
        self._set_running(False)
        self.progress_bar.setValue(100 if success else self.progress_bar.value())
        self.lbl_status.setText(message)
        if success:
            QMessageBox.information(self, "完成", message)
        else:
            QMessageBox.warning(self, "任务结束", message)
