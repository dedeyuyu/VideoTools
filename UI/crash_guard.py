"""
crash_guard.py — 全局异常保护
- 捕获未处理的异常，写入 crash_logs/ 目录，不让整个软件直接退出
- 出错时立即尝试保存所有设置，防止辛苦调整的参数丢失
"""
import os
import sys
import time
import threading
import traceback

_window = None
_showing = False


def _log_dir():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(base, "crash_logs")
    os.makedirs(d, exist_ok=True)
    return d


def _emergency_save():
    w = _window
    if w is None:
        return
    for name in ("duet_tool",):
        tool = getattr(w, name, None)
        if tool is not None:
            try:
                tool.save_settings()
            except Exception:
                pass


def _handle(exc_type, exc, tb):
    global _showing
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    print(text, file=sys.stderr, flush=True)
    path = os.path.join(_log_dir(), time.strftime("crash_%Y%m%d_%H%M%S.txt"))
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass
    _emergency_save()
    # 只在主线程弹窗，并防止连环弹窗
    if threading.current_thread() is threading.main_thread() and not _showing:
        try:
            from PyQt6.QtWidgets import QMessageBox
            _showing = True
            QMessageBox.warning(
                _window, "程序出现错误（已自动保护）",
                f"发生了一个错误，但软件没有退出，您的设置已自动保存。\n\n"
                f"{exc_type.__name__}: {exc}\n\n错误日志：{path}")
        except Exception:
            pass
        finally:
            _showing = False


def install(window):
    global _window
    _window = window
    sys.excepthook = _handle
    threading.excepthook = lambda a: _handle(a.exc_type, a.exc_value, a.exc_traceback)
