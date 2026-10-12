# 🎬 视频集成工具箱 (VideoTools)

一款基于 PyQt6 的桌面视频/图片处理工具箱，集成多种实用功能。界面支持 **简体中文 / English**（左下角「设置」中切换）。

## ✨ 功能模块

| 模块 | 功能 |
|------|------|
| ✨ 合拍视频批量合成 | 主视频 + 人物视频批量对齐、多格/画中画模板、标题/电话卡片、批量导出 |
| 🚀 视频合并与转场 | 多段视频合并、添加转场特效 |
| ✨ 图片合并成视频 | 将图片序列合成为视频 |
| 🎨 处理版权图片 | 人脸检测遮脸（马赛克/模糊等）+ 大头图裁剪，支持手动标记区域 |
| 🔃 横屏转竖屏 | 横屏视频转竖屏 |
| 🖼️ 图片批量裁剪 | 批量裁剪图片 |
| 🎞️ 多片段合成 | 多片段视频合成 |
| 📸 链接截图 | 网页/链接自动截图 |
| ⏩ 自动调速 | 视频加速，可自动控制在 3 分钟以内 |
| 📥 YouTube下载 | 使用 yt-dlp 下载 YouTube 视频 |
| ☁️ 云盘下载 | 云盘文件下载 |

## 🛠️ 环境要求

- Python 3.12 / 3.13
- Windows 10/11

## 🚀 运行（源码）

双击 **`启动VideoTools.bat`**：会自动寻找已安装 PyQt6 的 Python；如果缺依赖，会提示一键安装 `requirements.txt`。

也可以手动运行：

```bash
pip install -r requirements.txt
python main/main.py
```

## 📁 目录说明

```
VideoTools/
├── 启动VideoTools.bat     # 源码启动入口（双击运行）
├── main/main.py           # 主窗口 / 程序入口
├── UI/                    # 各功能界面
│   ├── i18n.py            #   多语言（中文/English）显示层
│   ├── i18n_en.py         #   英文翻译表
│   ├── ui_settings.py     #   设置窗口（语言、主题……）
│   └── ui_*.py            #   各工具界面
├── image_worker/          # 后台处理（FFmpeg 渲染、对齐、调速等）
├── Video/                 # 视频合并辅助模块
├── theme_icons/           # 界面 SVG 图标
├── log/log.ico            # 软件图标
├── duet_data/             # 合拍工具的设置、模板、卡片预设（用户数据，勿删）
├── duet_card_library/     # 卡片素材图库
├── duet_fonts/            # 卡片字体
├── duet_cache/            # 默认缓存目录（可在软件里改到别处）
├── crash_logs/            # 崩溃日志（软件出错时自动生成）
├── ffmpeg/                # ffmpeg.exe / ffprobe.exe
├── yt-dlp.exe             # 下载工具
├── whisper_runner.py      # 语音识别子进程
├── audio_library.json     # 背景音乐库列表
│
├── build.py               # 打包：PyInstaller + Inno Setup
├── videotools.spec        # PyInstaller 配置
├── installer/             # Inno Setup 安装包脚本
├── upload_installer.py    # 上传安装包到 GitHub Release（令牌放 github_token.txt，不入库）
├── 打包/                   # build.py 生成的绿色版程序（不入库）
├── output_installer/      # build.py 生成的安装包（只保留最新版）
│
└── _archive/              # 旧的临时脚本、旧原型、旧安装包、测试文件（不入库，确认不需要可整个删除）
```

## 📄 许可证

MIT License
