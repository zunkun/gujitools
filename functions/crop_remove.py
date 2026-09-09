"""
File: functions/crop_remove.py
复合流程：裁剪（基于检测）+ 去底色（Otsu / 红色印章保留）。

与 crop 共享 area/border 规则（继承 TextRegionProcessor），
区别是 ROI 做 Otsu 二值化去底色，并支持印章保留。

- `area` 控制裁剪区域与输出方式（详见 TextRegionProcessor）；
- `border` 控制空白边界（详见 TextRegionProcessor）；
- 额外参数：offset / type / seal / sealcolor / sealarea / sealmin_sat。

线程安全说明：每张图的 img_rgb / gray / threshold / red_mask 通过
`_on_boxes_detected` 返回的 ctx 字典传递，绝不写入 self 实例变量，
从而可被 ThreadPoolExecutor 并发调用而不串扰。
"""

import cv2
import numpy as np
from PIL import Image
import utils
from functions.text_region import TextRegionProcessor
from utils import resolve_final_output_dir  # 新增导入


class CropRemoveFunction(TextRegionProcessor):
    """裁剪 + Otsu 去底色。"""

    def __init__(self, command_args):
        super().__init__(command_args)
        self.default_temp_name = "rembg"
        # 这些是命令级常量，线程间共享只读，安全
        self._offset = command_args.get("offset", 0)
        self._img_type = command_args.get("type", 1)
        self._enable_seal = command_args.get("seal", False)
        self._seal_color = command_args.get("sealcolor", False)
        self._seal_area = command_args.get("sealarea", 80)
        self._seal_min_sat = command_args.get("sealmin_sat", 50)
        # 重新计算输出路径（覆盖父类可能已有的计算）
        self._calc_outpath()

    def _calc_outpath(self):
        """计算输出目录。

        使用统一的路径解析规则：
        - 未指定 --output：输出目录 = 输入路径的父目录 / default_temp_name（与输入并列）；
        - 指定简单名称（如 "out"）：输出目录 = 输入路径的父目录 / 名称 / default_temp_name；
        - 指定绝对/相对路径：输出目录 = 解析后的路径 / default_temp_name。

        这样确保目录输入时，输出与输入目录并列，符合用户预期。
        """
        self.outpath = resolve_final_output_dir(
            self.input,
            self.output_raw,
            self.is_file,
            self.default_temp_name,
        )
        print(f"输出目录：{self.outpath}")

    def _on_boxes_detected(self, img_bgr, boxes):
        """检测到框后：计算灰度图、印章掩码、联合 Otsu 阈值。

        返回 ctx 字典（线程安全：状态通过参数传递，不写入 self）。
        """
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        red_mask = None
        if self._enable_seal:
            red_mask, _ = utils.extract_red_seal(
                img_rgb, self._seal_area, self._seal_min_sat
            )

        # 联合阈值：左右框像素合并计算（符合 project_memory 约定）
        all_pixels = []
        for x1, y1, x2, y2 in boxes:
            roi = gray[y1:y2, x1:x2]
            if roi.size > 0:
                all_pixels.append(roi.ravel())
        if all_pixels:
            threshold = (
                utils.calculate_auto_threshold(np.concatenate(all_pixels))
                + self._offset
            )
        else:
            threshold = 128
        threshold = min(max(threshold, 30), 240)

        return {
            "img_rgb": img_rgb,
            "gray": gray,
            "threshold": threshold,
            "red_mask": red_mask,
        }

    def _process_roi(self, img_bgr, box, ctx):
        """对单个文本框区域应用 Otsu 去底色。"""
        return utils.apply_otsu_to_region(
            ctx["img_rgb"],
            ctx["gray"],
            box,
            ctx["threshold"],
            self._enable_seal,
            self._seal_color,
            ctx["red_mask"],
            self._img_type,
        )

    def _handle_no_boxes(self, img_bgr, image_path, area_mode):
        """无检测框：area=1 输出原图；area=2/3 整图 Otsu。"""
        if area_mode == 1:
            # 修复：img_bgr 是 BGR，_save_output 假定 RGB，需先转换
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            out_path = self.outpath / f"{image_path.stem}.png"
            self._save_output(img_rgb, out_path)
            return {
                "status": "no_detect",
                "file": image_path.name,
                "outputs": [str(out_path)],
            }

        # area=2/3：整图 Otsu（状态局部计算，不写 self）
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        red_mask = None
        if self._enable_seal:
            red_mask, _ = utils.extract_red_seal(
                img_rgb, self._seal_area, self._seal_min_sat
            )

        non_white = gray < 250
        if np.count_nonzero(non_white) > 500:
            threshold = utils.calculate_auto_threshold(gray[non_white]) + self._offset
        else:
            threshold = 128
        threshold = min(max(threshold, 30), 240)

        final_arr = utils.apply_otsu_whole(
            img_rgb, gray, threshold, red_mask, self._seal_color, self._img_type
        )
        out_path = self.outpath / f"{image_path.stem}.png"
        self._save_output(final_arr, out_path)
        return {
            "status": "whole_otsu",
            "file": image_path.name,
            "outputs": [str(out_path)],
        }

    def _new_blank(self, h, w):
        """seal_color → RGB 白色；否则 → 灰度白色。"""
        if self._enable_seal and self._seal_color:
            return np.full((h, w, 3), 255, dtype=np.uint8)
        return np.full((h, w), 255, dtype=np.uint8)

    def _save_output(self, arr, out_path):
        """按 img_type 保存（1=8bit二值, 2=1bit单色, 3=8bit灰度）。"""
        if arr.ndim == 3:
            Image.fromarray(arr, "RGB").save(
                out_path, format="PNG", optimize=True, compress_level=9, dpi=(300, 300)
            )
        else:
            img = Image.fromarray(arr, "L")
            if self._img_type == 2:
                img = img.convert("1")
            img.save(
                out_path, format="PNG", optimize=True, compress_level=9, dpi=(300, 300)
            )
