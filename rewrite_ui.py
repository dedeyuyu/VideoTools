import sys
import os

def rewrite_main():
    with open("main/main.py", "r", encoding="utf-8") as f:
        content = f.read()

    import re
    # Replace the imports
    content = re.sub(
        r'from PyQt6\.QtWidgets import \(QApplication, QMainWindow, QWidget, QHBoxLayout,\n                             QStackedWidget, QVBoxLayout, QPushButton, QFrame,\n                             QLabel, QScrollArea\)',
        r'from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,\n                             QStackedWidget, QVBoxLayout, QPushButton, QFrame,\n                             QLabel, QScrollArea, QTreeWidget, QTreeWidgetItem)',
        content
    )

    # Replace setup_ui
    setup_ui_new = '''    def setup_ui(self):
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
        
        self.item_video = QTreeWidgetItem(["🚀 视频合并与转场"])
        self.item_img_merge = QTreeWidgetItem(["✨ 图片合并成视频"])
        self.item_copyright = QTreeWidgetItem(["🎨 处理版权图片"])
        self.item_l2p = QTreeWidgetItem(["🔃 横屏转竖屏"])
        self.item_image = QTreeWidgetItem(["🖼️ 图片批量裁剪"])
        self.item_multi = QTreeWidgetItem(["🎞️ 多片段合成"])
        self.item_screenshot = QTreeWidgetItem(["📸 链接截图"])
        
        cat_video.addChildren([self.item_video, self.item_img_merge, self.item_copyright, 
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
        self.btn_components.setToolTip("管理必要组件 — FFmpeg / opencv-python\\n检测状态 / 一键下载安装")
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

        self.video_tool      = VideoMergerUI()
        self.img_merge_tool  = ImageMergerUI()
        self.copyright_tool  = CopyrightProcessorUI()
        self.l2p_tool        = LandscapeToPortraitUI()
        self.image_tool      = ImageCropperUI()
        self.multi_segment_tool = MultiSegmentUI()
        self.screenshot_tool = AutoScreenshotUI()
        self.youtube_tool    = YouTubeDownloaderUI()
        self.gdrive_tool     = GDriveDownloaderUI()

        self.stacked_widget.addWidget(self.video_tool)          # 0
        self.stacked_widget.addWidget(self.img_merge_tool)      # 1
        self.stacked_widget.addWidget(self.copyright_tool)      # 2
        self.stacked_widget.addWidget(self.l2p_tool)            # 3
        self.stacked_widget.addWidget(self.image_tool)          # 4
        self.stacked_widget.addWidget(self.multi_segment_tool)  # 5
        self.stacked_widget.addWidget(self.screenshot_tool)     # 6
        self.stacked_widget.addWidget(self.youtube_tool)        # 7
        self.stacked_widget.addWidget(self.gdrive_tool)         # 8

        self.content_layout.addWidget(self.stacked_widget)
        self.main_layout.addWidget(self.content_widget)

        self.item_to_index = {
            self.item_video: 0,
            self.item_img_merge: 1,
            self.item_copyright: 2,
            self.item_l2p: 3,
            self.item_image: 4,
            self.item_multi: 5,
            self.item_screenshot: 6,
            self.item_youtube: 7,
            self.item_gdrive: 8,
        }

        self.nav_tree.itemClicked.connect(self.on_tree_item_clicked)
        self.nav_tree.setCurrentItem(self.item_video)
        self.stacked_widget.setCurrentIndex(0)

    def on_tree_item_clicked(self, item, column):
        if item in self.item_to_index:
            self.stacked_widget.setCurrentIndex(self.item_to_index[item])
'''

    content = re.sub(
        r'    def setup_ui\(self\):.*?    def switch_tab\(self, index, active_btn\):\n        self\.stacked_widget\.setCurrentIndex\(index\)\n        for btn in self\.nav_buttons:\n            btn\.setChecked\(False\)\n        active_btn\.setChecked\(True\)',
        setup_ui_new,
        content,
        flags=re.DOTALL
    )

    # Replace QSS logic for Sidebar and TreeWidget
    dark_qss = r"""
                QMainWindow { background-color: #1a1d27; }
                QWidget { font-family: "Microsoft YaHei", "Segoe UI"; font-size: 10pt; color: #d1d5db; }
                QFrame#Sidebar { background-color: #1e222d; border-right: 1px solid #2b303b; }
                QLabel#LogoText { font-size: 14pt; font-weight: bold; color: #ffffff; }
                QTreeWidget#NavTree { background: transparent; border: none; outline: none; }
                QTreeWidget#NavTree::item { padding: 8px; border-radius: 6px; }
                QTreeWidget#NavTree::item:hover { background-color: #2b303b; }
                QTreeWidget#NavTree::item:selected { background-color: #f43f5e; color: #ffffff; font-weight: bold; }
"""

    light_qss = r"""
                QMainWindow { background-color: #f3f4f6; }
                QWidget { font-family: "Microsoft YaHei", "Segoe UI"; font-size: 10pt; color: #374151; }
                QFrame#Sidebar { background-color: #ffffff; border-right: 1px solid #e5e7eb; }
                QLabel#LogoText { font-size: 14pt; font-weight: bold; color: #111827; }
                QTreeWidget#NavTree { background: transparent; border: none; outline: none; }
                QTreeWidget#NavTree::item { padding: 8px; border-radius: 6px; }
                QTreeWidget#NavTree::item:hover { background-color: #f3f4f6; }
                QTreeWidget#NavTree::item:selected { background-color: #3b82f6; color: #ffffff; font-weight: bold; }
"""

    content = re.sub(r'QMainWindow \{ background-color: #1a1d27; \}.*?QPushButton\.NavBtn:checked \{ background-color: #f43f5e; color: #ffffff; \} ', dark_qss, content, flags=re.DOTALL)
    content = re.sub(r'QMainWindow \{ background-color: #f3f4f6; \}.*?QPushButton\.NavBtn:checked \{ background-color: #3b82f6; color: #ffffff; \} ', light_qss, content, flags=re.DOTALL)


    with open("main/main.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    rewrite_main()
