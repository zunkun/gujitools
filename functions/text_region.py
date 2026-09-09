"""
File: functions/text_region.py
文本区域处理基类：YOLO 检测 → area/border 规则 → 输出构建。

crop 和 cropremove 共享相同的检测与裁剪规则，唯一区别是 ROI 处理：
- crop：裁剪原图像素
- cropremove：Otsu 去底色

本基类将公共流程模板化，子类只需实现差异方法：
- `_on_boxes_detected(img_bgr, boxes)`：检测到框后预处理，返回上下文 ctx
- `_process_roi(img_bgr, box, ctx)`：处理单个文本框区域
- `_handle_no_boxes(img_bgr, image_path, area_mode)`：无检测框时的处理
- `_save_output(arr, out_path)`：保存输出图片

ctx 通过参数传递（而非 self 实例变量），保证 ThreadPoolExecutor 并发安全。
"""

from pathlib import Path
import cv2
import numpy as np
import utils
from functions.base import FunctionBase


class TextRegionProcessor(FunctionBase):
    """文本区域处理基类：封装 YOLO 检测 + area/border 规则 + 输出构建。"""

    SYMMETRIC_GAP_MM = 10  # 单框对称输出时，实际框与空白镜像之间的间隔（mm）

    def __init__(self, command_args):
        super().__init__(command_args)
        self._calc_outpath()
        self._model = utils.load_yolo_model()

    def _calc_outpath(self):
        """计算输出目录。"""
        raw_out = self.output_raw
        if raw_out is None or str(raw_out).strip() == "":
            if self.is_file:
                self.outpath = self.parent_path / self.default_temp_name
            else:
                self.outpath = self.input / self.default_temp_name
            return
        file_stem = self.input.stem
        self.outpath = self.parse_user_output(raw_out, file_stem)

    def _process_single_image(self, image_path: Path) -> dict:
        """完整处理流程：读取 → 检测 → area/border 规则 → 输出。"""
        if not utils.is_valid_image_size(image_path):
            return {
                "status": "skipped",
                "file": image_path.name,
                "reason": "file too small",
            }

        img_bgr = cv2.imread(str(image_path))
        if img_bgr is None:
            raise ValueError(f"无法读取图片: {image_path}")

        area_mode = self.command_args.get("area", 1)
        ext = self.command_args.get("ext", "png")

        # YOLO 检测
        left_boxes, right_boxes = utils.detect_left_right_boxes(img_bgr, self._model)
        left_box = left_boxes[0][:4] if left_boxes else None
        right_box = right_boxes[0][:4] if right_boxes else None
        boxes = [b for b in (left_box, right_box) if b is not None]

        # 无检测框
        if not boxes:
            return self._handle_no_boxes(img_bgr, image_path, area_mode)

        # 子类预处理（计算阈值等），返回上下文 ctx
        ctx = self._on_boxes_detected(img_bgr, boxes)

        # 记录原始框数量（在 area=3 合并前判断）
        single_box_detected = len(boxes) == 1

        # area=3 合并
        if area_mode == 3 and left_box and right_box:
            lx1, ly1, lx2, ly2 = left_box
            rx1, ry1, rx2, ry2 = right_box
            cx1 = min(lx1, rx1)
            cy1 = min(ly1, ry1)
            cx2 = max(lx2, rx2)
            cy2 = max(ly2, ry2)
            boxes = [(cx1, cy1, cx2, cy2)]

        # border 参数
        border_mm = self.command_args.get("border")
        border_padding = utils.parse_border_mm(border_mm, dpi=300)

        # 特殊处理：area=2/3 + border有值 + 仅一个文本框 → 对称输出
        # 实际框 + border 组成一半，另一边为空白镜像，中间间隔 SYMMETRIC_GAP_MM
        if single_box_detected and border_padding is not None and area_mode in (2, 3):
            is_left = left_box is not None
            actual_box = left_box if is_left else right_box
            final_arr = self._build_symmetric_output(
                img_bgr, actual_box, border_padding, ctx, is_left
            )
            out_path = self.outpath / f"{image_path.stem}.{ext}"
            self._save_output(final_arr, out_path)
            return {
                "status": "success",
                "file": image_path.name,
                "outputs": [str(out_path)],
            }

        # area=1：逐框裁剪输出（-l/-r）
        if area_mode == 1:
            if border_padding is None:
                border_padding = [0, 0, 0, 0]
            outputs = []
            for box, suffix in ((left_box, "-l"), (right_box, "-r")):
                if box is None:
                    continue
                final_arr = self._build_output(img_bgr, [box], border_padding, ctx)
                out_path = self.outpath / f"{image_path.stem}{suffix}.{ext}"
                self._save_output(final_arr, out_path)
                outputs.append(str(out_path))
            return {"status": "success", "file": image_path.name, "outputs": outputs}

        # area=2/3：单图输出
        final_arr = self._build_output(img_bgr, boxes, border_padding, ctx)
        out_path = self.outpath / f"{image_path.stem}.{ext}"
        self._save_output(final_arr, out_path)
        return {
            "status": "success",
            "file": image_path.name,
            "outputs": [str(out_path)],
        }

    def _build_output(self, img_bgr, boxes, border_padding, ctx):
        """构建输出图像：框内为处理后像素，框外白色。

        - border_padding=None → 原图尺寸
        - border_padding=[t,r,b,l] → 裁剪到联合外边界 + 边距
        """
        H, W = img_bgr.shape[:2]

        all_x1 = min(b[0] for b in boxes)
        all_y1 = min(b[1] for b in boxes)
        all_x2 = max(b[2] for b in boxes)
        all_y2 = max(b[3] for b in boxes)

        if border_padding is None:
            out_arr = self._new_blank(H, W)
            for x1, y1, x2, y2 in boxes:
                roi = self._process_roi(img_bgr, (x1, y1, x2, y2), ctx)
                self._paste(out_arr, roi, x1, y1)
            return out_arr

        top, right, bottom, left = border_padding
        new_h = (all_y2 - all_y1) + top + bottom
        new_w = (all_x2 - all_x1) + left + right

        out_arr = self._new_blank(new_h, new_w)
        for x1, y1, x2, y2 in boxes:
            roi = self._process_roi(img_bgr, (x1, y1, x2, y2), ctx)
            ox = x1 - all_x1 + left
            oy = y1 - all_y1 + top
            self._paste(out_arr, roi, ox, oy)
        return out_arr

    def _build_symmetric_output(self, img_bgr, box, border_padding, ctx, is_left):
        """单框对称输出：检测到的框 + border 组成一半，另一边为空白镜像，中间有间隔。

        布局（is_left=True 时实际框在左，is_left=False 时在右）：

            +----------- top -----------+
            | left | box | gap | blank | right
            +--------- bottom ---------+

        - 实际框（box）经 _process_roi 处理后粘贴到对应半边
        - 另一半为空白（由 _new_blank 初始化为白色）
        - gap = SYMMETRIC_GAP_MM 按 300 DPI 换算为像素
        """
        x1, y1, x2, y2 = box
        top, right, bottom, left = border_padding

        gap_px = round(self.SYMMETRIC_GAP_MM * 300 / 25.4)
        box_w = x2 - x1
        box_h = y2 - y1

        new_h = top + box_h + bottom
        new_w = left + box_w + gap_px + box_w + right

        out_arr = self._new_blank(new_h, new_w)
        roi = self._process_roi(img_bgr, (x1, y1, x2, y2), ctx)

        if is_left:
            ox = left
        else:
            ox = left + box_w + gap_px
        oy = top
        self._paste(out_arr, roi, ox, oy)
        return out_arr

    def _new_blank(self, h, w):
        """创建空白输出数组（白色）。子类可重写返回灰度。"""
        return np.full((h, w, 3), 255, dtype=np.uint8)

    def _paste(self, out_arr, roi, ox, oy):
        """将 roi 粘贴到 out_arr 的 (ox, oy) 位置，自动处理通道差异。"""
        h, w = roi.shape[:2]
        if out_arr.ndim == 3 and roi.ndim == 2:
            out_arr[oy : oy + h, ox : ox + w] = np.stack([roi] * 3, axis=-1)
        else:
            out_arr[oy : oy + h, ox : ox + w] = roi

    # ---- 子类必须实现 ----
    def _on_boxes_detected(self, img_bgr, boxes):
        """检测到框后的预处理 hook。返回上下文 ctx（供 _process_roi 使用）。默认返回 None。"""
        return None

    def _process_roi(self, img_bgr, box, ctx):
        """处理单个文本框区域，返回像素数组。"""
        raise NotImplementedError

    def _handle_no_boxes(self, img_bgr, image_path, area_mode):
        """无检测框时的处理。"""
        raise NotImplementedError

    def _save_output(self, arr, out_path):
        """保存输出图片。"""
        raise NotImplementedError

    def execute(self):
        return super().execute()
