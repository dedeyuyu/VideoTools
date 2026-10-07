# extractor.py
import subprocess
import os

def extract_frames(video_path, output_folder, interval, max_count):
    """使用 FFmpeg 截图。
    interval: 间隔秒数 (如 0.5)
    max_count: 最大截图数量
    """
    try:
        # 换算帧率
        fps = 1.0 / float(interval)
        output_pattern = os.path.join(output_folder, "%02d.jpg")
        
        # 构建 FFmpeg 命令
        command = [
            'ffmpeg',
            '-ss', '0.3',                 # 首帧从 0.3 秒开始
            '-i', os.path.abspath(video_path),
            '-vf', f'fps={fps}',
            '-vframes', str(max_count),
            os.path.abspath(output_pattern),
            '-y'
        ]
        
        # --- 【核心修改区：隐藏弹出的黑框】 ---
        creationflags = 0
        if os.name == 'nt':  # 判断当前如果是 Windows 系统
            # 加上这句魔法代码，就能彻底压制黑框的弹出
            creationflags = subprocess.CREATE_NO_WINDOW 
        # -----------------------------------
        
        # 运行命令，加入 creationflags 参数
        subprocess.run(
            command, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            creationflags=creationflags,   # <--- 加上这个参数
            check=True
        )
        return True
    except Exception as e:
        print(f"截图出错: {e}")
        return False