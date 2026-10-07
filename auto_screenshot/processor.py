# processor.py
import os
import shutil
from downloader import download_video
from extractor import extract_frames

def process_urls(urls, max_count, interval, base_path, base_folder_name, log_callback, stop_event):
    temp_dir = os.path.join(base_path, "temp_downloads")
    os.makedirs(temp_dir, exist_ok=True)
    
    success_count = 0
    
    for index, url in enumerate(urls):
        # --- 【核心修改】每次循环开始前检查停止信号 ---
        if stop_event.is_set():
            log_callback("🛑 任务已由用户手动强制停止。")
            break
            
        url = url.strip()
        if not url: continue
            
        log_callback(f"\n---> 开始处理第 {index+1} 个视频...")
        
        folder_name = f"{base_folder_name}_{index+1:03d}"
        output_folder = os.path.join(base_path, folder_name)
        os.makedirs(output_folder, exist_ok=True)
        
        # 下载视频
        log_callback(f"正在下载: {url}")
        video_path = download_video(url, temp_dir)
        
        # 再次检查信号（下载可能耗时很久，下载完再检查一次）
        if stop_event.is_set():
            if video_path and os.path.exists(video_path): os.remove(video_path)
            log_callback("🛑 任务在下载后停止。")
            break

        if not video_path:
            log_callback("❌ 下载失败，跳过。")
            continue
            
        # 截图
        log_callback("下载成功，正在截图...")
        success = extract_frames(video_path, output_folder, interval, max_count)
        
        if video_path and os.path.exists(video_path):
            try: os.remove(video_path)
            except: pass
            
        if success:
            success_count += 1
            log_callback(f"✅ 处理完成: {folder_name}")
        else:
            log_callback("❌ 截图过程出错。")
            
    try: shutil.rmtree(temp_dir)
    except: pass
    
    log_callback(f"\n🎉 流程结束。总计处理成功: {success_count} 个。")