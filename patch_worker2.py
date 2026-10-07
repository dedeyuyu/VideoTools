import re
import codecs

path = r"d:\Antigravity\VideoTools\image_worker\duet_worker.py"
with codecs.open(path, 'r', 'utf-8') as f:
    code = f.read()

# Update signature
code = code.replace(
    '                     wm_png: str = "",',
    '                     wm_png: str = "", global_speed: float = 1.0, max_3min: bool = False,'
)

# Replace final filter complex assembly
old_fc_assembly = """    fc.append(f"[{last}]scale={out_w}:{out_h},format=yuv420p[outv]")

    audio_srcs = []
    if task.get("p_audio"):
        audio_srcs.append("[0:a]")
    if task.get("v_audio") and not mute_viral:
        audio_srcs.append("[1:a]")
    amap = None
    if len(audio_srcs) == 2:
        fc.append(f"{audio_srcs[1]}{audio_srcs[0]}amix=inputs=2:duration=longest:normalize=0,volume={volume:.2f}[outa]")
        amap = "[outa]"
    elif len(audio_srcs) == 1:
        fc.append(f"{audio_srcs[0]}volume={volume:.2f}[outa]")
        amap = "[outa]"

    cmd += ["-filter_complex", ";".join(fc), "-map", "[outv]"]
    if amap:
        cmd += ["-map", amap, "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]
    cmd += _encoder_args(enc_key, quality)
    cmd += ["-t", f"{D:.3f}", "-movflags", "+faststart", out_path]"""

new_fc_assembly = """    fc.append(f"[{last}]scale={out_w}:{out_h},format=yuv420p[outv]")

    audio_srcs = []
    if task.get("p_audio"):
        audio_srcs.append("[0:a]")
    if task.get("v_audio") and not mute_viral:
        audio_srcs.append("[1:a]")
    amap = None
    if len(audio_srcs) == 2:
        fc.append(f"{audio_srcs[1]}{audio_srcs[0]}amix=inputs=2:duration=longest:normalize=0,volume={volume:.2f}[outa]")
        amap = "[outa]"
    elif len(audio_srcs) == 1:
        fc.append(f"{audio_srcs[0]}volume={volume:.2f}[outa]")
        amap = "[outa]"

    final_v = "outv"
    final_a = amap.strip("[]") if amap else None
    
    speed = max(0.1, float(global_speed))
    if max_3min and D > 180.0:
        req_speed = D / 179.5
        if req_speed > speed:
            speed = req_speed
            
    if abs(speed - 1.0) > 1e-3:
        fc.append(f"[{final_v}]setpts=PTS/{speed:.4f}[speedv]")
        final_v = "speedv"
        if final_a:
            af = _atempo_chain(speed)
            fc.append(f"[{final_a}]{af}[speeda]")
            final_a = "speeda"

    cmd += ["-filter_complex", ";".join(fc), "-map", f"[{final_v}]"]
    if final_a:
        cmd += ["-map", f"[{final_a}]", "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]
    cmd += _encoder_args(enc_key, quality)
    
    out_duration = D / speed
    cmd += ["-t", f"{out_duration:.3f}", "-movflags", "+faststart", out_path]"""

code = code.replace(old_fc_assembly, new_fc_assembly)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(code)

print("Patched duet_worker.py")
