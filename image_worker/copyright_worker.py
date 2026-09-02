# copyright_worker.py
"""
后台工作线程：版权图片处理
模式一：人物遮脸 — 检测人脸 → 绘制遮脸图形 + 裁剪大头图
模式二：左右裁剪 — 检测人脸中心 X 轴 → 左右分割
依赖：opencv-python（人脸检测）、Pillow（图像处理）
"""

import math
import os
import threading
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PIL import Image, ImageDraw, ImageFilter

SUPPORTED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}


# ── 人脸检测 ──────────────────────────────────────────────────────────────────

def _detect_largest_face(img_rgb, min_confidence: float = 0.15):
    """
    检测图片中面积最大的人脸。
    返回 (face_rect, feature_rect) 两个 (x, y, w, h)：
      face_rect    — 完整人脸检测框（用于大头图扩展裁剪）
      feature_rect — 仅眼/鼻/嘴关键点的紧凑框（用于遮脸图形，更精准）
    未检测到时返回 (None, None)。
    """
    _mp_error = None
    _cv_error = None

    # ── 优先：mediapipe ────────────────────────────────────────────────────
    try:
        import numpy as np
        import mediapipe as mp

        h_img, w_img = img_rgb.shape[:2]
        img_c = np.ascontiguousarray(img_rgb, dtype=np.uint8)

        # 准备缩放版（宽度压缩到 640），有助于大图检测
        if w_img > 640:
            scale   = 640 / w_img
            import cv2 as _cv2s
            img_small = _cv2s.resize(img_c, (640, int(h_img * scale)),
                                     interpolation=_cv2s.INTER_AREA)
            sx, sy = 1 / scale, 1 / scale
        else:
            img_small = img_c
            sx = sy = 1.0

        result_face    = None
        result_feature = None

        # ── solutions API（mediapipe 0.10.x）─────────────────────────────
        if hasattr(mp, 'solutions'):
            mp_face = mp.solutions.face_detection
            # 多级置信度：用户值 → 0.1 → 0.05（越来越宽松）
            conf_levels = sorted(set([min_confidence, 0.1, 0.05]))
            found = False
            for conf in conf_levels:
                if found:
                    break
                # model_selection=0 近景/自拍模型（肖像更精准），先尝试
                for model_sel in (0, 1):
                    if found:
                        break
                    for try_img in (img_c, img_small):
                        try:
                            with mp_face.FaceDetection(
                                model_selection=model_sel,
                                min_detection_confidence=conf
                            ) as det:
                                res = det.process(try_img)

                            if not (res and res.detections):
                                continue

                            # 选面积最大的检测结果
                            def _area(d):
                                b = d.location_data.relative_bounding_box
                                return b.width * b.height
                            lg = max(res.detections, key=_area)
                            b  = lg.location_data.relative_bounding_box

                            # 缩放图换算回原始坐标
                            _sx = sx if (try_img is img_small) else 1.0
                            _sy = sy if (try_img is img_small) else 1.0
                            th  = try_img.shape[0]
                            tw  = try_img.shape[1]

                            x   = max(0, int(b.xmin  * tw * _sx))
                            y   = max(0, int(b.ymin  * th * _sy))
                            fw  = min(int(b.width  * tw * _sx), w_img - x)
                            fh  = min(int(b.height * th * _sy), h_img - y)
                            result_face = (x, y, fw, fh)

                            # ── 关键点：眼/鼻/嘴 → 精准遮脸框 ──────────
                            kps = lg.location_data.relative_keypoints
                            if len(kps) >= 4:
                                # kps[0]=右眼, [1]=左眼, [2]=鼻尖, [3]=嘴中
                                kx = [kps[i].x * tw * _sx for i in range(4)]
                                ky = [kps[i].y * th * _sy for i in range(4)]
                                kx1, kx2 = min(kx), max(kx)
                                ky1, ky2 = min(ky), max(ky)
                                span_x = max(kx2 - kx1, 30)
                                span_y = max(ky2 - ky1, 30)
                                # 四周各加 40% span 的 padding，使遮挡自然盖住面部
                                px = span_x * 0.40
                                py = span_y * 0.40
                                feat_x = max(0, int(kx1 - px))
                                feat_y = max(0, int(ky1 - py))
                                feat_w = min(int(span_x + 2 * px), w_img - feat_x)
                                feat_h = min(int(span_y + 2 * py), h_img - feat_y)
                                result_feature = (feat_x, feat_y, feat_w, feat_h)
                            else:
                                # 无关键点：用检测框中部 70% 作为遮脸区域
                                shrink_x = int(fw * 0.15)
                                shrink_y = int(fh * 0.15)
                                result_feature = (x + shrink_x, y + shrink_y,
                                                  fw - 2 * shrink_x, fh - 2 * shrink_y)
                            found = True
                            break
                        except Exception:
                            continue

        # ── Tasks API（mediapipe >= 1.0）──────────────────────────────────
        if result_face is None and hasattr(mp, 'tasks'):
            try:
                import os as _os2
                from mediapipe.tasks.python.vision import FaceDetector
                from mediapipe.tasks.python import BaseOptions
                model_path = _os2.path.join(
                    _os2.path.dirname(_os2.path.abspath(__file__)),
                    "face_detector.tflite"
                )
                if _os2.path.isfile(model_path):
                    base_opts = BaseOptions(model_asset_path=model_path)
                    opts = FaceDetector.FaceDetectorOptions(base_options=base_opts)
                    with FaceDetector.create_from_options(opts) as det:
                        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_c)
                        dr = det.detect(mp_img)
                    if dr.detections:
                        d  = max(dr.detections,
                                 key=lambda x: x.bounding_box.width * x.bounding_box.height)
                        bb = d.bounding_box
                        result_face = (max(0, bb.origin_x), max(0, bb.origin_y),
                                       bb.width, bb.height)
                        # Tasks API 无详细关键点，用检测框近似
                        x, y, fw, fh = result_face
                        shrink_x = int(fw * 0.15)
                        shrink_y = int(fh * 0.15)
                        result_feature = (x + shrink_x, y + shrink_y,
                                          fw - 2 * shrink_x, fh - 2 * shrink_y)
            except Exception:
                pass

        # mediapipe 引擎可用，返回结果
        if hasattr(mp, 'solutions') or hasattr(mp, 'tasks'):
            return result_face, result_feature

    except ImportError:
        _mp_error = "mediapipe 未安装"
    except Exception as e:
        _mp_error = f"mediapipe 运行失败: {e}"

    # ── 备用：cv2 Haar Cascade ─────────────────────────────────────────────
    try:
        import sys, os as _os, importlib
        for key in [k for k in sys.modules if k == 'cv2' or k.startswith('cv2.')]:
            del sys.modules[key]
        importlib.invalidate_caches()
        import cv2

        if not hasattr(cv2, 'CascadeClassifier'):
            raise AttributeError("CascadeClassifier 属性缺失")

        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        if not _os.path.isfile(cascade_path):
            raise FileNotFoundError(f"haarcascade 文件不存在: {cascade_path}")

        face_cascade = cv2.CascadeClassifier(cascade_path)
        if face_cascade.empty():
            raise RuntimeError("CascadeClassifier.empty()=True，XML 加载失败")

        gray  = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
        faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30)
        )
        if len(faces) == 0:
            return None, None
        largest_cv = tuple(max(faces, key=lambda f: int(f[2]) * int(f[3])))
        x, y, w, h = largest_cv
        shrink_x = int(w * 0.1)
        shrink_y = int(h * 0.1)
        feat = (x + shrink_x, y + shrink_y, w - 2*shrink_x, h - 2*shrink_y)
        return largest_cv, feat

    except (ImportError, AttributeError) as e:
        _cv_error = f"cv2 不可用: {e}"
    except Exception as e:
        _cv_error = f"cv2 错误: {e}"

    # ── 两者均不可用 ──────────────────────────────────────────────────────
    details = []
    if _mp_error:
        details.append(f"  • mediapipe: {_mp_error}")
    if _cv_error:
        details.append(f"  • cv2: {_cv_error}")

    raise RuntimeError(
        "人脸检测引擎均不可用，详细原因：\n"
        + "\n".join(details)
        + "\n\n请重启软件后重试，或在「📦 下载必要组件」中重新安装 mediapipe。"
    )


# ── 遮脸图形绘制 ──────────────────────────────────────────────────────────────

def _star_points(cx: float, cy: float, outer_r: float, inner_r: float, n: int = 5):
    """计算 n 角星的多边形顶点（PIL polygon 格式）。"""
    pts = []
    for i in range(n * 2):
        angle = math.pi / n * i - math.pi / 2
        r = outer_r if i % 2 == 0 else inner_r
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return pts


def apply_cover(
    img: Image.Image,
    face_rect: tuple,
    cover_style: str,
    circle_color: tuple = (255, 80, 80),
) -> Image.Image:
    """
    在图片的人脸区域绘制遮挡效果，返回新的 PIL Image（不修改原图）。
    cover_style: "mosaic" | "blur" | "black_box" | "colored_circle" | "star" | "smiley"
    """
    out = img.copy().convert("RGB")
    x, y, w, h = (int(v) for v in face_rect)
    draw = ImageDraw.Draw(out)

    cx = x + w // 2
    cy = y + h // 2
    r  = min(w, h) // 2

    if cover_style == "mosaic":
        region = out.crop((x, y, x + w, y + h))
        block  = max(1, min(w, h) // 10)
        small  = region.resize((max(1, w // block), max(1, h // block)), Image.NEAREST)
        pixelated = small.resize((w, h), Image.NEAREST)
        out.paste(pixelated, (x, y))

    elif cover_style == "blur":
        region  = out.crop((x, y, x + w, y + h))
        radius  = max(8, min(w, h) // 5)
        blurred = region.filter(ImageFilter.GaussianBlur(radius=radius))
        out.paste(blurred, (x, y))

    elif cover_style == "black_box":
        draw.rectangle([x, y, x + w, y + h], fill=(0, 0, 0))

    elif cover_style == "colored_circle":
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tuple(circle_color))

    elif cover_style == "star":
        pts = _star_points(cx, cy, r, r * 0.4)
        draw.polygon(pts, fill=(255, 200, 0))   # 金黄色

    elif cover_style == "smiley":
        # 黄色圆脸
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 220, 0))
        # 眼睛
        eye_r = max(2, r // 8)
        eye_y = cy - r // 4
        offset = r // 3
        draw.ellipse([cx - offset - eye_r, eye_y - eye_r,
                      cx - offset + eye_r, eye_y + eye_r], fill=(30, 30, 30))
        draw.ellipse([cx + offset - eye_r, eye_y - eye_r,
                      cx + offset + eye_r, eye_y + eye_r], fill=(30, 30, 30))
        # 笑弧
        smile_margin = r // 2
        smile_box = [cx - smile_margin, cy,
                     cx + smile_margin, cy + r // 2]
        line_w = max(2, r // 10)
        draw.arc(smile_box, start=0, end=180, fill=(30, 30, 30), width=line_w)

    return out


# ── 大头图裁剪 ────────────────────────────────────────────────────────────────

def crop_portrait(img: Image.Image, face_rect: tuple) -> Image.Image:
    """
    扩展人脸检测框以包含完整头部，裁剪大头图。
    向上扩展 60% 脸高（包含发顶/头顶），左右各 10%（包含耳朵），向下微扩 3%。
    最终裁剪紧贴头部，最大化面部+头部占比。
    """
    x, y, w, h = (int(v) for v in face_rect)
    W, H = img.size

    exp_top    = int(h * 0.60)   # 向上：包含头发/发顶
    exp_side   = int(w * 0.10)   # 左右：包含耳朵
    exp_bottom = int(h * 0.03)   # 向下：下巴微扩

    x1 = max(0, x - exp_side)
    y1 = max(0, y - exp_top)
    x2 = min(W, x + w + exp_side)
    y2 = min(H, y + h + exp_bottom)

    return img.crop((x1, y1, x2, y2))




# ── 左右分割 ──────────────────────────────────────────────────────────────────

def split_lr(img: Image.Image, face_rect):
    """
    以人脸中心 X 轴为分割点，将图片分为左/右两张。
    分割点强制约束在图片宽度的 20%~80% 之间以避免退化分割。
    未检测到人脸时使用图片水平中心。
    返回 (left, right, split_x)
    """
    W, H = img.size
    if face_rect is not None:
        fx, _, fw, _ = (int(v) for v in face_rect)
        split_x = fx + fw // 2
        split_x = max(int(W * 0.2), min(int(W * 0.8), split_x))
    else:
        split_x = W // 2

    left  = img.crop((0,       0, split_x, H))
    right = img.crop((split_x, 0, W,       H))
    return left, right, split_x


# ── 工作线程 ──────────────────────────────────────────────────────────────────

class CopyrightWorker(QThread):
    """
    信号：
      log_signal(str)           — 实时日志
      progress_signal(int, str) — 进度百分比 + 状态文字
      finished_signal(bool, str)— 完成标志 + 汇总消息
    """

    log_signal      = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(
        self,
        image_paths:        list,
        mode:               str,    # "face_cover" | "lr_split"
        cover_style:        str,    # 遮脸图形类型（仅 face_cover 模式使用）
        circle_color:       tuple,  # RGB (仅 colored_circle 使用)
        output_dir:         str,
        min_confidence:     float = 0.15,  # 人脸检测最低置信度
        face_fallback:      str   = "skip",  # 检测失败时："skip" 跳过 | "use_top" 使用顶部区域
        manual_annotations: dict  = None,  # {path: (x,y,w,h)} 手动标记区域
    ):
        super().__init__()
        self.image_paths        = image_paths
        self.mode               = mode
        self.cover_style        = cover_style
        self.circle_color       = circle_color
        self.output_dir         = output_dir
        self.min_confidence     = min_confidence
        self.face_fallback      = face_fallback
        self.manual_annotations = manual_annotations or {}
        self._stop_event        = threading.Event()

    # ── 控制 ─────────────────────────────────────────────────────────────────

    def stop(self):
        self._stop_event.set()

    def _log(self, msg: str):
        self.log_signal.emit(msg)

    def _progress(self, pct: int, text: str):
        self.progress_signal.emit(pct, text)

    # ── 单张图片处理 ──────────────────────────────────────────────────────────

    def _process_one(self, img_path: str) -> bool:
        """处理单张图片，返回 True 表示成功，False 表示跳过。"""
        try:
            import numpy as np
        except ImportError:
            raise RuntimeError(
                "需要安装 numpy。\n"
                "通常随 mediapipe 或 opencv-python 自动安装，\n"
                "请在「📦 下载必要组件」中安装 mediapipe。"
            )

        stem = Path(img_path).stem
        img  = Image.open(img_path).convert("RGB")
        img_array = np.array(img)

        # ── 优先使用手动标记区域 ──────────────────────────────────────────
        manual = self.manual_annotations.get(img_path)
        if manual:
            face_rect    = manual
            feature_rect = manual   # 手动标记：遮脸和裁剪使用同一区域
            is_manual    = True
            self._log(f"    🎯 使用手动标记区域: {Path(img_path).name}")
        else:
            face_rect, feature_rect = _detect_largest_face(img_array, self.min_confidence)
            is_manual = False

        # ── 人物遮脸模式 ──────────────────────────────────────────────────
        if self.mode == "face_cover":
            if face_rect is None:
                if self.face_fallback == "use_top":
                    # 使用图片顶部 35% 宽 60% 区域作为人脸区域（适合正面肖像）
                    W, H = img.size
                    fh = int(H * 0.35)
                    fw = int(W * 0.60)
                    fx = int((W - fw) / 2)
                    fy = 0
                    face_rect    = (fx, fy, fw, fh)
                    feature_rect = face_rect   # fallback 时同用
                    self._log(f"    ℹ️  未检测到人脸，使用顶部区域: {Path(img_path).name}")
                else:
                    self._log(f"    ⚠️  未检测到人脸，跳过: {Path(img_path).name}")
                    return False

            # 遮脸图：手动标记时直接用标记区域；自动检测时用关键点精准框
            cover_rect = feature_rect if feature_rect else face_rect
            covered = apply_cover(img, cover_rect, self.cover_style, self.circle_color)
            out1 = os.path.join(self.output_dir, f"{stem}_遮脸.jpg")
            covered.save(out1, "JPEG", quality=95)
            self._log(f"    ✅ 遮脸图: {out1}")

            # 大头图：手动标记时直接裁剪（用户已精确框选）；自动检测时向上扩展包含头发
            if is_manual:
                x, y, w, h = (int(v) for v in face_rect)
                portrait = img.crop((max(0, x), max(0, y),
                                     min(img.width, x + w), min(img.height, y + h)))
            else:
                portrait = crop_portrait(img, face_rect)
            out2 = os.path.join(self.output_dir, f"{stem}_大头图.jpg")
            portrait.save(out2, "JPEG", quality=95)
            self._log(f"    ✅ 大头图: {out2}")


        # ── 左右裁剪模式 ──────────────────────────────────────────────────
        else:
            left, right, split_x = split_lr(img, face_rect)
            if face_rect is None:
                self._log(f"    ℹ️  未检测到人脸，居中分割 (x={split_x}): {Path(img_path).name}")
            else:
                self._log(f"    👤 人脸中心 x={split_x}，进行左右分割")

            out_l = os.path.join(self.output_dir, f"{stem}_左.jpg")
            out_r = os.path.join(self.output_dir, f"{stem}_右.jpg")
            left.save(out_l,  "JPEG", quality=95)
            right.save(out_r, "JPEG", quality=95)
            self._log(f"    ✅ 左图: {out_l}")
            self._log(f"    ✅ 右图: {out_r}")

        return True

    # ── 主流程 ────────────────────────────────────────────────────────────────

    def run(self):
        total      = len(self.image_paths)
        ok_count   = 0
        skip_count = 0

        os.makedirs(self.output_dir, exist_ok=True)

        for idx, img_path in enumerate(self.image_paths):
            if self._stop_event.is_set():
                self._log("🛑 已停止任务。")
                break

            pct = int(idx / total * 100)
            name = Path(img_path).name
            self._progress(pct, f"正在处理 {idx + 1}/{total}: {name}")
            self._log(f"\n{'─' * 50}")
            self._log(f"▶ [{idx + 1}/{total}]  {name}")

            try:
                success = self._process_one(img_path)
                if success:
                    ok_count += 1
                else:
                    skip_count += 1
            except RuntimeError as e:
                # 依赖缺失等致命错误，直接终止整个任务
                self._log(f"    ❌ 致命错误: {e}")
                self.finished_signal.emit(False, str(e))
                return
            except Exception as e:
                self._log(f"    ❌ 处理失败: {e}")
                skip_count += 1

        self._progress(100, "全部完成！")
        summary = (
            f"任务结束。✅ 成功 {ok_count} 张 | "
            f"⏭️ 跳过 {skip_count} 张"
        )
        self._log(f"\n{'═' * 50}")
        self._log(f"🎉 {summary}")
        self.finished_signal.emit(ok_count > 0, summary)
