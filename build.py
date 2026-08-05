"""
build.py  -- VideoTools packaging script
Usage: python build.py  (run from d:\\Antigravity\\VideoTools)
Output: dist folder -> \\VideoTools\\VideoTools.exe + all DLLs
"""

import os
import sys
import shutil
import subprocess

ROOT      = os.path.dirname(os.path.abspath(__file__))
DIST_DIR  = os.path.join(ROOT, "dist_pack")
WORK_DIR  = os.path.join(ROOT, "_build_temp")
OUT_APP   = os.path.join(DIST_DIR, "VideoTools")
SPEC_FILE = os.path.join(ROOT, "videotools.spec")
FFMPEG_SRC = os.path.join(ROOT, "ffmpeg")
FINAL_DIR  = os.path.join(ROOT, "\u6253\u5305")   # Chinese "pack" folder

print("=" * 60)
print("Step 1: Check PyInstaller ...")
try:
    import PyInstaller
    print("  [OK] PyInstaller", PyInstaller.__version__)
except ImportError:
    print("  [!] Not found, installing ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    print("  [OK] PyInstaller installed")

print("\nStep 2: Clean old output ...")
if os.path.exists(OUT_APP):
    shutil.rmtree(OUT_APP)
    print("  Removed:", OUT_APP)
if os.path.exists(WORK_DIR):
    shutil.rmtree(WORK_DIR)
os.makedirs(DIST_DIR, exist_ok=True)

print("\nStep 3: Run PyInstaller (onedir mode) ...")
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--clean",
    f"--distpath={DIST_DIR}",
    f"--workpath={WORK_DIR}",
    SPEC_FILE,
]
result = subprocess.run(cmd, cwd=ROOT)
if result.returncode != 0:
    print("\n  [FAIL] PyInstaller build failed!")
    sys.exit(1)
print("  [OK] Build succeeded")

print("\nStep 4: Copy ffmpeg / ffprobe ...")
ffmpeg_dst = os.path.join(OUT_APP, "ffmpeg")
os.makedirs(ffmpeg_dst, exist_ok=True)
for exe_name in ("ffmpeg.exe", "ffprobe.exe"):
    src = os.path.join(FFMPEG_SRC, exe_name)
    dst = os.path.join(ffmpeg_dst, exe_name)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        size_mb = os.path.getsize(dst) / (1024 * 1024)
        print(f"  [OK] {exe_name}  ({size_mb:.1f} MB)")
    else:
        print(f"  [WARN] {src} not found - copy ffmpeg manually")

print("\nStep 5: Move result to output folder ...")
if os.path.exists(FINAL_DIR):
    # Kill any running instance that may be locking DLLs in the old folder
    import subprocess as _sp
    _sp.run(
        ["taskkill", "/F", "/IM", "VideoTools.exe"],
        capture_output=True
    )
    import time; time.sleep(0.6)
    shutil.rmtree(FINAL_DIR, ignore_errors=True)
shutil.move(OUT_APP, FINAL_DIR)
shutil.rmtree(DIST_DIR, ignore_errors=True)
print("  [OK] Moved to:", FINAL_DIR)

print("\nStep 6: Clean temp build files ...")
if os.path.exists(WORK_DIR):
    shutil.rmtree(WORK_DIR)
    print("  [OK] Removed:", WORK_DIR)

print("\n" + "=" * 60)
print("[DONE] Build complete!")
print("  App folder :", FINAL_DIR)
print("  Launch with:", os.path.join(FINAL_DIR, "VideoTools.exe"))
print("=" * 60)

# ── Step 7: Build Inno Setup installer ───────────────────────────────
print("\nStep 7: Build Inno Setup installer ...")

ISCC_PATHS = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    r"C:\Program Files\Inno Setup 5\ISCC.exe",
]
ISS_FILE  = os.path.join(ROOT, "installer", "VideoTools.iss")
OUT_DIR   = os.path.join(ROOT, "output_installer")
os.makedirs(OUT_DIR, exist_ok=True)

iscc = None
for p in ISCC_PATHS:
    if os.path.exists(p):
        iscc = p
        break

if iscc is None:
    print("  [WARN] Inno Setup Compiler (ISCC.exe) not found.")
    print("         Please compile installer\\VideoTools.iss manually.")
else:
    print(f"  Using: {iscc}")
    res = subprocess.run([iscc, ISS_FILE], cwd=ROOT)
    if res.returncode == 0:
        # 找到生成的安装包文件
        for fname in os.listdir(OUT_DIR):
            if fname.endswith(".exe"):
                size_mb = os.path.getsize(os.path.join(OUT_DIR, fname)) / (1024 * 1024)
                print(f"  [OK]  Installer: {fname}  ({size_mb:.1f} MB)")
        print("  [OK] Installer built successfully!")
    else:
        print("  [FAIL] Inno Setup build failed — check the .iss file.")

print("\nAll done!")
