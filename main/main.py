import sys
import os
import ctypes

# ================= 新增：跨文件夹路径引导 =================
# 让程序知道项目的根目录在哪里，从而能找到 UI、Video 等文件夹
if getattr(sys, 'frozen', False):
    root_dir = os.path.dirname(sys.executable)
else:
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(root_dir, relative_path)
# ========================================================

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, 
                             QStackedWidget, QVBoxLayout, QPushButton, QFrame, QLabel)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QIcon

# 修改：加上 "UI." 前缀来导入界面文件
from UI.ui import VideoMergerUI
from UI.ui_image_merger import ImageMergerUI
from UI.ui_image_cropper import ImageCropperUI
from UI.ui_multi_segment import MultiSegmentUI
from UI.ui_youtube_downloader import YouTubeDownloaderUI
from UI.ui_auto_screenshot import AutoScreenshotUI
from UI.ui_gdrive_downloader import GDriveDownloaderUI

class ToolboxApp(QMainWindow):

    def __init__(self):
        super().__init__()
        try:
            myappid = 'mycompany.videotools.1.0.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        self.setWindowTitle("视频集成工具 1.2.0")
        self.setMinimumSize(1000, 750)
        self.setWindowIcon(QIcon(resource_path(os.path.join("log", "log.ico")))) 
        
        # 1. 初始化设置管理器，读取深色模式偏好
        self.settings = QSettings("MyCompany", "VideoToolbox")
        self.is_dark_mode = self.settings.value("is_dark_mode", True, type=bool)

        self.setup_ui()
        self.apply_theme()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.nav_bar = QFrame()
        self.nav_bar.setObjectName("NavBar")
        self.nav_bar.setFixedHeight(60)
        nav_layout = QHBoxLayout(self.nav_bar)
        nav_layout.setContentsMargins(20, 0, 20, 0)
        nav_layout.setSpacing(15)

        logo_label = QLabel("🎬 视频集成工具")
        logo_label.setObjectName("LogoText")
        nav_layout.addWidget(logo_label)
        nav_layout.addSpacing(20)

        self.btn_nav_video = QPushButton("🚀 视频合并与转场")
        self.btn_nav_img_merge = QPushButton("✨ 图片合并成视频") 
        self.btn_nav_image = QPushButton("🖼️ 图片批量裁剪")
        self.btn_nav_multi = QPushButton("🎞️ 多片段合成")
        self.btn_nav_youtube = QPushButton("📥 YouTube下载")
        self.btn_nav_screenshot = QPushButton("📸 链接截图")
        self.btn_nav_gdrive = QPushButton("☁️ 云盘下载")
        
        for btn in [self.btn_nav_video, self.btn_nav_img_merge, self.btn_nav_image, self.btn_nav_multi, self.btn_nav_youtube, self.btn_nav_screenshot, self.btn_nav_gdrive]:
            btn.setCheckable(True)
            btn.setProperty("class", "NavBtn")
            nav_layout.addWidget(btn)

        self.btn_nav_video.setChecked(True) 
        nav_layout.addStretch() 

        self.btn_theme = QPushButton("切换亮/暗色")
        self.btn_theme.setProperty("class", "ActionBtn")
        self.btn_theme.clicked.connect(self.toggle_theme)
        nav_layout.addWidget(self.btn_theme)

        self.main_layout.addWidget(self.nav_bar)

        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setContentsMargins(20, 20, 20, 20)
        
        self.video_tool = VideoMergerUI()
        self.img_merge_tool = ImageMergerUI()
        self.image_tool = ImageCropperUI()
        self.multi_segment_tool = MultiSegmentUI()
        self.youtube_tool = YouTubeDownloaderUI()
        self.screenshot_tool = AutoScreenshotUI()
        self.gdrive_tool = GDriveDownloaderUI()
        
        self.stacked_widget.addWidget(self.video_tool)
        self.stacked_widget.addWidget(self.img_merge_tool)
        self.stacked_widget.addWidget(self.image_tool)
        self.stacked_widget.addWidget(self.multi_segment_tool)
        self.stacked_widget.addWidget(self.youtube_tool)
        self.stacked_widget.addWidget(self.screenshot_tool)
        self.stacked_widget.addWidget(self.gdrive_tool)

        self.main_layout.addWidget(self.stacked_widget)

        self.btn_nav_video.clicked.connect(lambda: self.switch_tab(0, self.btn_nav_video))
        self.btn_nav_img_merge.clicked.connect(lambda: self.switch_tab(1, self.btn_nav_img_merge))
        self.btn_nav_image.clicked.connect(lambda: self.switch_tab(2, self.btn_nav_image))
        self.btn_nav_multi.clicked.connect(lambda: self.switch_tab(3, self.btn_nav_multi))
        self.btn_nav_youtube.clicked.connect(lambda: self.switch_tab(4, self.btn_nav_youtube))
        self.btn_nav_screenshot.clicked.connect(lambda: self.switch_tab(5, self.btn_nav_screenshot))
        self.btn_nav_gdrive.clicked.connect(lambda: self.switch_tab(6, self.btn_nav_gdrive))
        self.nav_buttons = [self.btn_nav_video, self.btn_nav_img_merge, self.btn_nav_image, self.btn_nav_multi, self.btn_nav_youtube, self.btn_nav_screenshot, self.btn_nav_gdrive]

    def switch_tab(self, index, active_btn):
        self.stacked_widget.setCurrentIndex(index)
        for btn in self.nav_buttons:
            btn.setChecked(False)
        active_btn.setChecked(True)

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()

    def apply_theme(self):
        if self.is_dark_mode:
            qss = """
                QMainWindow { background-color: #1a1d27; }
                QWidget { font-family: "Microsoft YaHei", "Segoe UI"; font-size: 10pt; color: #d1d5db; }
                QFrame#NavBar { background-color: #1e222d; border-bottom: 1px solid #2b303b; }
                QLabel#LogoText { font-size: 14pt; font-weight: bold; color: #ffffff; }
                QPushButton.NavBtn { background: transparent; border: none; color: #9ca3af; padding: 10px 15px; font-weight: bold; font-size: 11pt; border-radius: 6px; }
                QPushButton.NavBtn:hover { background-color: #2b303b; color: #ffffff; }
                QPushButton.NavBtn:checked { background-color: #f43f5e; color: #ffffff; } 
                QFrame.Card { background-color: #222631; border-radius: 10px; border: 1px solid #2b303b; }
                QLabel.CardTitle { font-size: 11pt; font-weight: bold; color: #ffffff; }
                QPushButton { background-color: #374151; color: white; border: none; border-radius: 6px; padding: 8px 15px; }
                QPushButton:hover { background-color: #4b5563; }
                QPushButton:disabled { background-color: #1f2937; color: #6b7280; }
                QPushButton#PrimaryBtn { background-color: #f43f5e; font-size: 12pt; font-weight: bold; padding: 12px; }
                QPushButton#PrimaryBtn:hover { background-color: #e11d48; }
                QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit { background-color: #1a1d27; border: 1px solid #374151; border-radius: 4px; padding: 5px; color: #ffffff; }
                QComboBox::drop-down { border: none; }
                QListWidget { background-color: #1a1d27; border: 2px dashed #374151; border-radius: 8px; padding: 10px; outline: none; }
                QListWidget::item { padding: 5px; border-bottom: 1px solid #2b303b; }
                QListWidget::item:selected { background-color: #374151; border-radius: 4px; }
                QProgressBar { border: 1px solid #374151; border-radius: 6px; text-align: center; background-color: #1a1d27; }
                QProgressBar::chunk { background-color: #f43f5e; border-radius: 5px; }
                QSlider::groove:horizontal { border-radius: 4px; height: 6px; background: #374151; }
                QSlider::handle:horizontal { background: #f43f5e; width: 14px; margin: -4px 0; border-radius: 7px; }
                QScrollArea { background: transparent; border: none; }
                QScrollBar:vertical { background: #ffffff; width: 8px; margin: 0; border-radius: 4px; }
                QScrollBar::handle:vertical { background: #4b5563; min-height: 28px; border-radius: 4px; }
                QScrollBar::handle:vertical:hover { background: #9ca3af; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
            """
        else:
            qss = """
                QMainWindow { background-color: #f3f4f6; }
                QWidget { font-family: "Microsoft YaHei", "Segoe UI"; font-size: 10pt; color: #374151; }
                QFrame#NavBar { background-color: #ffffff; border-bottom: 1px solid #e5e7eb; }
                QLabel#LogoText { font-size: 14pt; font-weight: bold; color: #111827; }
                QPushButton.NavBtn { background: transparent; border: none; color: #6b7280; padding: 10px 15px; font-weight: bold; font-size: 11pt; border-radius: 6px; }
                QPushButton.NavBtn:hover { background-color: #f3f4f6; color: #111827; }
                QPushButton.NavBtn:checked { background-color: #3b82f6; color: #ffffff; } 
                QFrame.Card { background-color: #ffffff; border-radius: 10px; border: 1px solid #e5e7eb; }
                QLabel.CardTitle { font-size: 11pt; font-weight: bold; color: #111827; }
                QPushButton { background-color: #f3f4f6; color: #374151; border: 1px solid #d1d5db; border-radius: 6px; padding: 8px 15px; }
                QPushButton:hover { background-color: #e5e7eb; }
                QPushButton:disabled { background-color: #f3f4f6; color: #9ca3af; }
                QPushButton#PrimaryBtn { background-color: #3b82f6; color: white; border: none; font-size: 12pt; font-weight: bold; padding: 12px; }
                QPushButton#PrimaryBtn:hover { background-color: #2563eb; }
                QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit { background-color: #f9fafb; border: 1px solid #d1d5db; border-radius: 4px; padding: 5px; color: #111827; }
                QListWidget { background-color: #f9fafb; border: 2px dashed #d1d5db; border-radius: 8px; padding: 10px; outline: none; }
                QListWidget::item { padding: 5px; border-bottom: 1px solid #e5e7eb; }
                QListWidget::item:selected { background-color: #e5e7eb; border-radius: 4px; }
                QProgressBar { border: 1px solid #d1d5db; border-radius: 6px; text-align: center; background-color: #f9fafb; }
                QProgressBar::chunk { background-color: #3b82f6; border-radius: 5px; }
                QSlider::groove:horizontal { border-radius: 4px; height: 6px; background: #d1d5db; }
                QSlider::handle:horizontal { background: #3b82f6; width: 14px; margin: -4px 0; border-radius: 7px; }
                QScrollArea { background: transparent; border: none; }
                QScrollBar:vertical { background: #ffffff; width: 8px; margin: 0; border-radius: 4px; }
                QScrollBar::handle:vertical { background: #9ca3af; min-height: 28px; border-radius: 4px; }
                QScrollBar::handle:vertical:hover { background: #6b7280; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
            """
        self.setStyleSheet(qss)

    # 2. 软件关闭时，通知所有子页面保存设置
    def closeEvent(self, event):
        self.settings.setValue("is_dark_mode", self.is_dark_mode)
        self.video_tool.save_settings()
        self.img_merge_tool.save_settings()
        self.image_tool.save_settings()
        self.multi_segment_tool.save_settings()
        self.youtube_tool.save_settings()
        self.screenshot_tool.save_settings()
        self.gdrive_tool.save_settings()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ToolboxApp()
    window.show()
    sys.exit(app.exec())