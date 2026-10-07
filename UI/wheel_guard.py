"""
wheel_guard.py — 防误触滚轮

数字框 / 下拉框 / 滑块：只有鼠标点击选中（获得焦点）后，滚轮才会修改数值；
未选中时滚动滚轮，会把滚动交给外层的滚动区域（正常上下翻页）。
"""
from PyQt6.QtCore import QObject, QEvent, Qt
from PyQt6.QtWidgets import (QApplication, QAbstractSpinBox, QComboBox, QAbstractSlider,
                             QScrollBar, QAbstractScrollArea)

_GUARDED = (QAbstractSpinBox, QComboBox, QAbstractSlider)


def _is_guarded(obj):
    return isinstance(obj, _GUARDED) and not isinstance(obj, QScrollBar)


class WheelGuard(QObject):
    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Type.Polish and _is_guarded(obj):
            obj.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        elif t == QEvent.Type.Wheel and _is_guarded(obj):
            fw = QApplication.focusWidget()
            focused = obj.hasFocus() or (fw is not None and obj.isAncestorOf(fw))
            if not focused:
                self._scroll_parent(obj, ev)
                return True
        return False

    @staticmethod
    def _scroll_parent(obj, ev):
        p = obj.parentWidget()
        while p is not None:
            if isinstance(p, QAbstractScrollArea):
                sb = p.verticalScrollBar()
                if sb is not None and sb.maximum() > sb.minimum():
                    steps = ev.angleDelta().y() / 120.0
                    sb.setValue(int(sb.value() - steps * sb.singleStep() * 3))
                    return
            p = p.parentWidget()


_guard = None


def install_wheel_guard():
    global _guard
    app = QApplication.instance()
    if app is None or _guard is not None:
        return
    _guard = WheelGuard(app)
    app.installEventFilter(_guard)
    for w in app.allWidgets():
        if _is_guarded(w):
            w.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
