import os
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal


class ImageMergeWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, tasks, duration, aspect_ratio, resolution,
                 enable_trans, trans_name, enable_eff, eff_name,
                 ffmpeg_path, audio_loop: bool = True,
                 audio_volume: int = 100):
        super().__init__()
        self.tasks = tasks
        self.duration = duration
        self.aspect_ratio = aspect_ratio
        self.resolution = resolution
        self.enable_trans = enable_trans
        self.trans_name = trans_name
        self.enable_eff = enable_eff
        self.eff_name = eff_name
        self.ffmpeg_path = ffmpeg_path
        self.audio_loop = audio_loop
        self.audio_volume = audio_volume
        self.is_stopped = False

    # ------------------------------------------------------------------ #
    #  Dimension helpers                                                   #
    # ------------------------------------------------------------------ #

    def get_target_dimensions(self):
        res_map = {"720P": (720, 1280), "1080P": (1080, 1920), "2K": (1440, 2560), "4K": (2160, 3840)}
        short_edge, long_edge = res_map.get(self.resolution, (1080, 1920))

        if self.aspect_ratio == "16:9":   return long_edge,  short_edge,            "16/9"
        elif self.aspect_ratio == "9:16": return short_edge, long_edge,             "9/16"
        elif self.aspect_ratio == "3:4":  return short_edge, int(short_edge*4/3),   "3/4"
        elif self.aspect_ratio == "4:5":  return short_edge, int(short_edge*5/4),   "4/5"
        elif self.aspect_ratio == "1:1":  return short_edge, short_edge,            "1/1"
        else:                             return short_edge, long_edge,             "9/16"

    # ------------------------------------------------------------------ #
    #  Motion-effect filter                                                #
    # ------------------------------------------------------------------ #

    def get_effect_filter(self, w, h, frames):
        """Core Ken-Burns / colour-grade algorithm bank."""
        mapping = {
            "Zoom Center":       f"zoompan=z='min(max(zoom,1)+0.0015,1.5)':x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':d={frames}:s={w}x{h}",
            "Zoom Top-Left":     f"zoompan=z='min(max(zoom,1)+0.0015,1.5)':x='0':y='0':d={frames}:s={w}x{h}",
            "Zoom Top-Right":    f"zoompan=z='min(max(zoom,1)+0.0015,1.5)':x='iw-(iw/zoom)':y='0':d={frames}:s={w}x{h}",
            "Zoom Bottom-Left":  f"zoompan=z='min(max(zoom,1)+0.0015,1.5)':x='0':y='ih-(ih/zoom)':d={frames}:s={w}x{h}",
            "Zoom Bottom-Right": f"zoompan=z='min(max(zoom,1)+0.0015,1.5)':x='iw-(iw/zoom)':y='ih-(ih/zoom)':d={frames}:s={w}x{h}",
            "Zoom Out":          f"zoompan=z='if(lt(on,15), 1+(on/15)*0.5, max(1.5-(on-15)*0.0008, 1))':x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':d={frames}:s={w}x{h}",
            "Pan Up":            f"zoompan=z='1.3':x='iw/2-(iw/zoom)/2':y='(ih-ih/zoom)*(1 - (on/{frames})*0.3)':d={frames}:s={w}x{h}",
            "B&W":               "colorchannelmixer=.3:.4:.3:0:.3:.4:.3:0:.3:.4:.3:0",
            "EQ":                "eq=contrast=1.2:brightness=0.05:saturation=1.3",
        }
        return mapping.get(self.eff_name, "")

    # ------------------------------------------------------------------ #
    #  Audio helpers                                                       #
    # ------------------------------------------------------------------ #

    def _get_audio_bitrate(self, audio_path: str) -> str:
        """Probe source audio bitrate; fall back to 192k on any error."""
        ffprobe = self.ffmpeg_path.replace("ffmpeg.exe", "ffprobe.exe")
        if not os.path.isfile(ffprobe):
            return "192k"
        try:
            cmd = [
                ffprobe, "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=bit_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            raw = res.stdout.strip()
            if raw and raw.isdigit():
                bps = int(raw)
                # Clamp between 96k and 320k
                kbps = max(96, min(320, bps // 1000))
                return f"{kbps}k"
        except Exception:
            pass
        return "192k"

    # ------------------------------------------------------------------ #
    #  Main worker loop                                                    #
    # ------------------------------------------------------------------ #

    def run(self):
        target_w, target_h, aspect_str = self.get_target_dimensions()
        total_tasks = len(self.tasks)

        is_zoom_effect = self.enable_eff and ("Zoom" in self.eff_name or "Pan" in self.eff_name)

        for i, task in enumerate(self.tasks):
            if self.is_stopped:
                self.finished.emit(False, "用户手动停止了任务。")
                return

            images = task["images"]
            output_file = task["output_file"]
            audio_path: str | None = task.get("audio_path")
            if not images:
                continue

            self.progress.emit(
                int((i / total_tasks) * 100),
                f"正在生成视频 {i + 1}/{total_tasks} ({target_w}x{target_h})..."
            )

            # ── Calculate total video time ────────────────────────────────
            fade_duration = 1 if self.enable_trans and len(images) > 1 else 0
            if self.enable_trans and len(images) > 1:
                total_video_time = len(images) * self.duration - (len(images) - 1) * fade_duration
            else:
                total_video_time = len(images) * self.duration

            # ── Build input list ──────────────────────────────────────────
            inputs = []
            for img in images:
                inputs.extend(["-loop", "1", "-t", str(self.duration), "-i", img])

            has_audio = bool(audio_path and os.path.isfile(audio_path))
            audio_idx = len(images)  # index in FFmpeg input list

            # Per-audio skip/fade (stored in the library by the user)
            skip_start: float = task.get("audio_skip_start", 0.0)
            fade_in:    float = task.get("audio_fade_in",    0.0)

            if has_audio:
                # Using -ss before -i so FFmpeg seeks before decoding.
                # Combined with -stream_loop -1 this restarts from skip_start
                # on every loop iteration — clean and frame-accurate.
                if self.audio_loop:
                    if skip_start > 0:
                        inputs.extend(["-stream_loop", "-1", "-ss", f"{skip_start:.3f}", "-i", audio_path])
                    else:
                        inputs.extend(["-stream_loop", "-1", "-i", audio_path])
                else:
                    if skip_start > 0:
                        inputs.extend(["-ss", f"{skip_start:.3f}", "-i", audio_path])
                    else:
                        inputs.extend(["-i", audio_path])

            # ── Build video filter_complex ────────────────────────────────
            filter_complex = ""
            v_streams = []

            for idx, img in enumerate(images):
                if is_zoom_effect:
                    scale_w = int(target_w) * 2
                    scale_h = int(target_h) * 2
                    chain = (f"[{idx}:v]fps=25,"
                             f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=decrease,"
                             f"pad={scale_w}:{scale_h}:(ow-iw)/2:(oh-ih)/2")
                else:
                    chain = (f"[{idx}:v]fps=25,"
                             f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                             f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2")

                if self.enable_eff:
                    total_frames = int(self.duration * 25)
                    eff = self.get_effect_filter(target_w, target_h, total_frames)
                    if eff:
                        chain += f",{eff}"

                chain += f",trim=duration={self.duration},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v{idx}];"
                filter_complex += chain
                v_streams.append(f"[v{idx}]")

            # ── Video stream concat / xfade ───────────────────────────────
            if self.enable_trans and len(images) > 1:
                current_stream = v_streams[0]
                for idx in range(1, len(images)):
                    next_stream = v_streams[idx]
                    offset = idx * (self.duration - fade_duration)
                    out_stream = f"[xfade{idx}]" if idx < len(images) - 1 else "[outv]"
                    filter_complex += (
                        f"{current_stream}{next_stream}"
                        f"xfade=transition={self.trans_name}:duration={fade_duration}:offset={offset}"
                        f"{out_stream};"
                    )
                    current_stream = out_stream
            else:
                concat_str = "".join(v_streams)
                filter_complex += f"{concat_str}concat=n={len(images)}:v=1:a=0[outv];"

            # ── Audio filter chain ────────────────────────────────────────
            if has_audio:
                a_filters = []
                # 1. Fade-in (applied at t=0 of the already-seeked stream)
                if fade_in > 0:
                    a_filters.append(f"afade=t=in:st=0:d={fade_in:.2f}")
                # 2. Volume adjustment (skip at 100% to save processing)
                if self.audio_volume != 100:
                    a_filters.append(f"volume={self.audio_volume / 100.0:.3f}")
                # 3. Trim to exact video duration & normalise format
                a_filters.extend([
                    f"atrim=duration={total_video_time:.3f}",
                    "asetpts=PTS-STARTPTS",
                    "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo",
                ])
                filter_complex += f"[{audio_idx}:a]{','.join(a_filters)}[outa]"

            # ── Assemble FFmpeg command ───────────────────────────────────
            audio_bitrate = self._get_audio_bitrate(audio_path) if has_audio else "192k"

            cmd = [self.ffmpeg_path, "-y"] + inputs + [
                "-filter_complex", filter_complex,
                "-map", "[outv]",
            ]

            if has_audio:
                cmd.extend(["-map", "[outa]", "-c:a", "aac", "-b:a", audio_bitrate])
            else:
                cmd.extend(["-an"])

            cmd.extend([
                "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                "-aspect", aspect_str,
                "-t", str(total_video_time),
                output_file,
            ])

            # ── Execute ───────────────────────────────────────────────────
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                _stdout, stderr = process.communicate()
                if process.returncode != 0:
                    err_str = "\n".join(stderr.strip().split("\n")[-5:])
                    self.finished.emit(False, f"底层合并崩溃，生成失败：\n{err_str}")
                    return
            except Exception as e:
                self.finished.emit(False, f"进程执行错误: {str(e)}")
                return

        self.progress.emit(100, "全部处理完成！")
        self.finished.emit(True, "所有视频已成功生成。")

    def stop(self):
        self.is_stopped = True