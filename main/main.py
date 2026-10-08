import sys
import os
import ctypes

# ================= 新增：跨文件夹路径引导 =================
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
                             QStackedWidget, QVBoxLayout, QPushButton, QFrame,
                             QLabel, QScrollArea, QTreeWidget, QTreeWidgetItem)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QIcon

from UI.ui import VideoMergerUI
from UI.ui_image_merger import ImageMergerUI
from UI.ui_image_cropper import ImageCropperUI
from UI.ui_multi_segment import MultiSegmentUI
from UI.ui_youtube_downloader import YouTubeDownloaderUI
from UI.ui_auto_screenshot import AutoScreenshotUI
from UI.ui_gdrive_downloader import GDriveDownloaderUI
from UI.ui_copyright_processor import CopyrightProcessorUI
from UI.ui_duet_video import DuetVideoUI
from UI.ui_landscape_to_portrait import LandscapeToPortraitUI
from UI.ui_ffmpeg_downloader_mgr import (FFmpegDownloaderDialog, get_ffmpeg_status,
                                          get_opencv_status, get_ytdlp_status,
                                          get_mediapipe_status, get_face_detection_status)

class ToolboxApp(QMainWindow):

    def __init__(self):
        super().__init__()
        try:
            myappid = 'mycompany.videotools.1.4.1'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        self.setWindowTitle("视频集成工具 v1.5.5")
        self.setMinimumSize(1100, 750)
        self.setWindowIcon(QIcon(resource_path(os.path.join("log", "log.ico")))) 
        
        self.settings = QSettings("MyCompany", "VideoToolbox")
        self.is_dark_mode = self.settings.value("is_dark_mode", True, type=bool)

        self.setup_ui()
        self.apply_theme()
        from UI.wheel_guard import install_wheel_guard
        install_wheel_guard()
        self._update_components_btn_style()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QHBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # ── 左侧侧边栏 ────────────────────────────────────────────────
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(10, 20, 10, 20)
        sidebar_layout.setSpacing(10)

        logo_label = QLabel("🎬 视频集成工具")
        logo_label.setObjectName("LogoText")
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(logo_label)
        sidebar_layout.addSpacing(20)

        self.nav_tree = QTreeWidget()
        self.nav_tree.setObjectName("NavTree")
        self.nav_tree.setHeaderHidden(True)
        self.nav_tree.setIndentation(15)
        self.nav_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # 视频批量工具
        cat_video = QTreeWidgetItem(["📂 视频批量工具"])
        cat_video.setFlags(cat_video.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        
        self.item_duet = QTreeWidgetItem(["✨ 合拍视频批量合成"])
        self.item_video = QTreeWidgetItem(["🚀 视频合并与转场"])
        self.item_img_merge = QTreeWidgetItem(["✨ 图片合并成视频"])
        self.item_copyright = QTreeWidgetItem(["🎨 处理版权图片"])
        self.item_l2p = QTreeWidgetItem(["🔃 横屏转竖屏"])
        self.item_image = QTreeWidgetItem(["🖼️ 图片批量裁剪"])
        self.item_multi = QTreeWidgetItem(["🎞️ 多片段合成"])
        self.item_screenshot = QTreeWidgetItem(["📸 链接截图"])
        
        cat_video.addChildren([self.item_duet, self.item_video, self.item_img_merge, self.item_copyright, 
                               self.item_l2p, self.item_image, self.item_multi, self.item_screenshot])
        self.nav_tree.addTopLevelItem(cat_video)

        # 通用下载
        cat_download = QTreeWidgetItem(["📂 通用下载"])
        cat_download.setFlags(cat_download.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        
        self.item_youtube = QTreeWidgetItem(["📥 YouTube下载"])
        self.item_gdrive = QTreeWidgetItem(["☁️ 云盘下载"])
        
        cat_download.addChildren([self.item_youtube, self.item_gdrive])
        self.nav_tree.addTopLevelItem(cat_download)

        self.nav_tree.expandAll()
        sidebar_layout.addWidget(self.nav_tree)
        sidebar_layout.addStretch()

        self.btn_components = QPushButton("📦 下载必要组件")
        self.btn_components.setProperty("class", "ActionBtn")
        self.btn_components.setToolTip("管理必要组件 — FFmpeg / opencv-python\n检测状态 / 一键下载安装")
        self.btn_components.clicked.connect(self._open_components_manager)
        sidebar_layout.addWidget(self.btn_components)

        self.btn_theme = QPushButton("切换亮/暗色")
        self.btn_theme.setProperty("class", "ActionBtn")
        self.btn_theme.clicked.connect(self.toggle_theme)
        sidebar_layout.addWidget(self.btn_theme)

        self.main_layout.addWidget(self.sidebar)

        # ── 右侧主内容区 ─────────────────────────────────────────────────────
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setContentsMargins(20, 20, 20, 20)

        self.duet_tool       = DuetVideoUI()
        self.video_tool      = VideoMergerUI()
        self.img_merge_tool  = ImageMergerUI()
        self.copyright_tool  = CopyrightProcessorUI()
        self.l2p_tool        = LandscapeToPortraitUI()
        self.image_tool      = ImageCropperUI()
        self.multi_segment_tool = MultiSegmentUI()
        self.screenshot_tool = AutoScreenshotUI()
        self.youtube_tool    = YouTubeDownloaderUI()
        self.gdrive_tool     = GDriveDownloaderUI()

        self.stacked_widget.addWidget(self.duet_tool)           # 0
        self.stacked_widget.addWidget(self.video_tool)          # 1
        self.stacked_widget.addWidget(self.img_merge_tool)      # 2
        self.stacked_widget.addWidget(self.copyright_tool)      # 3
        self.stacked_widget.addWidget(self.l2p_tool)            # 4
        self.stacked_widget.addWidget(self.image_tool)          # 5
        self.stacked_widget.addWidget(self.multi_segment_tool)  # 6
        self.stacked_widget.addWidget(self.screenshot_tool)     # 7
        self.stacked_widget.addWidget(self.youtube_tool)        # 8
        self.stacked_widget.addWidget(self.gdrive_tool)         # 9

        self.content_layout.addWidget(self.stacked_widget)
        self.main_layout.addWidget(self.content_widget)

        self.item_to_index = {
            id(self.item_duet): 0,
            id(self.item_video): 1,
            id(self.item_img_merge): 2,
            id(self.item_copyright): 3,
            id(self.item_l2p): 4,
            id(self.item_image): 5,
            id(self.item_multi): 6,
            id(self.item_screenshot): 7,
            id(self.item_youtube): 8,
            id(self.item_gdrive): 9,
        }

        self.nav_tree.itemClicked.connect(self.on_tree_item_clicked)
        self.nav_tree.setCurrentItem(self.item_duet)
        self.stacked_widget.setCurrentIndex(0)

    def on_tree_item_clicked(self, item, column):
        idx = self.item_to_index.get(id(item))
        if idx is not None:
            self.stacked_widget.setCurrentIndex(idx)

    def _open_components_manager(self):
        """打开「下载必要组件」对话框。"""
        dlg = FFmpegDownloaderDialog(parent=self)
        dlg.exec()
        self._update_components_btn_style()

    def _update_components_btn_style(self):
        """根据 FFmpeg、人脸检测引擎（mediapipe/opencv）、yt-dlp 安装状态更新按钮样式。"""
        ffmpeg_ok    = get_ffmpeg_status()["installed"]
        face_det_ok  = get_face_detection_status()["installed"]   # mediapipe 或 可用的 opencv
        ytdlp_ok     = get_ytdlp_status()["installed"]

        if ffmpeg_ok and face_det_ok and ytdlp_ok:
            self.btn_components.setText("📦 下载必要组件 ✅")
            self.btn_components.setStyleSheet("")
        else:
            missing = []
            if not ffmpeg_ok:
                missing.append("FFmpeg")
            if not face_det_ok:
                missing.append("人脸检测引擎 (mediapipe)")
            if not ytdlp_ok:
                missing.append("yt-dlp")
            self.btn_components.setText("📦 下载必要组件 ❌")
            self.btn_components.setStyleSheet(
                "QPushButton { color: #f43f5e; font-weight: bold; }"
            )
            self.btn_components.setToolTip(
                f"缺少必要组件：{', '.join(missing)}\n点击下载安装"
            )

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()

    def apply_theme(self):
        if self.is_dark_mode:
            qss = """
                QMainWindow { background-color: #121212; }
                QWidget { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 10pt; color: #E0E0E0; }
                
                QFrame#Sidebar { 
                    background-color: #1A1A1A; 
                    border-right: 1px solid #282828; 
                }
                QLabel#LogoText { 
                    font-size: 15pt; 
                    font-weight: 600; 
                    color: #FFFFFF; 
                    padding: 10px 0;
                    letter-spacing: 1px;
                }
                
                QTreeWidget#NavTree { 
                    background: transparent; 
                    border: none; 
                    outline: none; 
                }
                QTreeWidget#NavTree::item { 
                    padding: 12px 10px; 
                    border-radius: 8px; 
                    margin: 4px 6px;
                }
                QTreeWidget#NavTree::item:hover { 
                    background-color: #252525; 
                }
                QTreeWidget#NavTree::item:selected { 
                    background-color: #2D3748; 
                    color: #63B3ED; 
                    font-weight: bold; 
                }
                
                QFrame.Card { 
                    background-color: #1A1A1A; 
                    border-radius: 12px; 
                    border: 1px solid #282828; 
                }
                QLabel.CardTitle { 
                    font-size: 12pt; 
                    font-weight: bold; 
                    color: #FFFFFF; 
                }
                
                QPushButton { 
                    background-color: #252525; 
                    color: #E0E0E0; 
                    border: 1px solid #333333; 
                    border-radius: 6px; 
                    padding: 8px 16px; 
                }
                QPushButton:hover { 
                    background-color: #303030; 
                    border: 1px solid #444444; 
                }
                QPushButton:disabled { 
                    background-color: #161616; 
                    color: #555555; 
                    border: 1px solid #222222;
                }
                
                QPushButton.ActionBtn { 
                    background-color: #3182CE; 
                    color: white; 
                    border: none; 
                    font-weight: bold; 
                    padding: 10px 18px; 
                    border-radius: 8px;
                }
                QPushButton.ActionBtn:hover { 
                    background-color: #2B6CB0; 
                }
                
                QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit { 
                    background-color: #121212; 
                    border: 1px solid #333333; 
                    border-radius: 6px; 
                    padding: 6px 10px; 
                    color: #E0E0E0; 
                }
                QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QLineEdit:focus {
                    border: 1px solid #3182CE;
                }
                QComboBox::drop-down { border: none; }
                
                QListWidget { 
                    background-color: #121212; 
                    border: 1px solid #282828; 
                    border-radius: 8px; 
                    padding: 6px; 
                    outline: none; 
                }
                QListWidget::item { 
                    padding: 10px; 
                    border-bottom: 1px solid #1E1E1E; 
                    border-radius: 4px;
                }
                QListWidget::item:selected { 
                    background-color: #252525; 
                    border: 1px solid #333333;
                }
                
                QProgressBar { 
                    border: none; 
                    border-radius: 6px; 
                    text-align: center; 
                    background-color: #252525; 
                    color: #FFFFFF;
                }
                QProgressBar::chunk { 
                    background-color: #3182CE; 
                    border-radius: 6px; 
                }
                
                QSlider::groove:horizontal { border-radius: 3px; height: 6px; background: #252525; }
                QSlider::handle:horizontal { background: #3182CE; width: 14px; margin: -4px 0; border-radius: 7px; }
                
                QScrollArea { background: transparent; border: none; }
                QScrollBar:vertical { background: transparent; width: 6px; margin: 0; border-radius: 3px; }
                QScrollBar::handle:vertical { background: #ECC94B; min-height: 20px; border-radius: 3px; }
                QScrollBar::handle:vertical:hover { background: #D69E2E; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

                /* —— 选中项 / 标签页 / 表格 / 文本框（暗色） —— */
                QListWidget::item:selected { background-color: #2D3748; color: #FFFFFF; }
                QScrollArea > QWidget#qt_scrollarea_viewport { background: transparent; }
                QScrollArea > QWidget#qt_scrollarea_viewport > QWidget { background: transparent; }
                QTabWidget::pane { background-color: #1A1A1A; border: 1px solid #282828; border-radius: 8px; top: -1px; }
                QTabWidget QStackedWidget { background: transparent; }
                QTabBar::tab { background: #252525; color: #A0AEC0; padding: 7px 16px; margin-right: 2px;
                               border-top-left-radius: 6px; border-top-right-radius: 6px; }
                QTabBar::tab:selected { background: #3182CE; color: #FFFFFF; font-weight: bold; }
                QTabBar::tab:hover:!selected { background: #303030; color: #E0E0E0; }
                QGroupBox { border: 1px solid #333333; border-radius: 8px; margin-top: 14px; padding-top: 8px; color: #E0E0E0; }
                QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #E0E0E0; }
                QTableWidget, QTableView { background-color: #121212; color: #E0E0E0; gridline-color: #282828;
                                           border: 1px solid #282828; border-radius: 8px;
                                           selection-background-color: #2D3748; selection-color: #FFFFFF; }
                QHeaderView::section { background-color: #252525; color: #E0E0E0; border: none;
                                       border-right: 1px solid #333333; padding: 6px; }
                QTableCornerButton::section { background-color: #252525; border: none; }
                QPlainTextEdit, QTextEdit { background-color: #121212; color: #E0E0E0;
                                            border: 1px solid #333333; border-radius: 6px; }
                QComboBox QAbstractItemView { background-color: #1A1A1A; color: #E0E0E0;
                                              selection-background-color: #2D3748; selection-color: #FFFFFF; }
                QDialog { background-color: #1A1A1A; }


                QCheckBox, QLabel { background: transparent; }
            """
        else:
            qss = """
                QMainWindow { background-color: #F8F9FA; }
                QWidget { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 10pt; color: #2D3748; }
                
                QFrame#Sidebar { 
                    background-color: #FFFFFF; 
                    border-right: 1px solid #E2E8F0; 
                }
                QLabel#LogoText { 
                    font-size: 15pt; 
                    font-weight: 600; 
                    color: #1A202C; 
                    padding: 10px 0;
                    letter-spacing: 1px;
                }
                
                QTreeWidget#NavTree { 
                    background: transparent; 
                    border: none; 
                    outline: none; 
                }
                QTreeWidget#NavTree::item { 
                    padding: 12px 10px; 
                    border-radius: 8px; 
                    margin: 4px 6px;
                }
                QTreeWidget#NavTree::item:hover { 
                    background-color: #F7FAFC; 
                }
                QTreeWidget#NavTree::item:selected { 
                    background-color: #EBF8FF; 
                    color: #3182CE; 
                    font-weight: bold; 
                }
                
                QFrame.Card { 
                    background-color: #FFFFFF; 
                    border-radius: 12px; 
                    border: 1px solid #E2E8F0; 
                }
                QLabel.CardTitle { 
                    font-size: 12pt; 
                    font-weight: bold; 
                    color: #1A202C; 
                }
                
                QPushButton { 
                    background-color: #FFFFFF; 
                    color: #4A5568; 
                    border: 1px solid #E2E8F0; 
                    border-radius: 6px; 
                    padding: 8px 16px; 
                }
                QPushButton:hover { 
                    background-color: #F7FAFC; 
                    border: 1px solid #CBD5E0; 
                }
                QPushButton:disabled { 
                    background-color: #F7FAFC; 
                    color: #A0AEC0; 
                    border: 1px solid #E2E8F0;
                }
                
                QPushButton.ActionBtn { 
                    background-color: #3182CE; 
                    color: white; 
                    border: none; 
                    font-weight: bold; 
                    padding: 10px 18px; 
                    border-radius: 8px;
                }
                QPushButton.ActionBtn:hover { 
                    background-color: #2B6CB0; 
                }
                
                QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit { 
                    background-color: #FFFFFF; 
                    border: 1px solid #E2E8F0; 
                    border-radius: 6px; 
                    padding: 6px 10px; 
                    color: #2D3748; 
                }
                QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QLineEdit:focus {
                    border: 1px solid #3182CE;
                }
                QComboBox::drop-down { border: none; }
                
                QListWidget { 
                    background-color: #FFFFFF; 
                    border: 1px solid #E2E8F0; 
                    border-radius: 8px; 
                    padding: 6px; 
                    outline: none; 
                }
                QListWidget::item { 
                    padding: 10px; 
                    border-bottom: 1px solid #F7FAFC; 
                    border-radius: 4px;
                }
                QListWidget::item:selected { 
                    background-color: #F7FAFC; 
                    border: 1px solid #E2E8F0;
                }
                
                QProgressBar { 
                    border: none; 
                    border-radius: 6px; 
                    text-align: center; 
                    background-color: #EDF2F7; 
                    color: #1A202C;
                }
                QProgressBar::chunk { 
                    background-color: #3182CE; 
                    border-radius: 6px; 
                }
                
                QSlider::groove:horizontal { border-radius: 3px; height: 6px; background: #E2E8F0; }
                QSlider::handle:horizontal { background: #3182CE; width: 14px; margin: -4px 0; border-radius: 7px; }
                
                QScrollArea { background: transparent; border: none; }
                QScrollBar:vertical { background: transparent; width: 6px; margin: 0; border-radius: 3px; }
                QScrollBar::handle:vertical { background: #CBD5E0; min-height: 20px; border-radius: 3px; }
                QScrollBar::handle:vertical:hover { background: #A0AEC0; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

                /* —— 选中项 / 标签页 / 表格 / 文本框（亮色） —— */
                QListWidget::item:selected { background-color: #EBF8FF; color: #1E3A8A; font-weight: bold; }
                QScrollArea > QWidget#qt_scrollarea_viewport { background: transparent; }
                QScrollArea > QWidget#qt_scrollarea_viewport > QWidget { background: transparent; }
                QTabWidget::pane { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; top: -1px; }
                QTabWidget QStackedWidget { background: transparent; }
                QTabBar::tab { background: #EDF2F7; color: #4A5568; padding: 7px 16px; margin-right: 2px;
                               border-top-left-radius: 6px; border-top-right-radius: 6px; }
                QTabBar::tab:selected { background: #3182CE; color: #FFFFFF; font-weight: bold; }
                QTabBar::tab:hover:!selected { background: #E2E8F0; color: #1A202C; }
                QGroupBox { border: 1px solid #E2E8F0; border-radius: 8px; margin-top: 14px; padding-top: 8px; color: #2D3748; }
                QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #2D3748; }
                QTableWidget, QTableView { background-color: #FFFFFF; color: #2D3748; gridline-color: #EDF2F7;
                                           border: 1px solid #E2E8F0; border-radius: 8px;
                                           selection-background-color: #EBF8FF; selection-color: #1E3A8A; }
                QHeaderView::section { background-color: #F7FAFC; color: #2D3748; border: none;
                                       border-right: 1px solid #E2E8F0; padding: 6px; }
                QTableCornerButton::section { background-color: #F7FAFC; border: none; }
                QPlainTextEdit, QTextEdit { background-color: #FFFFFF; color: #2D3748;
                                            border: 1px solid #E2E8F0; border-radius: 6px; }
                QComboBox QAbstractItemView { background-color: #FFFFFF; color: #2D3748;
                                              selection-background-color: #EBF8FF; selection-color: #1E3A8A; }
                QDialog { background-color: #F8F9FA; }
                QCheckBox, QLabel { background: transparent; }
            """
            import os
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            icon_dir = os.path.join(base_dir, "theme_icons").replace("\\", "/")
            qss += f"""
                QCheckBox::indicator {{ width: 16px; height: 16px; image: url('{icon_dir}/checkbox_unchecked.svg'); }}
                QCheckBox::indicator:checked {{ image: url('{icon_dir}/checkbox_checked.svg'); }}
                QRadioButton::indicator {{ width: 16px; height: 16px; image: url('{icon_dir}/radio_unchecked.svg'); }}
                QRadioButton::indicator:checked {{ image: url('{icon_dir}/radio_checked.svg'); }}
            """
            
        self.setStyleSheet(qss)

    def closeEvent(self, event):
        self.settings.setValue("is_dark_mode", self.is_dark_mode)
        self.video_tool.save_settings()
        self.img_merge_tool.save_settings()
        self.copyright_tool.save_settings()
        if hasattr(self, 'l2p_tool'):
            self.l2p_tool.save_settings()
        self.image_tool.save_settings()
        self.multi_segment_tool.save_settings()
        self.youtube_tool.save_settings()
        self.screenshot_tool.save_settings()
        self.gdrive_tool.save_settings()
        if hasattr(self, 'duet_tool'):
            self.duet_tool.save_settings()
        event.accept()

if __name__ == "__main__":
    import ctypes
    # Fix taskbar icon issue on Windows
    try:
        myappid = 'videotools.app.v1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    _MUTEX_NAME = "Global\\VideoToolbox_SingleInstance_v2"
    ctypes.windll.kernel32.SetLastError(0)
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    _last_error = ctypes.windll.kernel32.GetLastError()
    if _last_error == 183:
        # Instead of showing a popup, try to bring the existing window to front
        hwnd = ctypes.windll.user32.FindWindowW(None, "视频集成工具 v1.5.5")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9) # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path(os.path.join("log", "log.ico"))))
    
    from PyQt6.QtWidgets import QSplashScreen
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtCore import Qt
    splash_pix = QPixmap(resource_path(os.path.join("log", "log.ico")))
    if not splash_pix.isNull():
        splash_pix = splash_pix.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        splash = QSplashScreen(splash_pix, Qt.WindowType.WindowStaysOnTopHint)
        splash.show()
        app.processEvents()
    else:
        splash = None

    window = ToolboxApp()
    window.show()
    if splash:
        splash.finish(window)
    sys.exit(app.exec())