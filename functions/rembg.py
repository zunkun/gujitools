"""
File: functions/rembg.py
去底色功能：对单张图片执行整图 Otsu 二值化/灰度化/彩色保留印章。

此功能对应 `guji rembg` 命令，处理流程：

1. **图片加载与标准化**
   - 读取图片并统一为 RGB 模式；
   - RGBA 透明图与白底合并（避免 alpha 通道影响阈值计算）。

2. **印章检测**（可选，`--seal` 开关）
   - 基于 HSV 色域双区间提取红色掩码；
   - 连通域过滤噪声（面积/纵横比/填充率三重判定）。

3. **阈值计算**
   - 取非白像素（gray < 250）作为输入，调用 `calculate_auto_threshold` 计算 Otsu 阈值；
   - 叠加 `offset` 偏移量，并限制在 [30, 240] 范围内；
   - 非白像素不足 500 时退化为固定阈值 128。

4. **去底处理**
   - 调用 `apply_otsu_whole` 生成白底黑字输出；
   - 支持 3 种输出类型：二值(type=1)、1bit(type=2)、灰度(type=3)；
   - `--sealcolor` 开关下输出彩色图，保留红色印章原色。

5. **保存为 PNG**（300 DPI，optimize+compress_level=9）
"""

from pathlib import Path
import numpy as np
from PIL import Image
import utils
from functions.base import FunctionBase
from utils import resolve_final_output_dir  # 新增导入


class RembgFunction(FunctionBase):
    """去底色功能实现类。

    继承 FunctionBase 的并发执行引擎，只需实现 `_process_single_image`。
    """

    def __init__(self, command_args):
        super().__init__(command_args)
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

    def _process_single_image(self, image_path: Path) -> dict:
        """处理单张图片：加载 → 印章检测 → 阈值计算 → 去底 → 保存。

        参数:
            image_path: 图片文件路径。

        返回:
            {"status": "success/skipped", "file": filename, "output": path}
        """
        # 过滤异常小文件（下载不完整或占位符）
        if not utils.is_valid_image_size(image_path):
            return {
                "status": "skipped",
                "file": image_path.name,
                "reason": "file too small",
            }

        with Image.open(image_path) as img:
            img.load()

            # 统一为 RGB：RGBA 与白底合并，其他模式直接转换
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])  # alpha 通道作为 mask 合成到白底
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")

            img_arr = np.array(img)
            gray_arr = np.array(img.convert("L"))

            # 获取命令行参数
            enable_seal = self.command_args.get("seal", False)
            seal_area = self.command_args.get("sealarea", 80)
            seal_min_sat = self.command_args.get("sealmin_sat", 50)
            seal_color = self.command_args.get("sealcolor", False)
            offset = self.command_args.get("offset", 0)
            img_type = self.command_args.get("type", 1)

            # 红色印章掩码提取（可选）
            red_mask = None
            if enable_seal:
                red_mask, _ = utils.extract_red_seal(img_arr, seal_area, seal_min_sat)

            # 阈值计算：取非白像素子集计算 Otsu，叠加 offset
            # 非白像素不足 500 时退化为 128（近似空白页）
            non_white = gray_arr < 250
            if np.count_nonzero(non_white) > 500:
                threshold = utils.calculate_auto_threshold(gray_arr[non_white]) + offset
            else:
                threshold = 128
            # 限制阈值范围，避免极端值导致全黑或全白
            threshold = min(max(threshold, 30), 240)

            # 执行整图去底，生成输出数组
            final_arr = utils.apply_otsu_whole(
                img_arr, gray_arr, threshold, red_mask, seal_color, img_type
            )

            # 保存为 PNG（300 DPI）
            out_path = self.outpath / f"{image_path.stem}.png"
            if final_arr.ndim == 3:
                # 彩色输出（印章原色保留）
                Image.fromarray(final_arr, "RGB").save(
                    out_path,
                    format="PNG",
                    optimize=True,
                    compress_level=9,
                    dpi=(300, 300),
                )
            else:
                # 单通道输出（灰度或二值）
                img_out = Image.fromarray(final_arr, "L")
                if img_type == 2:
                    img_out = img_out.convert("1")  # 8bit → 1bit 单色位图
                img_out.save(
                    out_path,
                    format="PNG",
                    optimize=True,
                    compress_level=9,
                    dpi=(300, 300),
                )

            return {
                "status": "success",
                "file": image_path.name,
                "output": str(out_path),
            }

    def execute(self):
        return super().execute()
