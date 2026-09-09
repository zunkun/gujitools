"""
File: functions/crop.py
裁剪功能：基于 YOLO 检测定位文本框并裁剪原图像素。

与 cropremove 共享 area/border 规则（继承 TextRegionProcessor），
但不做 Otsu 去底色，仅裁剪原始图像像素。
"""

import cv2
from PIL import Image
from functions.text_region import TextRegionProcessor
from pathlib import Path
from utils.path_utils import resolve_final_output_dir


class CropFunction(TextRegionProcessor):
    """裁剪功能：输出原始彩色像素。"""

    def __init__(self, *args, output_suffix: str = ".png", **kwargs):
        super().__init__(*args, **kwargs)
        # 全局输出后缀，统一小写
        self.output_suffix = output_suffix.lower()
        # 重新计算输出路径（覆盖父类可能已有的计算）
        self._calc_outpath()

    def _calc_outpath(self):
        """根据输入和 --output 计算最终的输出目录。"""
        self.outpath = resolve_final_output_dir(
            self.input,
            self.output_raw,
            self.is_file,
            self.default_temp_name,
        )
        print(f"输出目录：{self.outpath}")

    def _process_roi(self, img_bgr, box, ctx):
        """裁剪框内原图像素（不做去底色）。ctx 在 crop 中不使用。"""
        x1, y1, x2, y2 = box
        return img_bgr[y1:y2, x1:x2]

    def _handle_no_boxes(self, img_bgr, image_path, area_mode):
        """无检测框：输出原图，使用配置的输出后缀"""
        out_path = self.outpath / f"{image_path.stem}{self.output_suffix}"
        self._save_output(img_bgr, out_path)
        return {
            "status": "no_detect",
            "file": image_path.name,
            "outputs": [str(out_path)],
        }

    def _save_output(self, arr, out_path):
        """保存图片，自动识别后缀，修复PIL格式映射问题，自动创建目录"""
        out_path = Path(out_path)
        # 自动创建输出目录（解决文件夹不存在报错）
        out_path.parent.mkdir(parents=True, exist_ok=True)

        rgb_arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb_arr, "RGB")

        suffix = out_path.suffix.lstrip(".").upper()
        # ========== 关键修复：PIL格式名称映射表 ==========
        fmt_map = {"PNG": "PNG", "JPG": "JPEG", "JPEG": "JPEG", "WEBP": "WEBP"}
        # 不存在则默认 PNG
        fmt = fmt_map.get(suffix, "PNG")

        save_kwargs = {"dpi": (300, 300), "format": fmt}
        if fmt == "PNG":
            save_kwargs.update({"optimize": True, "compress_level": 9})
        elif fmt == "JPEG":
            save_kwargs.update({"quality": 95, "optimize": True})
        elif fmt == "WEBP":
            save_kwargs.update({"quality": 90})

        print(f"Saving output: {out_path} (format={fmt})")
        img.save(out_path, **save_kwargs)
