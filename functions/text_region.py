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

**几何规则来源**：area/border 的画布尺寸与粘贴落点由
`utils.box_geometry.build_output_layout` / `build_symmetric_layout` 统一计算
（与 desktop 侧预览共用同一份规则）。本模块只负责用 numpy 把布局"画"出来，
不再自行推导几何。
"""

from pathlib import Path
import time

import numpy as np
import utils
from functions.base import FunctionBase
from functions.detect import detect_page_boxes_by_path, warm_up_detect_model
from utils.box_geometry import build_output_layout, build_symmetric_layout


class TextRegionProcessor(FunctionBase):
    """文本区域处理基类：封装 YOLO 检测 + area/border 规则 + 输出构建。"""

    def __init__(self, command_args, reporter=None):
        """计算输出目录；YOLO 模型**延迟**到真正需要检测时才加载。

        area=4「整页」模式下完全不检测，模型也就不会被加载——这既省掉了
        非古籍文档白白等模型初始化，也让「没有 YOLO 权重」的环境仍能跑整页流程。

        检测本身走 `detect_page_boxes_by_path`：优先交给**常驻 YOLO 服务**
        （模型全局只加载一次、多进程共用），服务不可用时它自己在本进程内
        加载单例。因此本对象不持有模型。
        """
        super().__init__(command_args, reporter)
        self._calc_outpath()

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

        # 走 utils.imread（np.fromfile + imdecode）：cv2.imread 遇中文路径返回 None
        img_bgr = utils.imread(image_path)
        if img_bgr is None:
            raise ValueError(f"无法读取图片: {image_path}")

        area_mode = self.command_args.get("area", 1)
        ext = self.command_args.get("ext", "png")
        # 整页模式不检测，耗时无意义；只有真正跑了 YOLO 的那条路才有值
        detect_elapsed = None

        if area_mode == 4:
            # 整页模式：不调用 YOLO，整页即唯一文本框（普通文档 / 检测失败兜底）
            h, w = img_bgr.shape[:2]
            left_box, right_box = (0, 0, w, h), None
        else:
            # YOLO 检测：唯一入口在 functions.detect，保证 crop / cropremove /
            # GUI detect 阶段拿到的框完全一致（此前三处各自调 utils 原语）。
            # ⚠️ 走**按路径**的入口：检测优先交给常驻 YOLO 服务（服务自己读图），
            # 模型全局只加载一次；服务不可用时它内部回落到本进程内加载。
            detect_started = time.perf_counter()
            left_box, right_box = detect_page_boxes_by_path(image_path)
            detect_elapsed = time.perf_counter() - detect_started
        boxes = [b for b in (left_box, right_box) if b is not None]
        self._report_boxes(image_path, left_box, right_box, detect_elapsed)

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

        # border 参数：没给（None/空）时按 area 取默认——area=1/2/3 → "0"
        # （不加留白，第四步会在 A4 上重新排版），area=4（整页）→ None。
        # 规则只有一份，见 core.command_spec.effective_border_default。
        from core.command_spec import effective_border_default

        border_mm = self.command_args.get("border")
        if border_mm is None or not str(border_mm).strip():
            border_mm = effective_border_default(area_mode)
        border_padding = utils.parse_border_mm(border_mm, dpi=300)

        # 特殊处理：area=2/3 + border有值 + 仅一个文本框 → 对称输出
        # 实际框 + border 组成一半，另一边为空白镜像，中间间隔
        # utils.box_geometry.SYMMETRIC_GAP_MM（10mm）
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

        几何（画布尺寸与粘贴落点）来自 utils.box_geometry.build_output_layout，
        与 desktop 侧预览共用同一份规则；此处只负责 numpy 渲染。

        传入的 boxes 已经是「最终参与布局的框」：caller 在 area=3 时已把
        左右框合并为一个并集框。symmetry=False —— 对称输出只由
        `_build_symmetric_output` 负责，本方法不做镜像。
        """
        H, W = img_bgr.shape[:2]
        layout = build_output_layout(
            boxes=boxes,
            area=2,
            border_padding=border_padding,
            image_size=(W, H),
            symmetric=False,
        )
        return self._render_layout(img_bgr, layout, ctx)

    def _build_symmetric_output(self, img_bgr, box, border_padding, ctx, is_left):
        """单框对称输出：检测到的框 + border 组成一半，另一边为空白镜像，中间有间隔。

        布局（is_left=True 时实际框在左，is_left=False 时在右）：

            +----------- top -----------+
            | left | box | gap | blank | right
            +--------- bottom ---------+

        - 实际框（box）经 _process_roi 处理后粘贴到对应半边
        - 另一半为空白（由 _new_blank 初始化为白色）
        - 几何来自 utils.box_geometry.build_symmetric_layout（与 desktop 共用）
        """
        H, W = img_bgr.shape[:2]
        layout = build_symmetric_layout(
            box=box,
            border_padding=border_padding,
            image_size=(W, H),
            is_left=is_left,
        )
        return self._render_layout(img_bgr, layout, ctx)

    def _render_layout(self, img_bgr, layout, ctx):
        """把几何布局渲染为 numpy 图像（单画布）。

        布局可能含多个落点（如 area=2 双框无 border 时两框写回同一整页画布），
        全部按各自坐标粘贴到同一张输出数组上。
        """
        canvas = layout.canvases[0]
        out_arr = self._new_blank(canvas.size[1], canvas.size[0])
        for source, ox, oy in canvas.sources:
            roi = self._process_roi(img_bgr, tuple(source), ctx)
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
    def _report_boxes(self, image_path, left_box, right_box, elapsed=None) -> None:
        """汇报本图检测到的左右框。

        主通道是结构化事件 `page_boxes`（GUI 据此把框写回 boxes.json）；
        `[boxes]` 文本行仅为**兼容保留**——后续可从 stderr 观察：
        若桌面端日志中不再出现该行且框入库正常，即可安全删除。
        """
        # 结构化通道：坐标原样传递，不做字符串往返（避免 int(float(str)) 的精度绕路）
        self.reporter.event(
            "page_boxes",
            image=image_path.stem,
            left=None if left_box is None else [int(round(float(v))) for v in left_box[:4]],
            right=None if right_box is None else [int(round(float(v))) for v in right_box[:4]],
        )

        def fmt(box):
            if box is None:
                return "none"
            return ",".join(str(int(round(float(v)))) for v in box[:4])

        # ⚠️ 只在行尾追加耗时，**不要改动行内既有字段**：
        # `tests/reporter_cli_parity.py` 会按 `left=<nums>` 子串比对两通道同源。
        cost = "" if elapsed is None else f" cost={elapsed * 1000:.0f}ms"
        print(
            f"[boxes] {image_path.stem} left={fmt(left_box)} "
            f"right={fmt(right_box)}{cost}"
        )

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
        """执行文本区域处理：委托基类并发引擎逐图处理。

        复用 FunctionBase.execute() 的线程池、重试与日志；单图完整流程
        （读取→YOLO 检测→area/border 规则→输出）在 _process_single_image 中。

        ⚠️ 在进入并发引擎**之前**先把模型备好（`warm_up_detect_model`）：
        area=4 整页模式完全不用 YOLO，故先判断再预热，避免白加载；非整页时
        这笔开销被单独计时、单独报出，不会压在"第一张图"的耗时上。
        """
        # ⚠️ 先看有没有输入，再决定要不要加载模型（2026-09-26 审计）：空目录时
        #    以前会先花 ~5s / ~350MB 把 YOLO 拉起来（desktop 侧还会顺带拉起常驻
        #    服务），然后才报「未找到图片」——白付一次模型加载。
        #    这里直接交给 super()：它自己会抛统一的那条 FileNotFoundError。
        if not self._collect_input_files():
            return super().execute()
        if int(self.command_args.get("area", 1) or 1) != 4:
            load_line, _seconds = warm_up_detect_model()
            print(load_line)
        return super().execute()
