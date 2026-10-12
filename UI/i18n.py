# -*- coding: utf-8 -*-
"""
VideoTools 界面多语言（中文 / English）。

设计说明
--------
整个软件的界面文字原本都是直接写在代码里的中文。为了不改动上千处业务代码
（很多逻辑会拿界面文字做比较、或把它存进设置文件），这里采用“显示层翻译”：

1. 语言设置存放在 QSettings("MyCompany", "VideoToolbox") 的 "language" 键里
   （"zh" / "en"），切换后重启软件生效。
2. 选择 English 时，install() 会给常用 Qt 控件的“设置文字”方法打补丁
   （setText / setToolTip / addItem / setTitle ……），并在控件显示时扫描一次
   构造函数里传入的文字，把中文换成英文后再显示。
3. 同时给“读取文字”的方法（text() / currentText() / findText() ……）打补丁，
   让业务代码读到的仍然是原来的中文，所以原有的判断逻辑完全不受影响。
4. 翻译表在 UI/i18n_en.py（自动从源码中提取后翻译）。带变量的句子
   （f-string、% 格式化）按模板匹配。

只影响界面显示，不影响导出的视频、卡片文字、文件名和设置文件内容。
"""
import os
import re

from PyQt6.QtCore import QSettings, QObject, QEvent, Qt

ORG, APP = "MyCompany", "VideoToolbox"
LANGUAGES = [("zh", "简体中文"), ("en", "English")]

_CJK = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")
_HAN = re.compile(r"[\u4e00-\u9fff]")
_PATHLIKE = re.compile(r"([A-Za-z]:[\\/])|(^[\\/])|(\.[A-Za-z0-9]{2,4}$)")
_PH = re.compile(r"\{\d+\}|%\.?\d*[sdif]|\{[A-Za-z_][^{}]*\}|\{\}")
ROLE = int(Qt.ItemDataRole.UserRole) + 0x5A5          # 存放原文（中文）的数据角色


# ── 语言设置 ──────────────────────────────────────────────────────────
def get_language():
    v = QSettings(ORG, APP).value("language", "zh")
    return v if v in ("zh", "en") else "zh"


def set_language(lang):
    s = QSettings(ORG, APP)
    s.setValue("language", lang)
    s.sync()


LANG = get_language()

# 手工补充 / 覆盖的翻译（设置页等新增文字）
MANUAL = {
    "⚙️ 设置": "⚙️ Settings",
    "设置": "Settings",
    "软件设置": "Settings",
    "软件设置：界面语言（中文 / English）、主题等": "Settings: language (中文 / English), theme, etc.",
    "常规": "General",
    "界面语言:": "Language:",
    "界面主题:": "Theme:",
    "暗色": "Dark",
    "亮色": "Light",
    "切换语言后需要重启软件才能生效。": "Restart the app to apply the language change.",
    "数据与日志": "Data and logs",
    "📁 打开数据文件夹": "📁 Open data folder",
    "🧾 打开崩溃日志文件夹": "🧾 Open crash log folder",
    "保存": "Save",
    "取消": "Cancel",
    "关闭": "Close",
    "版本:": "Version:",
    "版本: {0}": "Version: {0}",
    "视频集成工具": "VideoTools",
    "🎬 视频集成工具": "🎬 VideoTools",
    "切换亮/暗色": "Light / Dark",
}

# ── 翻译表 ────────────────────────────────────────────────────────────
_EXACT = {}
_PATTERNS = []          # (needle, compiled_regex, value_template, ph_kinds)
_PHRASE_RE = None
_PHRASES = {}
_CACHE = {}
_loaded = False


def _norm(s):
    try:
        s.encode("utf-8")
        return s
    except UnicodeEncodeError:
        return s.encode("utf-16", "surrogatepass").decode("utf-16", "replace")


def _load():
    global _loaded, _PHRASE_RE
    if _loaded:
        return
    _loaded = True
    try:
        from UI.i18n_en import EN
    except Exception:
        EN = {}
    table = dict(EN)
    table.update(MANUAL)
    for k, v in table.items():
        if not isinstance(v, str) or not v or v == k:
            continue
        _EXACT[k] = v
        stripped = k.strip()
        if stripped and stripped != k:
            _EXACT.setdefault(stripped, v.strip())
        phs = _PH.findall(k)
        if phs:
            # f-string 模板里的 {{ }} 还原成单括号
            parts = _PH.split(k)
            lits = [p.replace("{{", "{").replace("}}", "}") for p in parts]
            if not any(_HAN.search(p) for p in lits):
                continue
            rx = "^" + "(.*?)".join(re.escape(p) for p in lits) + "$"
            try:
                crx = re.compile(rx, re.S)
            except re.error:
                continue
            needle = max(lits, key=len)
            _PATTERNS.append((needle, crx, v, phs))
        elif "\n" not in k and len(k.strip()) >= 2 and _HAN.search(k):
            _PHRASES[k.strip()] = v.strip()
    if _PHRASES:
        keys = sorted(_PHRASES, key=len, reverse=True)
        _PHRASE_RE = re.compile("|".join(re.escape(x) for x in keys))
    _PATTERNS.sort(key=lambda p: len(p[0]), reverse=True)


def _fill(template, phs, groups, depth):
    """把匹配到的变量值放回英文模板里（变量本身若是中文也会再翻译一次）。"""
    vals = [tr(g, _depth=depth + 1, allow_phrase=False) if _HAN.search(g or "") else g for g in groups]
    out = template
    seq = 0
    # 先替换 {n}
    def rep_index(m):
        i = int(m.group(1))
        return vals[i] if i < len(vals) else m.group(0)
    if any(re.fullmatch(r"\{\d+\}", p) for p in phs):
        out = re.sub(r"\{(\d+)\}", rep_index, out)
        return out.replace("{{", "{").replace("}}", "}")
    # 再按顺序替换 %s / {} / {name}
    def rep_seq(m):
        nonlocal seq
        if seq < len(vals):
            seq += 1
            return vals[seq - 1]
        return m.group(0)
    return _PH.sub(rep_seq, out)


def tr(text, _depth=0, allow_phrase=True):
    """把中文界面文字翻译成当前语言；找不到翻译就原样返回。"""
    if LANG != "en" or not isinstance(text, str) or not text or not _HAN.search(text):
        return text
    if _depth > 3:
        return text
    key = (text, allow_phrase)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    _load()
    s = _norm(text)
    res = _EXACT.get(s)
    if res is None:
        st = s.strip()
        if st != s and st in _EXACT:
            lead = s[:len(s) - len(s.lstrip())]
            trail = s[len(s.rstrip()):]
            res = lead + _EXACT[st] + trail
    if res is None:
        for needle, crx, val, phs in _PATTERNS:
            if needle in s:
                m = crx.match(s)
                if m:
                    res = _fill(val, phs, m.groups(), _depth)
                    break
    if res is None and "\n" in s:
        lines = s.split("\n")
        tl = [tr(x, _depth + 1, allow_phrase) for x in lines]
        if tl != lines:
            res = "\n".join(tl)
    if res is None and "·" in s:
        # 组合名称，例如模板名「常用·上1 / 下1」
        parts = s.split("·")
        tp = [tr(x, _depth + 1, allow_phrase) for x in parts]
        if all(a != b or not _HAN.search(a) for a, b in zip(parts, tp)):
            res = "·".join(tp)
    if res is None and allow_phrase and _PHRASE_RE is not None and not _PATHLIKE.search(s):
        new = _PHRASE_RE.sub(lambda m: _PHRASES[m.group(0)], s)
        if new != s and not _HAN.search(new):
            res = new
    if res is None:
        res = text
    if len(_CACHE) > 20000:
        _CACHE.clear()
    _CACHE[key] = res
    return res


def tr_strict(text):
    """只做整句/模板翻译，不做词语替换（用于文件名、列表项等）。"""
    return tr(text, allow_phrase=False)


# ── 运行时补丁 ────────────────────────────────────────────────────────
_ORIG = {}
_installed = False


def _orig(cls, name):
    return _ORIG[(cls, name)]


def _patch(cls, name, factory):
    if name not in cls.__dict__ and not hasattr(cls, name):
        return
    orig = getattr(cls, name)
    _ORIG[(cls, name)] = orig
    setattr(cls, name, factory(orig))


def _tr_args(args, strict=False):
    f = tr_strict if strict else tr
    return tuple(f(a) if isinstance(a, str) else
                 ([f(x) if isinstance(x, str) else x for x in a] if isinstance(a, list) else a)
                 for a in args)


def _amp(src, dst):
    """按钮等控件里单个 & 会被当成快捷键标记，翻译新增的 & 要转义。"""
    if "&" in dst and "&" not in src:
        return dst.replace("&", "&&")
    return dst


def _widget_setter(orig, strict=False, amp=False):
    """setText 一类：显示英文，记住原文以便 text() 返回中文。"""
    def w(self, *args):
        if args and isinstance(args[-1], str) and _HAN.search(args[-1]):
            src = args[-1]
            dst = tr_strict(src) if strict else tr(src)
            if amp:
                dst = _amp(src, dst)
            if dst != src:
                try:
                    self.setProperty("_i18n_src", src)
                    self.setProperty("_i18n_dst", dst)
                except Exception:
                    pass
                return orig(self, *args[:-1], dst)
        return orig(self, *args)
    return w


def _widget_getter(orig):
    def w(self, *args):
        raw = orig(self, *args)
        try:
            dst = self.property("_i18n_dst")
            if dst is not None and raw == dst:
                return self.property("_i18n_src")
        except Exception:
            pass
        return raw
    return w


def _simple_tr(orig, strict=False, amp=False):
    """只翻译字符串参数（不需要反查原文）。"""
    def w(self, *args, **kw):
        new = _tr_args(args, strict)
        if amp:
            new = tuple(_amp(a, b) if isinstance(a, str) and isinstance(b, str) else b
                        for a, b in zip(args, new))
        return orig(self, *new, **kw)
    return w


def _simple_tr_amp(orig):
    return _simple_tr(orig, amp=True)


# ---- 下拉框：每一项把原文存到 ROLE ----
def _combo_store(combo, idx, src):
    try:
        combo.setItemData(idx, src, ROLE)
    except Exception:
        pass


def _combo_translate_item(combo, idx):
    from PyQt6.QtWidgets import QComboBox
    raw = _orig(QComboBox, "itemText")(combo, idx)
    if not _HAN.search(raw or ""):
        return
    dst = tr_strict(raw)
    if dst != raw:
        _combo_store(combo, idx, raw)
        _orig(QComboBox, "setItemText")(combo, idx, dst)


def _combo_src(combo, idx):
    from PyQt6.QtWidgets import QComboBox
    if idx < 0:
        return None
    v = combo.itemData(idx, ROLE)
    return v if isinstance(v, str) else None


# ---- 列表 / 树 / 表格 项 ----
def _block(view):
    try:
        return view.blockSignals(True) if view is not None else None
    except Exception:
        return None


def _item_view(item):
    for n in ("tableWidget", "listWidget", "treeWidget"):
        f = getattr(item, n, None)
        if f:
            try:
                return f()
            except Exception:
                return None
    return None


def _translate_item(item, columns=None):
    """把一个列表项/表格项/树节点的中文显示成英文（原文存在 ROLE）。"""
    from PyQt6.QtWidgets import QTreeWidgetItem, QListWidgetItem, QTableWidgetItem
    view = _item_view(item)
    old = _block(view)
    try:
        if isinstance(item, QTreeWidgetItem):
            cols = range(item.columnCount()) if columns is None else columns
            for c in cols:
                raw = _orig(QTreeWidgetItem, "text")(item, c)
                if raw and _HAN.search(raw):
                    dst = tr_strict(raw)
                    if dst != raw:
                        item.setData(c, ROLE, raw)
                        _orig(QTreeWidgetItem, "setText")(item, c, dst)
                tip = item.toolTip(c)
                if tip and _HAN.search(tip):
                    _orig(QTreeWidgetItem, "setToolTip")(item, c, tr(tip))
            for i in range(item.childCount()):
                _translate_item(item.child(i))
        else:
            cls = type(item) if type(item) in (QListWidgetItem, QTableWidgetItem) else (
                QListWidgetItem if isinstance(item, QListWidgetItem) else QTableWidgetItem)
            raw = _orig(cls, "text")(item)
            if raw and _HAN.search(raw):
                dst = tr_strict(raw)
                if dst != raw:
                    item.setData(ROLE, raw)
                    _orig(cls, "setText")(item, dst)
            tip = item.toolTip()
            if tip and _HAN.search(tip):
                _orig(cls, "setToolTip")(item, tr(tip))
    except Exception:
        pass
    finally:
        if view is not None and old is not None:
            try:
                view.blockSignals(old)
            except Exception:
                pass


def _item_text_getter(orig, tree=False):
    def w(self, *args):
        raw = orig(self, *args)
        try:
            src = self.data(args[0], ROLE) if tree else self.data(ROLE)
            if isinstance(src, str) and raw == tr_strict(src):
                return src
        except Exception:
            pass
        return raw
    return w


def _item_text_setter(orig, tree=False):
    def w(self, *args):
        args = list(args)
        if args and isinstance(args[-1], str):
            src = args[-1]
            dst = tr_strict(src) if _HAN.search(src) else src
            view = _item_view(self)
            old = _block(view)
            try:
                if tree:
                    self.setData(args[0], ROLE, src if dst != src else None)
                else:
                    self.setData(ROLE, src if dst != src else None)
            except Exception:
                pass
            finally:
                if view is not None and old is not None:
                    view.blockSignals(old)
            args[-1] = dst
        return orig(self, *args)
    return w


# ---- 控件显示时的一次性扫描（翻译构造函数里传入的文字）----
def sweep(w):
    from PyQt6.QtWidgets import (QLabel, QAbstractButton, QGroupBox, QLineEdit, QTextEdit,
                                 QPlainTextEdit, QComboBox, QTabWidget, QListWidget, QTreeWidget,
                                 QTableWidget, QAbstractSpinBox, QSpinBox, QDoubleSpinBox,
                                 QProgressBar, QMenu, QToolBox, QWidget)
    try:
        if w.isWindow():
            t = _orig(QWidget, "windowTitle")(w)
            if t and _HAN.search(t):
                QWidget.setWindowTitle(w, t)
        tip = w.toolTip()
        if tip and _HAN.search(tip):
            QWidget.setToolTip(w, tip)
        if isinstance(w, QLabel):
            raw = _orig(QLabel, "text")(w)
            if raw and _HAN.search(raw) and raw != w.property("_i18n_dst"):
                QLabel.setText(w, raw)
        elif isinstance(w, QAbstractButton):
            raw = _orig(QAbstractButton, "text")(w)
            if raw and _HAN.search(raw) and raw != w.property("_i18n_dst"):
                QAbstractButton.setText(w, raw)
        elif isinstance(w, QGroupBox):
            raw = _orig(QGroupBox, "title")(w)
            if raw and _HAN.search(raw) and raw != w.property("_i18n_dst"):
                QGroupBox.setTitle(w, raw)
        elif isinstance(w, QLineEdit):
            ph = w.placeholderText()
            if ph and _HAN.search(ph):
                _orig(QLineEdit, "setPlaceholderText")(w, tr(ph))
        elif isinstance(w, (QTextEdit, QPlainTextEdit)):
            ph = w.placeholderText()
            if ph and _HAN.search(ph):
                base = QTextEdit if isinstance(w, QTextEdit) else QPlainTextEdit
                _orig(base, "setPlaceholderText")(w, tr(ph))
        elif isinstance(w, QComboBox):
            for i in range(w.count()):
                _combo_translate_item(w, i)
            ph = w.placeholderText()
            if ph and _HAN.search(ph):
                _orig(QComboBox, "setPlaceholderText")(w, tr(ph))
        elif isinstance(w, QTabWidget):
            for i in range(w.count()):
                t = _orig(QTabWidget, "tabText")(w, i)
                if t and _HAN.search(t):
                    _orig(QTabWidget, "setTabText")(w, i, _amp(t, tr(t)))
                tt = w.tabToolTip(i)
                if tt and _HAN.search(tt):
                    _orig(QTabWidget, "setTabToolTip")(w, i, tr(tt))
        elif isinstance(w, QToolBox):
            for i in range(w.count()):
                t = w.itemText(i)
                if t and _HAN.search(t):
                    _orig(QToolBox, "setItemText")(w, i, tr(t))
        elif isinstance(w, QListWidget):
            for i in range(w.count()):
                _translate_item(w.item(i))
        elif isinstance(w, QTreeWidget):
            hi = w.headerItem()
            if hi is not None:
                _translate_item(hi)
            for i in range(w.topLevelItemCount()):
                _translate_item(w.topLevelItem(i))
        elif isinstance(w, QTableWidget):
            for c in range(w.columnCount()):
                hi = w.horizontalHeaderItem(c)
                if hi is not None:
                    _translate_item(hi)
            for r in range(w.rowCount()):
                vi = w.verticalHeaderItem(r)
                if vi is not None:
                    _translate_item(vi)
                for c in range(w.columnCount()):
                    it = w.item(r, c)
                    if it is not None:
                        _translate_item(it)
        elif isinstance(w, QAbstractSpinBox):
            if isinstance(w, (QSpinBox, QDoubleSpinBox)):
                base = QSpinBox if isinstance(w, QSpinBox) else QDoubleSpinBox
                for g, s in (("suffix", "setSuffix"), ("prefix", "setPrefix")):
                    v = getattr(w, g)()
                    if v and _HAN.search(v):
                        _orig(base, s)(w, tr(v))
            sv = w.specialValueText()
            if sv and _HAN.search(sv):
                _orig(QAbstractSpinBox, "setSpecialValueText")(w, tr(sv))
        elif isinstance(w, QProgressBar):
            f = w.format()
            if f and _HAN.search(f):
                _orig(QProgressBar, "setFormat")(w, tr(f))
        elif isinstance(w, QMenu):
            t = w.title()
            if t and _HAN.search(t):
                _orig(QMenu, "setTitle")(w, _amp(t, tr(t)))
            for a in w.actions():
                _translate_action(a)
    except Exception:
        pass


def _translate_action(a):
    from PyQt6.QtGui import QAction
    try:
        raw = _orig(QAction, "text")(a)
        if raw and _HAN.search(raw) and raw != a.property("_i18n_dst"):
            QAction.setText(a, raw)
        tip = a.toolTip()
        if tip and _HAN.search(tip) and tip != raw:
            _orig(QAction, "setToolTip")(a, tr(tip))
    except Exception:
        pass


class _ShowFilter(QObject):
    def eventFilter(self, obj, ev):
        try:
            if ev.type() == QEvent.Type.Show and obj.isWidgetType():
                sweep(obj)
        except Exception:
            pass
        return False


_filter = None


def install(app=None):
    """在创建任何界面之前调用。中文模式下什么都不做。"""
    global _installed, _filter
    if LANG != "en" or _installed:
        return
    _installed = True
    _load()
    from PyQt6.QtWidgets import (QLabel, QAbstractButton, QGroupBox, QWidget, QLineEdit,
                                 QTextEdit, QPlainTextEdit, QComboBox, QTabWidget, QToolBox,
                                 QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
                                 QTableWidget, QTableWidgetItem, QSpinBox, QDoubleSpinBox,
                                 QAbstractSpinBox, QProgressBar, QMenu, QMessageBox,
                                 QFileDialog, QInputDialog, QStatusBar, QDialogButtonBox,
                                 QSplashScreen, QToolButton)
    from PyQt6.QtGui import QAction, QPainter

    # 普通控件文字
    for cls, setter, getter, amp in ((QLabel, "setText", "text", False),
                                     (QAbstractButton, "setText", "text", True),
                                     (QGroupBox, "setTitle", "title", True),
                                     (QAction, "setText", "text", True)):
        _patch(cls, setter, (lambda a: (lambda o: _widget_setter(o, amp=a)))(amp))
        _patch(cls, getter, _widget_getter)
    _patch(QWidget, "setWindowTitle", _widget_setter)
    _patch(QWidget, "windowTitle", _widget_getter)
    for cls, name in ((QWidget, "setToolTip"), (QAction, "setToolTip"), (QAction, "setStatusTip"),
                      (QLineEdit, "setPlaceholderText"), (QTextEdit, "setPlaceholderText"),
                      (QPlainTextEdit, "setPlaceholderText"), (QComboBox, "setPlaceholderText"),
                      (QProgressBar, "setFormat"),
                      (QTabWidget, "setTabToolTip"), (QToolBox, "addItem"), (QToolBox, "insertItem"),
                      (QToolBox, "setItemText"), (QSpinBox, "setSuffix"), (QSpinBox, "setPrefix"),
                      (QDoubleSpinBox, "setSuffix"), (QDoubleSpinBox, "setPrefix"),
                      (QAbstractSpinBox, "setSpecialValueText"),
                      (QTextEdit, "append"), (QPlainTextEdit, "appendPlainText"),
                      (QStatusBar, "showMessage"), (QSplashScreen, "showMessage"),
                      (QDialogButtonBox, "addButton"), (QMessageBox, "setText"),
                      (QMessageBox, "setInformativeText"), (QMessageBox, "setDetailedText"),
                      (QMessageBox, "addButton"),
                      (QTableWidget, "setHorizontalHeaderLabels"), (QTableWidget, "setVerticalHeaderLabels"),
                      (QTreeWidget, "setHeaderLabels"), (QTreeWidget, "setHeaderLabel")):
        _patch(cls, name, _simple_tr)
    for cls, name in ((QMenu, "setTitle"), (QMenu, "addMenu"), (QMenu, "addAction"),
                      (QMenu, "addSection"), (QTabWidget, "addTab"), (QTabWidget, "insertTab"),
                      (QTabWidget, "setTabText")):
        _patch(cls, name, _simple_tr_amp)
    # 保留原始 getter 供扫描使用
    for cls, name in ((QTabWidget, "tabText"),):
        _ORIG[(cls, name)] = getattr(cls, name)

    # QPainter.drawText（自绘控件上的文字）
    _patch(QPainter, "drawText", _simple_tr)

    # 下拉框
    def _combo_add(orig):
        def w(self, *args, **kw):
            n0 = self.count()
            r = orig(self, *args, **kw)
            for i in range(self.count()):
                if i >= n0 or True:
                    pass
            # 新加入的项（可能插在中间）：逐项检查未翻译的中文
            for i in range(self.count()):
                if _combo_src(self, i) is None:
                    _combo_translate_item(self, i)
            return r
        return w
    for name in ("addItem", "addItems", "insertItem", "insertItems"):
        _patch(QComboBox, name, _combo_add)
    _ORIG[(QComboBox, "itemText")] = QComboBox.itemText
    _ORIG[(QComboBox, "currentText")] = QComboBox.currentText
    _ORIG[(QComboBox, "findText")] = QComboBox.findText
    _ORIG[(QComboBox, "setCurrentText")] = QComboBox.setCurrentText
    _ORIG[(QComboBox, "setItemText")] = QComboBox.setItemText

    def _set_item_text(self, idx, text):
        if isinstance(text, str) and _HAN.search(text):
            dst = tr_strict(text)
            if dst != text:
                _combo_store(self, idx, text)
                return _ORIG[(QComboBox, "setItemText")](self, idx, dst)
        _combo_store(self, idx, None)
        return _ORIG[(QComboBox, "setItemText")](self, idx, text)

    def _item_text(self, idx):
        src = _combo_src(self, idx)
        return src if src is not None else _ORIG[(QComboBox, "itemText")](self, idx)

    def _current_text(self):
        raw = _ORIG[(QComboBox, "currentText")](self)
        idx = self.currentIndex()
        src = _combo_src(self, idx)
        if src is not None and raw == _ORIG[(QComboBox, "itemText")](self, idx):
            return src
        return raw

    def _find_text(self, text, *args):
        for i in range(self.count()):
            if _combo_src(self, i) == text:
                return i
        return _ORIG[(QComboBox, "findText")](self, text, *args)

    def _set_current_text(self, text):
        i = _find_text(self, text)
        if i >= 0 and not self.isEditable():
            self.setCurrentIndex(i)
            return
        return _ORIG[(QComboBox, "setCurrentText")](self, text)

    QComboBox.setItemText = _set_item_text
    QComboBox.itemText = _item_text
    QComboBox.currentText = _current_text
    QComboBox.findText = _find_text
    QComboBox.setCurrentText = _set_current_text

    # 列表 / 树 / 表格项
    for cls in (QListWidgetItem, QTableWidgetItem):
        _patch(cls, "setText", lambda o: _item_text_setter(o, False))
        _patch(cls, "text", lambda o: _item_text_getter(o, False))
        _patch(cls, "setToolTip", _simple_tr)
    _patch(QTreeWidgetItem, "setText", lambda o: _item_text_setter(o, True))
    _patch(QTreeWidgetItem, "text", lambda o: _item_text_getter(o, True))
    _patch(QTreeWidgetItem, "setToolTip", _simple_tr)

    def _insert_hook(orig):
        def w(self, *args, **kw):
            for a in args:
                if isinstance(a, (QListWidgetItem, QTableWidgetItem, QTreeWidgetItem)):
                    _translate_item(a)
                elif isinstance(a, list):
                    for x in a:
                        if isinstance(x, (QListWidgetItem, QTableWidgetItem, QTreeWidgetItem)):
                            _translate_item(x)
            return orig(self, *_tr_args(args, strict=True), **kw)
        return w
    for cls, name in ((QTableWidget, "setItem"), (QTableWidget, "setHorizontalHeaderItem"),
                      (QListWidget, "addItem"), (QListWidget, "insertItem"),
                      (QListWidget, "addItems"), (QListWidget, "insertItems"),
                      (QTreeWidget, "addTopLevelItem"), (QTreeWidget, "addTopLevelItems"),
                      (QTreeWidget, "insertTopLevelItem"), (QTreeWidget, "insertTopLevelItems"),
                      (QTreeWidgetItem, "addChild"), (QTreeWidgetItem, "addChildren"),
                      (QTreeWidgetItem, "insertChild"), (QTreeWidgetItem, "insertChildren")):
        _patch(cls, name, _insert_hook)

    # 文件对话框：只翻译标题和过滤器，路径保持不变
    def _fd(orig_static, cap_idx=1, filt_idx=3):
        def w(*args, **kw):
            args = list(args)
            if len(args) > cap_idx and isinstance(args[cap_idx], str):
                args[cap_idx] = tr(args[cap_idx])
            fmap = {}
            if len(args) > filt_idx and isinstance(args[filt_idx], str):
                parts = args[filt_idx].split(";;")
                tp = [tr(p) for p in parts]
                fmap = dict(zip(tp, parts))
                args[filt_idx] = ";;".join(tp)
            for k in ("caption", "filter"):
                if isinstance(kw.get(k), str):
                    kw[k] = tr(kw[k])
            r = orig_static(*args, **kw)
            if isinstance(r, tuple) and len(r) == 2 and isinstance(r[1], str):
                return (r[0], fmap.get(r[1], r[1]))
            return r
        return staticmethod(w)
    for name in ("getOpenFileName", "getOpenFileNames", "getSaveFileName"):
        o = getattr(QFileDialog, name)
        _ORIG[(QFileDialog, name)] = o
        setattr(QFileDialog, name, _fd(o))
    o = QFileDialog.getExistingDirectory
    _ORIG[(QFileDialog, "getExistingDirectory")] = o
    setattr(QFileDialog, "getExistingDirectory", _fd(o, 1, 99))

    # 输入对话框：getItem 的返回值映射回原文
    o_item = QInputDialog.getItem

    def _get_item(parent, title, label, items, *args, **kw):
        items = list(items)
        en = [tr_strict(x) for x in items]
        back = dict(zip(en, items))
        r = o_item(parent, tr(title), tr(label), en, *args, **kw)
        return (back.get(r[0], r[0]), r[1])
    QInputDialog.getItem = staticmethod(_get_item)
    for name in ("getText", "getInt", "getDouble", "getMultiLineText"):
        o = getattr(QInputDialog, name)

        def mk(o):
            def w(parent, title, label, *args, **kw):
                return o(parent, tr(title), tr(label), *args, **kw)
            return staticmethod(w)
        setattr(QInputDialog, name, mk(o))

    # 显示时扫描
    if app is not None:
        _filter = _ShowFilter(app)
        app.installEventFilter(_filter)
