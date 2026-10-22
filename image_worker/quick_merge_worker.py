# -*- coding: utf-8 -*-
"""
quick_merge_worker.py — 快速合并后台渲染线程

支持功能：
- 1 个板块（单板块自动归类合并）或 2~5 个板块配对合并
- 按名称相似度（可设阈值）或文件名开头数字自动匹配成组
- 支持「按顺序合并」与「随机顺序合并」
- 支持设置「每组输出数量」（当输出数量 > 1 时，多段匹配组会进行多轮合并，随机模式下每轮重新随机打乱顺序）
- 未匹配到的视频（只有 1 段）直接单独输出，同样应用静音/倍速/尺寸设置
- 保留原声 / 去除原声（支持全局静音及单板块静音）
- 倍速调节（0.25x ~ 4.0x）
- 丰富的 FFmpeg xfade 转场及自定义转场时长
- 多种目标画幅比例（9:16、16:9、3:4、4:3、4:5、1:1、19:6）与填充模式
- 输出保留原视频（以每组主视频为准）的文件名
"""
import os
import re
import random
import difflib
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal


TRANSITION_OPTIONS = [
    ("无转场 (直接拼接)", "none"),
    ("溶解过渡 (fade)", "fade"),
    ("向左滑动 (slideleft)", "slideleft"),
    ("向右滑动 (slideright)", "slideright"),
    ("向上滑动 (slideup)", "slideup"),
    ("向下滑动 (slidedown)", "slidedown"),
    ("平滑左移 (smoothleft)", "smoothleft"),
    ("平滑右移 (smoothright)", "smoothright"),
    ("直线左擦除 (wipeleft)", "wipeleft"),
    ("直线右擦除 (wiperight)", "wiperight"),
    ("颜色擦除 (colorwipe)", "colorwipe"),
    ("圆形展开 (circleopen)", "circleopen"),
    ("距离渐变 (distance)", "distance"),
    ("像素叠加 (pixelize)", "pixelize"),
    ("闪黑过渡 (fadeblack)", "fadeblack"),
    ("闪白过渡 (fadewhite)", "fadewhite"),
]

ASPECT_OPTIONS = [
    ("9:16 (竖屏 1080×1920)", "9:16"),
    ("16:9 (横屏 1920×1080)", "16:9"),
    ("3:4 (竖屏 1080×1440)", "3:4"),
    ("4:3 (横屏 1440×1080)", "4:3"),
    ("4:5 (竖屏 1080×1350)", "4:5"),
    ("1:1 (方形 1080×1080)", "1:1"),
    ("19:6 (超宽画幅 1900×600)", "19:6"),
]

FIT_OPTIONS = [
    ("完整保留画面（居中留黑边）", "pad"),
    ("居中裁剪铺满（无黑边）", "crop"),
    ("模糊背景填充（无黑边）", "blur"),
]


def extract_leading_number(filepath: str):
    """提取文件名开头的数字（忽略前导空格，01 与 1 视为相同数字 1）。无开头数字返回 None。"""
    stem = os.path.splitext(os.path.basename(filepath))[0].strip()
    m = re.match(r"^(\d+)", stem)
    if m:
        return int(m.group(1))
    return None


def compute_name_similarity(path_a: str, path_b: str) -> float:
    """计算两个视频文件名（不含扩展名）的相似度 (0.0 ~ 1.0)。"""
    stem_a = os.path.splitext(os.path.basename(path_a))[0].strip()
    stem_b = os.path.splitext(os.path.basename(path_b))[0].strip()
    if not stem_a or not stem_b:
        return 0.0
    if stem_a.lower() == stem_b.lower():
        return 1.0
    r1 = difflib.SequenceMatcher(None, stem_a, stem_b).ratio()
    r2 = difflib.SequenceMatcher(None, stem_a.lower(), stem_b.lower()).ratio()
    return max(r1, r2)


def _match_single_slot_groups(
    video_list: list[str],
    match_mode: str = "similarity",
    similarity_threshold: float = 0.60,
) -> list[dict]:
    """
    单板块模式：将同一个板块中的所有视频按「开头数字」或「名称相似度」自动聚类分组。
    """
    raw_groups = []
    if not video_list:
        return raw_groups

    if match_mode == "number":
        num_clusters = {}   # num -> list of (0, path)
        ordered_items = []  # ("num", num) or ("single", path)
        for p in video_list:
            num = extract_leading_number(p)
            if num is not None:
                if num not in num_clusters:
                    num_clusters[num] = []
                    ordered_items.append(("num", num))
                num_clusters[num].append((0, p))
            else:
                ordered_items.append(("single", p))

        for kind, val in ordered_items:
            if kind == "num":
                clips = num_clusters[val]
                primary_path = clips[0][1]
                if len(clips) > 1:
                    info = f"开头数字 #{val}（共 {len(clips)} 段）"
                else:
                    info = f"开头数字 #{val}（未匹配，单独输出）"
                raw_groups.append({
                    "clips": clips,
                    "primary_path": primary_path,
                    "match_info": info,
                })
            else:
                raw_groups.append({
                    "clips": [(0, val)],
                    "primary_path": val,
                    "match_info": "无开头数字（单独输出）",
                })
    else:
        # 按名称相似度聚类：遍历每个视频，找相似度最高且 >= 阈值的已有分组归入；否则新建分组
        clusters = []  # [{"primary_path": p, "clips": [(0, p), ...], "sims": [...]}, ...]
        for p in video_list:
            best_idx = -1
            best_sim = -1.0
            for c_idx, cl in enumerate(clusters):
                # 与该组主视频或组内成员比较相似度（取最高值，同时要求与组主视频相似度不低于阈值的 85%）
                sim_primary = compute_name_similarity(p, cl["primary_path"])
                sim_any = max(compute_name_similarity(p, mp) for _, mp in cl["clips"])
                sim = max(sim_primary, sim_any if sim_primary >= similarity_threshold * 0.85 else sim_primary)
                if sim >= similarity_threshold and sim > best_sim:
                    best_sim = sim
                    best_idx = c_idx
            if best_idx >= 0:
                clusters[best_idx]["clips"].append((0, p))
                clusters[best_idx]["sims"].append(best_sim)
            else:
                clusters.append({
                    "primary_path": p,
                    "clips": [(0, p)],
                    "sims": [],
                })

        for cl in clusters:
            clips = cl["clips"]
            if len(clips) > 1:
                avg_sim = sum(cl["sims"]) / len(cl["sims"])
                info = f"相似度 {int(round(avg_sim * 100))}%（共 {len(clips)} 段）"
            else:
                info = "未达到阈值（单独输出）"
            raw_groups.append({
                "clips": clips,
                "primary_path": cl["primary_path"],
                "match_info": info,
            })

    return raw_groups


def match_video_groups(
    slot_lists: list[list[str]],
    match_mode: str = "similarity",
    similarity_threshold: float = 0.60,
    include_other_unmatched: bool = False,
    merge_order: str = "sequential",
    output_count: int = 1,
) -> list[dict]:
    """
    根据匹配模式将 1 个或多个板块中的视频进行配对，并按合并顺序与输出数量生成最终任务列表。

    参数:
        slot_lists: 长度为 N (1~5) 的列表，每个元素是该板块的视频路径列表
        match_mode:
            - "similarity": 按文件名相似度匹配（>= similarity_threshold）
            - "number":     按文件名开头数字匹配
            - "order":      按列表顺序依次匹配（多板块模式）
        similarity_threshold: 相似度阈值 (0.0 ~ 1.0)
        include_other_unmatched: 多板块下是否将视频2~N中未匹配到的视频也单独输出
        merge_order:
            - "sequential": 按顺序合并
            - "random":     在匹配到的同组视频中随机顺序合并
        output_count: 每组输出数量（>= 1）。当 > 1 时，多段匹配组会进行多轮合并，
                      若为随机顺序则每一轮都会重新随机打乱顺序。
    """
    if not slot_lists:
        return []

    num_slots = len(slot_lists)
    output_count = max(1, int(output_count or 1))

    # ── 单板块模式（1 个板块一股脑丢入自动归类）──────────────────────────
    if num_slots == 1:
        raw_groups = _match_single_slot_groups(
            slot_lists[0],
            match_mode=match_mode,
            similarity_threshold=similarity_threshold,
        )
    else:
        # ── 多板块模式（2 ~ 5 个板块配对）────────────────────────────────
        base_list = list(slot_lists[0]) if slot_lists else []
        used_in_slot = [set() for _ in range(num_slots)]
        raw_groups = []

        if match_mode == "number":
            slot_num_map = []
            for s_idx in range(num_slots):
                mp = {}
                for idx, p in enumerate(slot_lists[s_idx]):
                    num = extract_leading_number(p)
                    if num is not None:
                        mp.setdefault(num, []).append(idx)
                slot_num_map.append(mp)

            for i0, p0 in enumerate(base_list):
                used_in_slot[0].add(i0)
                num0 = extract_leading_number(p0)
                clips = [(0, p0)]
                if num0 is not None:
                    for s_idx in range(1, num_slots):
                        candidates = slot_num_map[s_idx].get(num0, [])
                        picked = next((c for c in candidates if c not in used_in_slot[s_idx]), None)
                        if picked is not None:
                            used_in_slot[s_idx].add(picked)
                            clips.append((s_idx, slot_lists[s_idx][picked]))
                if len(clips) > 1:
                    info = f"开头数字 #{num0}（共 {len(clips)} 段）"
                elif num0 is not None:
                    info = f"开头数字 #{num0}（未匹配，单独输出）"
                else:
                    info = "无开头数字（单独输出）"
                raw_groups.append({
                    "clips": clips,
                    "primary_path": p0,
                    "match_info": info,
                })

        elif match_mode == "similarity":
            slot_matches = [{} for _ in range(num_slots)]
            for s_idx in range(1, num_slots):
                other_list = slot_lists[s_idx]
                pairs = []
                for i0, p0 in enumerate(base_list):
                    for ik, pk in enumerate(other_list):
                        sim = compute_name_similarity(p0, pk)
                        if sim >= similarity_threshold:
                            pairs.append((sim, -i0, -ik, i0, ik))
                pairs.sort(reverse=True)
                matched_i0 = set()
                for sim, _, _, i0, ik in pairs:
                    if i0 not in matched_i0 and ik not in used_in_slot[s_idx]:
                        matched_i0.add(i0)
                        used_in_slot[s_idx].add(ik)
                        slot_matches[s_idx][i0] = (ik, sim)

            for i0, p0 in enumerate(base_list):
                used_in_slot[0].add(i0)
                clips = [(0, p0)]
                sims = []
                for s_idx in range(1, num_slots):
                    if i0 in slot_matches[s_idx]:
                        ik, sim = slot_matches[s_idx][i0]
                        clips.append((s_idx, slot_lists[s_idx][ik]))
                        sims.append(sim)
                if len(clips) > 1:
                    avg_sim = sum(sims) / len(sims)
                    info = f"相似度 {int(round(avg_sim * 100))}%（共 {len(clips)} 段）"
                else:
                    info = "未达到阈值（单独输出）"
                raw_groups.append({
                    "clips": clips,
                    "primary_path": p0,
                    "match_info": info,
                })

        else:
            for i0, p0 in enumerate(base_list):
                used_in_slot[0].add(i0)
                clips = [(0, p0)]
                for s_idx in range(1, num_slots):
                    if i0 < len(slot_lists[s_idx]):
                        used_in_slot[s_idx].add(i0)
                        clips.append((s_idx, slot_lists[s_idx][i0]))
                info = f"顺序第 {i0 + 1} 组（共 {len(clips)} 段）" if len(clips) > 1 else f"顺序第 {i0 + 1} 组（单独输出）"
                raw_groups.append({
                    "clips": clips,
                    "primary_path": p0,
                    "match_info": info,
                })

        if include_other_unmatched or not base_list:
            for s_idx in range(1, num_slots):
                for ik, pk in enumerate(slot_lists[s_idx]):
                    if ik not in used_in_slot[s_idx]:
                        used_in_slot[s_idx].add(ik)
                        raw_groups.append({
                            "clips": [(s_idx, pk)],
                            "primary_path": pk,
                            "match_info": f"视频{s_idx + 1} 未匹配（单独输出）",
                        })

    # ── 按轮次（output_count）与合并顺序（sequential / random）展开任务 ──
    expanded_groups = []
    last_order_by_group = {}  # group_idx -> tuple of paths

    for round_idx in range(output_count):
        for g_idx, g in enumerate(raw_groups):
            base_clips = list(g["clips"])
            is_single = len(base_clips) == 1

            # 第 2 轮及之后：只对有多个视频的匹配组进行额外轮次合并
            if round_idx > 0 and is_single:
                continue

            clips = list(base_clips)
            if not is_single and merge_order == "random":
                prev_tuple = last_order_by_group.get(g_idx)
                for _ in range(12):
                    random.shuffle(clips)
                    cur_tuple = tuple(p for _, p in clips)
                    if cur_tuple != prev_tuple:
                        break
                last_order_by_group[g_idx] = tuple(p for _, p in clips)
            else:
                last_order_by_group[g_idx] = tuple(p for _, p in clips)

            info = g["match_info"]
            if output_count > 1 and not is_single:
                info = f"[第{round_idx + 1}组] {info}"

            expanded_groups.append({
                "clips": clips,
                "primary_path": g["primary_path"],
                "match_info": info,
                "is_single": is_single,
                "round_idx": round_idx,
            })

    # ── 生成保留原视频命名的输出文件名（重名自动加 _2, _3 ... 保护）────────
    used_names = set()
    results = []
    for g in expanded_groups:
        stem = os.path.splitext(os.path.basename(g["primary_path"]))[0]
        candidate = f"{stem}.mp4"
        if candidate.lower() in used_names:
            idx = 2
            while f"{stem}_{idx}.mp4".lower() in used_names:
                idx += 1
            candidate = f"{stem}_{idx}.mp4"
        used_names.add(candidate.lower())
        results.append({
            "clips": g["clips"],
            "primary_path": g["primary_path"],
            "output_name": candidate,
            "match_info": g["match_info"],
            "is_single": g["is_single"],
            "round_idx": g.get("round_idx", 0),
        })

    return results


class QuickMergeWorker(QThread):
    """快速合并 FFmpeg 后台渲染线程。"""
    progress = pyqtSignal(int, str)
    task_status = pyqtSignal(int, str)   # (row_index, status_text)
    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        groups: list[dict],
        output_dir: str,
        ffmpeg_path: str,
        ffprobe_path: str,
        aspect_ratio: str = "9:16",
        fit_mode: str = "pad",
        speed: float = 1.0,
        mute_global: bool = False,
        slot_mutes: dict | None = None,
        transition: str = "none",
        transition_dur: float = 0.6,
        parent=None,
    ):
        super().__init__(parent)
        self.groups = groups
        self.output_dir = output_dir
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.aspect_ratio = aspect_ratio
        self.fit_mode = fit_mode
        self.speed = max(0.1, float(speed))
        self.mute_global = bool(mute_global)
        self.slot_mutes = slot_mutes or {}
        self.transition = transition or "none"
        self.transition_dur = max(0.1, float(transition_dur))
        self._stop = False

    def stop(self):
        self._stop = True

    def _probe_duration(self, filepath: str) -> float:
        cmd = [
            self.ffprobe_path, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            filepath,
        ]
        try:
            res = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            return max(0.1, float(res.stdout.strip()))
        except Exception:
            return 5.0

    def _has_audio(self, filepath: str) -> bool:
        cmd = [
            self.ffprobe_path, "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            filepath,
        ]
        try:
            res = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            return len(res.stdout.strip()) > 0
        except Exception:
            return False

    @staticmethod
    def _atempo_chain(speed: float) -> str:
        if abs(speed - 1.0) < 1e-4:
            return ""
        parts = []
        s = speed
        while s < 0.5:
            parts.append("atempo=0.5")
            s /= 0.5
        while s > 2.0:
            parts.append("atempo=2.0")
            s /= 2.0
        parts.append(f"atempo={s:.4f}")
        return ",".join(parts)

    def _target_dimensions(self) -> tuple[int, int, str]:
        mapping = {
            "9:16": (1080, 1920, "9/16"),
            "16:9": (1920, 1080, "16/9"),
            "3:4":  (1080, 1440, "3/4"),
            "4:3":  (1440, 1080, "4/3"),
            "4:5":  (1080, 1350, "4/5"),
            "1:1":  (1080, 1080, "1/1"),
            "19:6": (1900, 600,  "19/6"),
        }
        return mapping.get(self.aspect_ratio, (1080, 1920, "9/16"))

    def _video_scale_filter(self, idx: int, target_w: int, target_h: int) -> str:
        pts_expr = f"setpts={1.0 / self.speed:.6f}*PTS" if abs(self.speed - 1.0) > 1e-4 else "setpts=PTS-STARTPTS"
        common_tail = f"setsar=1,fps=30,format=yuv420p,{pts_expr},settb=AVTB"
        if self.fit_mode == "crop":
            return (
                f"[{idx}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                f"crop={target_w}:{target_h},{common_tail}[v{idx}];"
            )
        elif self.fit_mode == "blur":
            return (
                f"[{idx}:v]split=2[bg{idx}][fg{idx}];"
                f"[bg{idx}]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                f"crop={target_w}:{target_h},boxblur=20:10[bgb{idx}];"
                f"[fg{idx}]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease[fgs{idx}];"
                f"[bgb{idx}][fgs{idx}]overlay=(W-w)/2:(H-h)/2,{common_tail}[v{idx}];"
            )
        else:
            return (
                f"[{idx}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black,{common_tail}[v{idx}];"
            )

    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)
        target_w, target_h, aspect_str = self._target_dimensions()
        total = len(self.groups)
        success_count = 0

        for row_idx, group in enumerate(self.groups):
            if self._stop:
                self.finished.emit(False, f"已手动停止（已完成 {success_count}/{total} 个视频）。")
                return

            clips = group["clips"]   # [(slot_idx, path), ...]
            out_name = group["output_name"]
            out_path = os.path.join(self.output_dir, out_name)

            pct = int(row_idx * 100 / max(1, total))
            self.progress.emit(pct, f"正在合成 ({row_idx + 1}/{total}): {out_name}")
            self.task_status.emit(row_idx, "⏳ 合成中...")

            inputs = []
            durations = []
            silent_input_map = {}
            next_input_idx = len(clips)

            for idx, (slot_idx, vid_path) in enumerate(clips):
                inputs.extend(["-i", vid_path])
                raw_dur = self._probe_duration(vid_path)
                post_dur = max(0.1, raw_dur / self.speed)
                durations.append(post_dur)

                clip_muted = self.mute_global or bool(self.slot_mutes.get(slot_idx, False))
                if not self.mute_global:
                    if clip_muted or not self._has_audio(vid_path):
                        silent_input_map[idx] = next_input_idx
                        inputs.extend([
                            "-f", "lavfi",
                            "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100:d={post_dur:.3f}"
                        ])
                        next_input_idx += 1

            filter_complex = ""
            atempo_str = self._atempo_chain(self.speed)

            for idx, (slot_idx, _) in enumerate(clips):
                filter_complex += self._video_scale_filter(idx, target_w, target_h)
                if not self.mute_global:
                    if idx in silent_input_map:
                        a_in = f"[{silent_input_map[idx]}:a]"
                        filter_complex += (
                            f"{a_in}aresample=44100:async=1,"
                            f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                            f"atrim=duration={durations[idx]:.3f},asetpts=PTS-STARTPTS[a{idx}];"
                        )
                    else:
                        a_in = f"[{idx}:a]"
                        a_spd = f"{atempo_str}," if atempo_str else ""
                        filter_complex += (
                            f"{a_in}{a_spd}aresample=44100:async=1,"
                            f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                            f"asetpts=PTS-STARTPTS[a{idx}];"
                        )

            n_clips = len(clips)
            v_streams = [f"[v{i}]" for i in range(n_clips)]
            a_streams = [f"[a{i}]" for i in range(n_clips)]

            if n_clips == 1:
                filter_complex += "[v0]null[outv];"
                if not self.mute_global:
                    filter_complex += "[a0]anull[outa];"
            elif self.transition != "none":
                safe_fade = min(self.transition_dur, min(durations) * 0.45)
                safe_fade = max(0.05, safe_fade)
                cur_v = v_streams[0]
                cur_offset = max(0.0, durations[0] - safe_fade)
                for idx in range(1, n_clips):
                    nxt_v = v_streams[idx]
                    is_last = (idx == n_clips - 1)
                    out_v = "[xfadelast]" if is_last else f"[xfade{idx}]"
                    filter_complex += (
                        f"{cur_v}{nxt_v}xfade=transition={self.transition}:"
                        f"duration={safe_fade:.3f}:offset={max(0.0, cur_offset):.3f}{out_v};"
                    )
                    cur_v = out_v
                    cur_offset += durations[idx] - safe_fade
                filter_complex += "[xfadelast]setpts=PTS-STARTPTS[outv];"

                if not self.mute_global:
                    cur_a = a_streams[0]
                    for idx in range(1, n_clips):
                        nxt_a = a_streams[idx]
                        out_a = "[outa]" if idx == n_clips - 1 else f"[afade{idx}]"
                        filter_complex += f"{cur_a}{nxt_a}acrossfade=d={safe_fade:.3f}{out_a};"
                        cur_a = out_a
            else:
                if self.mute_global:
                    concat_v = "".join(v_streams)
                    filter_complex += f"{concat_v}concat=n={n_clips}:v=1:a=0[outv];"
                else:
                    interleaved = "".join(f"{v_streams[k]}{a_streams[k]}" for k in range(n_clips))
                    filter_complex += f"{interleaved}concat=n={n_clips}:v=1:a=1[outv][outa];"

            filter_complex = filter_complex.rstrip(";")

            cmd = [self.ffmpeg_path, "-y"] + inputs + ["-filter_complex", filter_complex, "-map", "[outv]"]
            if self.mute_global:
                cmd.append("-an")
            else:
                cmd.extend(["-map", "[outa]", "-c:a", "aac", "-b:a", "192k"])

            cmd.extend([
                "-c:v", "libx264",
                "-crf", "21",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-aspect", aspect_str,
                os.path.abspath(out_path),
            ])

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                _, stderr = proc.communicate()
                if proc.returncode != 0:
                    err_lines = "\n".join(stderr.strip().splitlines()[-5:])
                    self.task_status.emit(row_idx, "❌ 失败")
                    self.finished.emit(False, f"合成「{out_name}」时出错：\n{err_lines}")
                    return
                success_count += 1
                self.task_status.emit(row_idx, "✅ 完成")
            except Exception as e:
                self.task_status.emit(row_idx, "❌ 失败")
                self.finished.emit(False, f"执行 FFmpeg 时出错：\n{e}")
                return

        self.progress.emit(100, f"✅ 全部完成！共输出 {success_count} 个视频")
        self.finished.emit(True, f"快速合并全部完成！\n共成功导出 {success_count} 个视频至：\n{self.output_dir}")
