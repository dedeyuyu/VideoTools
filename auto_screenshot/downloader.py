# downloader.py
import yt_dlp
import os

def download_video(url, temp_dir):
    """下载视频到指定目录，返回下载后的本地视频路径，失败返回 None"""
    try:
        # yt-dlp 的下载配置
        ydl_opts = {
            'outtmpl': os.path.join(temp_dir, 'temp_video_%(id)s.%(ext)s'),
            'format': 'best', # 下载最佳画质
            'quiet': True,    # 隐藏控制台的下载刷屏信息
            'noplaylist': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename
    except Exception as e:
        print(f"下载出错 [{url}]: {e}")
        return None