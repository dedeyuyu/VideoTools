import os
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal

class FFmpegWorker(QThread):
    progress = pyqtSignal(int, str)  
    finished = pyqtSignal(bool, str) 

    def __init__(self, tasks, transition, aspect_ratio, resolution, speed, mute, ffmpeg_path, ffprobe_path,
                 audio_loop: bool = True, audio_volume: int = 100):
        super().__init__()
        self.tasks = tasks  
        self.transition = transition
        self.aspect_ratio = aspect_ratio
        self.resolution = resolution
        self.speed = speed
        self.mute = mute
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.audio_loop = audio_loop
        self.audio_volume = audio_volume
        self.is_stopped = False

    def get_video_duration(self, filepath):
        cmd = [self.ffprobe_path, '-v', 'error', '-show_entries', 
               'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', filepath]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return float(res.stdout.strip())
        except: return 0.0

    def has_audio(self, filepath):
        cmd = [self.ffprobe_path, '-v', 'error', '-select_streams', 'a', 
               '-show_entries', 'stream=codec_type', '-of', 'default=noprint_wrappers=1:nokey=1', filepath]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return len(res.stdout.strip()) > 0
        except: return False

    def get_atempo_filter(self, speed):
        if speed == 1.0: return ""
        filters = []
        temp_speed = speed
        while temp_speed < 0.5:
            filters.append("atempo=0.5")
            temp_speed /= 0.5
        filters.append(f"atempo={temp_speed}")
        return ",".join(filters)

    def _get_video_total_duration(self, task_videos: list) -> float:
        """Estimate the total merged video duration (used for audio trim)."""
        total = 0.0
        for vid in task_videos:
            total += self.get_video_duration(vid) / self.speed
        return total

    def _get_audio_bitrate(self, audio_path: str) -> str:
        """Probe source audio bitrate; fall back to 192k on any error."""
        ffprobe = self.ffprobe_path
        try:
            cmd = [
                ffprobe, "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=bit_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            raw = res.stdout.strip()
            if raw and raw.isdigit():
                bps = int(raw)
                kbps = max(96, min(320, bps // 1000))
                return f"{kbps}k"
        except Exception:
            pass
        return "192k"

    def get_target_dimensions(self):
        """核心计算：将画幅比例和分辨率结合，得出具体的宽高像素值"""
        res_map = {"720P": (720, 1280), "1080P": (1080, 1920), "2K": (1440, 2560), "4K": (2160, 3840)}
        short_edge, long_edge = res_map.get(self.resolution, (1080, 1920))

        if self.aspect_ratio == "16:9": return long_edge, short_edge, "16/9"
        elif self.aspect_ratio == "9:16": return short_edge, long_edge, "9/16"
        elif self.aspect_ratio == "3:4": return short_edge, int(short_edge * 4 / 3), "3/4"
        elif self.aspect_ratio == "4:5": return short_edge, int(short_edge * 5 / 4), "4/5"
        elif self.aspect_ratio == "1:1": return short_edge, short_edge, "1/1"
        else: return short_edge, long_edge, "9/16"

    def run(self):
        t_map = {"溶解": "fade", "滑动": "slideleft", "颜色擦去": "colorwipe", "直线擦去": "wipeleft", 
                 "对比并移动": "distance", "流动": "smoothleft", "堆叠": "squish", "叠加": "pixelize"}
        trans_name = t_map.get(self.transition, "fade")
        
        target_w, target_h, aspect_str = self.get_target_dimensions()
        
        total_tasks = len(self.tasks)
        for i, task in enumerate(self.tasks):
            if self.is_stopped:
                self.finished.emit(False, "手动停止")
                return

            task_videos = task["videos"]
            output_file = task["output_file"]
            if not task_videos: continue

            # ── Background audio (mute=True: replace original; mute=False+audio: mix with amix) ──
            audio_path: str | None = task.get("audio_path")
            skip_start: float = task.get("audio_skip_start", 0.0)
            fade_in:    float = task.get("audio_fade_in",    0.0)
            has_bg_audio = bool(audio_path and os.path.isfile(audio_path))
            
            self.progress.emit(int((i / total_tasks) * 100), f"正在处理第 {i+1}/{total_tasks} 个视频 ({target_w}x{target_h})...")

            inputs = []
            durations = []
            missing_audio_map = {}
            lavfi_idx = len(task_videos)
            
            for idx, vid in enumerate(task_videos):
                inputs.extend(['-i', vid])
                dur = self.get_video_duration(vid)
                durations.append(dur / self.speed)
                
                if not self.mute and not self.has_audio(vid):
                    missing_audio_map[idx] = lavfi_idx
                    inputs.extend(['-f', 'lavfi', '-i', f'anullsrc=channel_layout=stereo:sample_rate=44100:d={dur}'])
                    lavfi_idx += 1

            # Input index for the background audio stream
            bg_audio_idx = lavfi_idx
            if has_bg_audio:
                if self.audio_loop:
                    if skip_start > 0:
                        inputs.extend(['-stream_loop', '-1', '-ss', f'{skip_start:.3f}', '-i', audio_path])
                    else:
                        inputs.extend(['-stream_loop', '-1', '-i', audio_path])
                else:
                    if skip_start > 0:
                        inputs.extend(['-ss', f'{skip_start:.3f}', '-i', audio_path])
                    else:
                        inputs.extend(['-i', audio_path])

            filter_complex = ""
            fade_dur = 1.0

            for idx in range(len(task_videos)):
                filter_complex += (
                    f"[{idx}:v]scale={target_w}:{target_h}:"
                    f"force_original_aspect_ratio=decrease,"
                    f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,"
                    f"setsar=1,fps=fps=30,setpts={1/self.speed}*PTS[v{idx}];"
                )
                
                if not self.mute:
                    audio_in = f"[{missing_audio_map[idx]}:a]" if idx in missing_audio_map else f"[{idx}:a]"
                    audio_speed = self.get_atempo_filter(self.speed)
                    a_filter = f"{audio_speed}," if audio_speed else ""
                    filter_complex += f"{audio_in}{a_filter}aresample=44100:async=1,aformat=sample_fmts=fltp:channel_layouts=stereo[a{idx}];"

            v_streams = [f"[v{idx}]" for idx in range(len(task_videos))]
            a_streams = [f"[a{idx}]" for idx in range(len(task_videos))]

            if len(task_videos) > 1 and self.transition != "无转场":
                current_v = v_streams[0]
                current_offset = durations[0] - fade_dur
                for idx in range(1, len(task_videos)):
                    next_v = v_streams[idx]
                    is_last = (idx == len(task_videos) - 1)
                    out_v = f"[xfade{idx}]" if not is_last else "[xfadelast]"
                    safe_offset = max(0, current_offset)
                    filter_complex += (
                        f"{current_v}{next_v}xfade=transition={trans_name}:"
                        f"duration={fade_dur}:offset={safe_offset:.3f}{out_v};"
                    )
                    current_v = out_v
                    current_offset += durations[idx] - fade_dur
                # 重置最终输出的 PTS，防止最后一帧冻结
                filter_complex += "[xfadelast]setpts=PTS-STARTPTS[outv];"
                    
                if not self.mute:
                    current_a = a_streams[0]
                    for idx in range(1, len(task_videos)):
                        next_a = a_streams[idx]
                        out_a = f"[afade{idx}]" if idx < len(task_videos) - 1 else "[outa]"
                        filter_complex += f"{current_a}{next_a}acrossfade=d={fade_dur}{out_a};"
                        current_a = out_a
            else:
                if self.mute:
                    concat_v = "".join(v_streams)
                    filter_complex += f"{concat_v}concat=n={len(task_videos)}:v=1:a=0[outv];"
                else:
                    # ffmpeg concat 要求流必须交错排列：[v0][a0][v1][a1]...
                    # 不能将所有视频流放前面再跟所有音频流，否则 pad 类型不匹配
                    interleaved = "".join(
                        f"{v_streams[k]}{a_streams[k]}" for k in range(len(task_videos))
                    )
                    filter_complex += f"{interleaved}concat=n={len(task_videos)}:v=1:a=1[outv][outa];"

            # ── Background audio filter chain ────────────────────────────────────
            if has_bg_audio:
                total_video_dur = sum(durations)
                # 转场会使前后片段重叠，实际视频时长比原始累加短
                n_clips = len(task_videos)
                uses_xfade = (n_clips > 1 and self.transition != "无转场")
                effective_video_dur = (
                    total_video_dur - (n_clips - 1) * fade_dur
                    if uses_xfade else total_video_dur
                )
                a_filters = []
                if fade_in > 0:
                    a_filters.append(f"afade=t=in:st=0:d={fade_in:.2f}")
                if self.audio_volume != 100:
                    a_filters.append(f"volume={self.audio_volume / 100.0:.3f}")
                a_filters.extend([
                    f"atrim=duration={effective_video_dur:.3f}",
                    "asetpts=PTS-STARTPTS",
                    "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo",
                ])
                if self.mute:
                    # 去掉原声：背景音乐直接作为 [outa]
                    filter_complex += f"[{bg_audio_idx}:a]{','.join(a_filters)}[outa]"
                else:
                    # 保留原声：背景音乐处理后与原声 amix 混合
                    filter_complex += f"[{bg_audio_idx}:a]{','.join(a_filters)}[bga];"
                    filter_complex += f"[outa][bga]amix=inputs=2:duration=first:normalize=0[outa]"

            cmd = [self.ffmpeg_path, '-y'] + inputs
            if self.mute and has_bg_audio:
                # 去掉原声 + 背景音乐
                cmd.extend(['-filter_complex', filter_complex, '-map', '[outv]', '-map', '[outa]',
                             '-c:a', 'aac', '-b:a', self._get_audio_bitrate(audio_path)])
            elif self.mute:
                # 去掉声音，无背景音乐
                cmd.extend(['-filter_complex', filter_complex, '-map', '[outv]', '-an'])
            elif has_bg_audio:
                # 保留原声 + 背景音乐混音（amix 输出已写入 [outa]）
                cmd.extend(['-filter_complex', filter_complex, '-map', '[outv]', '-map', '[outa]',
                             '-c:a', 'aac', '-b:a', self._get_audio_bitrate(audio_path)])
            else:
                # 保留原声，无背景音乐
                cmd.extend(['-filter_complex', filter_complex, '-map', '[outv]', '-map', '[outa]'])

            cmd.extend(['-c:v', 'libx264', '-crf', '23', '-preset', 'fast', '-aspect', aspect_str, os.path.abspath(output_file)])

            try:
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', creationflags=subprocess.CREATE_NO_WINDOW)
                stdout, stderr = process.communicate()
                if process.returncode != 0:
                    err_str = "\n".join(stderr.strip().split('\n')[-4:])
                    self.finished.emit(False, f"合并遭遇未知错误:\n{err_str}")
                    return
            except Exception as e:
                self.finished.emit(False, f"错误: {str(e)}")
                return

        self.progress.emit(100, "全部处理完成！")
        self.finished.emit(True, "所有视频处理完毕。")

    def stop(self): self.is_stopped = True