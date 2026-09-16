"""
File: functions/detect.py
检测功能：在整页图片中检测左右两个文本框。

这是「检测」这一步的唯一实现——`crop = detect + 裁剪`、`cropremove =
detect + 裁剪 + 去底色`，两者都通过本模块拿到左右框，而不是各自调用
`utils.detect_left_right_boxes`。GUI 的 detect 阶段同样复用这里，因此
「CLI 与 desktop 用同一套算法、只是参数不同」在检测这一步也成立。

与其它功能类的区别：
- **`save` 决定是否落盘**。不带 `--save` 时 `self.outpath = None`，不计算路径、
  不创建目录、不写任何文件，只上报坐标——此时它纯粹是 `crop` / `cropremove`
  的前置中间步骤，供代码调用或 GUI 的 detect 阶段使用。
- **命令行下必须给 `--save`**：不落盘时命令行没有任何产出去处（坐标只打到
  stdout，下游 `crop` / `cropremove` 各自会重新检测），属于白算一趟，因此
  CLI 入口会直接拒绝（`cli.cli._reject_dry_run`）。本模块**不**做这个限制——
  它是可复用的库层，`DetectFunction` 作为中间步骤被代码调用时必须保持可用。
- **落地时**输出标注图（框 + 坐标文字），输出目录规则与 `crop`
  **完全一致**（都调 `utils.path_utils.resolve_final_output_dir`）：
  `<输入父目录>/detect`，即与 crop 同级、落在输入目录旁边。
- **`execute()` 被重写**：基类语义是「建目录 → 处理 → 落盘 → 统计」，
  对不落盘的检测无意义。
"""

import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple

import utils
from functions.base import FunctionBase
from utils.path_utils import resolve_final_output_dir

# 一个检测框 = (x1, y1, x2, y2) 像素坐标
Box = Tuple[int, int, int, int]


def extract_first_box(boxes) -> Optional[Box]:
    """从 `detect_left_right_boxes` 的返回里取面积最大的框的 4 个坐标。

    `detect_left_right_boxes` 返回 ``[(x1, y1, x2, y2, area), ...]``，
    已按面积降序排列，故取 ``[0]`` 即最大候选框。统一在此处裁剪到前 4 个
    元素——此前 CLI 与 GUI 各自写了一遍
    ``left_boxes[0][:4] if left_boxes else None``。

    参数:
        boxes: 单侧框列表，可为空。

    返回:
        (x1, y1, x2, y2)，或 None（该侧无框）。
    """
    if not boxes:
        return None
    return tuple(int(v) for v in boxes[0][:4])


def detect_page_boxes(
    img_bgr, model=None
) -> Tuple[Optional[Box], Optional[Box]]:
    """检测一页图片的左右文本框，返回 (left_box, right_box)。

    这是检测算法的**唯一入口**：crop / cropremove / GUI detect 阶段都调用
    它，保证三处的框完全相同。

    参数:
        img_bgr: BGR 图像数组（由 `utils.imread` 读取，支持中文路径）。
        model: YOLO 模型实例；None 时使用进程内单例。

    返回:
        (left_box, right_box)，各为 (x1, y1, x2, y2) 或 None。
    """
    if model is None:
        model = utils.load_yolo_model()
    left_boxes, right_boxes = utils.detect_left_right_boxes(img_bgr, model)
    return extract_first_box(left_boxes), extract_first_box(right_boxes)


class DetectFunction(FunctionBase):
    """检测功能：逐图检测左右文本框并上报坐标。

    是否落盘由 `save` 决定：关闭时**不生成任何文件**（供代码调用 /
    GUI detect 阶段当中间步骤），开启时把标注图（框 + 坐标文字）落地，
    视觉与 GUI 的 detect 预览一致。

    注意：命令行下「不带 `--save`」会被 CLI 入口拒绝，但那是入口层的
    取舍，与本类无关——本类保持可复用，不在此处设限。
    """

    def __init__(self, command_args, reporter=None):
        """初始化并加载 YOLO 模型（单例，进程内复用）。

        `save`（默认关闭）决定是否把标注图落地，落地目录同 crop 的
        输出规则（`-o` 或默认 `detect` 目录），仅在开启时才创建。
        """
        super().__init__(command_args, reporter)
        self._model = utils.load_yolo_model()
        self.save = bool(command_args.get("save", False))
        # 标注图后缀，与 crop 的 ext 语义一致（png 无损，适合线框标注）
        self.output_suffix = "." + str(command_args.get("ext") or "png").lower().lstrip(".")
        # 落地时才计算输出目录：关闭时不产生目录、也不打印「输出目录」。
        # 这是库层的中立行为（代码调用 / GUI 都需要），
        # 命令行「不落盘就拒绝」由 cli.cli._reject_dry_run 负责。
        self.outpath = self._resolve_outpath() if self.save else None

    def _resolve_outpath(self) -> Path:
        """按 `utils.path_utils.resolve_final_output_dir` 计算标注图输出目录。

        与 `crop` / `rembg` / `cropremove` **调用同一个函数**，因此目录规则
        完全一致——detect 与 crop 是同级步骤，输出都落在输入目录的**旁边**
        （`<输入父目录>/detect`），而不是嵌进输入目录里。

        例：输入 `.../test/a/images` → 输出 `.../test/a/detect`（与 images 并列）。

        仅在 `--save` 时才会被调用；不落盘时不计算路径，也不创建目录。
        """
        return resolve_final_output_dir(
            self.input,
            self.output_raw,
            self.is_file,
            self.default_temp_name,
        )

    def _process_single_image(self, image_path: Path) -> dict:
        """检测单图并上报框；仅在 `--save` 时把标注图落地。"""
        img_bgr = utils.imread(image_path)
        if img_bgr is None:
            raise ValueError(f"无法读取图片: {image_path}")

        left_box, right_box = detect_page_boxes(img_bgr, self._model)
        self._report_boxes(image_path, left_box, right_box)

        result = {
            "status": "success" if (left_box or right_box) else "no_detect",
            "file": image_path.name,
            "left": left_box,
            "right": right_box,
            "outputs": [],
        }
        if self.save:
            result["outputs"] = self._save_annotated(image_path, img_bgr, left_box, right_box)
        return result

    def _save_annotated(self, image_path, img_bgr, left_box, right_box):
        """把左右框画到图上并落地，返回写出的路径列表。

        只画**真正检测到的框**（None 项被 draw_boxes 跳过），因此
        「只检出左框」时不会画出错误的右框位置——与 GUI 预览一致。
        """
        annotated = utils.draw_boxes(img_bgr, [left_box, right_box])
        out_path = self.outpath / f"{image_path.stem}{self.output_suffix}"
        if not utils.imwrite(out_path, annotated):
            raise OSError(f"标注图写出失败: {out_path}")
        return [str(out_path)]

    def _report_boxes(self, image_path: Path, left_box, right_box) -> None:
        """经 reporter 上报本页检测框（结构化事件 + 一行人读日志）。

        事件名与 `functions/text_region.py` 完全一致（`page_boxes`），
        因此 desktop 侧对 detect 阶段与 crop 阶段看到的是同一种事件。
        """
        self.reporter.event(
            "page_boxes",
            image=image_path.stem,
            left=list(left_box) if left_box else None,
            right=list(right_box) if right_box else None,
        )
        self.reporter.log(
            f"检测完成: {image_path.name} "
            f"左={_fmt_box(left_box)} 右={_fmt_box(right_box)}"
        )

    def execute(self) -> dict:
        """逐图检测，返回汇总结果。

        **默认不写任何文件**；`--save` 开启时把标注图落地到 `outpath`。

        为什么重写：`FunctionBase.execute` 的语义是「建输出目录 → 处理 →
        落盘 → 统计写出数量」，而检测默认没有产出，也不该凭空创建输出
        目录。这里保留**相同的并发与进度汇报行为**（含失败重试），只在
        `--save` 时才做落盘相关的准备。

        返回:
            {"processed": n, "left": n, "right": n, "output": 目录或 None}
        """
        print(f"输入路径：{self.input}")
        if self.save:
            print(f"输出目录：{self.outpath}")

        image_files = self._collect_input_files()
        total = len(image_files)
        # 0/0 是明确信号：GUI 据此把进度条归零，而不是停在上一轮的残值
        self.reporter.event("progress_total", total=total)
        if not image_files:
            print("未找到图片文件")
            self.reporter.progress(0, 0)
            return {
                "processed": 0, "left": 0, "right": 0,
                "output": str(self.outpath) if self.save else None,
            }

        if self.save:
            clean = self.command_args.get("clean", False)
            if clean and self.outpath.exists():
                shutil.rmtree(self.outpath)
            self.outpath.mkdir(parents=True, exist_ok=True)

        print(f"图片总数: {total}")

        workers = max(
            1, int(self.command_args.get("workers", max(1, min(8, total))))
        )
        max_retries = 2
        results_by_file: dict = {}
        finished = 0

        def _run_round(current_files):
            """对一轮文件集合并行检测，返回每文件的结果。"""
            nonlocal finished
            round_results = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_map = {
                    executor.submit(self._process_single_image, p): p
                    for p in current_files
                }
                for future in as_completed(future_map):
                    path = future_map[future]
                    try:
                        result = future.result()
                        round_results.append(result)
                        print(f"检测完成: {path.name} -> {result['status']}")
                    except Exception as exc:
                        print(f"检测失败: {path.name} -> {exc}")
                        round_results.append(
                            {"status": "error", "file": path.name, "reason": str(exc)}
                        )
                    # 完成数可能因重试超过总数，上限截断到 total
                    finished += 1
                    self.reporter.progress(min(finished, total), total)
            return round_results

        pending_files = list(image_files)
        for attempt in range(1, max_retries + 2):
            if not pending_files:
                break
            round_results = _run_round(pending_files)
            next_pending = []
            for item in round_results:
                if item.get("status") == "error" and attempt <= max_retries:
                    origin = (
                        self.input / item["file"] if not self.is_file else self.input
                    )
                    if origin.exists():
                        next_pending.append(origin)
                        continue
                results_by_file[item["file"]] = item
            pending_files = next_pending

        results = [results_by_file[f] for f in sorted(results_by_file)]
        hit = [r for r in results if r.get("status") == "success"]
        hit_left = sum(1 for r in hit if r.get("left"))
        hit_right = sum(1 for r in hit if r.get("right"))
        failed = sum(1 for r in results if r.get("status") == "error")
        print(
            f"检测完成: 共 {total} 页，左框 {hit_left} 页，"
            f"右框 {hit_right} 页，失败 {failed} 页"
        )
        if self.save:
            saved = sum(len(r.get("outputs") or []) for r in results)
            print(f"标注图已保存: {saved} 张 -> {self.outpath}")
        return {
            "processed": total,
            "left": hit_left,
            "right": hit_right,
            "output": str(self.outpath) if self.save else None,
        }


def _fmt_box(box) -> str:
    """把框格式化为 `x1,y1,x2,y2`，None 显示为 `-`。"""
    return "-" if box is None else ",".join(str(int(v)) for v in box)
