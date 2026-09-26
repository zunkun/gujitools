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

    def __init__(self, command_args, reporter=None):
        """初始化并推导去底色输出目录。

        先调用基类解析输入/输出路径，再经 _calc_outpath 计算 self.outpath
        （规则见 _calc_outpath：未指定 --output 时与输入并列，否则按用户输出解析）。
        """
        super().__init__(command_args, reporter)
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

        # ⚠️ with 的目标取名 source、工作图取名 img：非 RGB 输入时
        # `img = source.convert("RGB")` 会换成新对象，而 with 的上下文管理器
        # **仍然持有原图**——不显式关掉，整张原图（68MB）就会活到块结束。
        with Image.open(image_path) as source:
            source.load()

            # 统一为 RGB：RGBA 与白底合并，其他模式直接转换
            if source.mode == "RGBA":
                img = Image.new("RGB", source.size, (255, 255, 255))
                img.paste(source, mask=source.split()[3])  # alpha 通道作为 mask 合成到白底
            elif source.mode != "RGB":
                img = source.convert("RGB")
            else:
                img = source

            img_arr = np.array(img)
            # 灰度必须走 PIL 的 convert("L")（ITU-R 601-2 系数 + PIL 的舍入）。
            # 换成 cv2.cvtColor 省事，但系数舍入差一点就可能让 Otsu 阈值挪一格，
            # 而「界面预览与最终产物逐像素一致」是硬契约。
            gray_img = img.convert("L")
            gray_arr = np.array(gray_img)
            # 两张 PIL 位图到此已无用（下面只用 numpy 数组）：**立刻关掉**。
            # 一页 5000×4400 是 RGB 68MB + L 23MB，乘以并发数就是白背的峰值内存
            # ——「处理完一张要还回去」说的正是这里。
            gray_img.close()
            img.close()
            if img is not source:
                source.close()

            # 获取命令行参数
            enable_seal = self.command_args.get("seal", False)
            seal_area = self.command_args.get("sealarea", 80)
            seal_min_sat = self.command_args.get("sealmin_sat", 50)
            seal_color = self.command_args.get("sealcolor", False)
            offset = self.command_args.get("offset", 0)
            img_type = self.command_args.get("type", 1)

            # 整图去底：阈值计算 + offset + 印章处理全部收在 utils.rembg_page。
            # ⚠️ 必须走这个函数而不是自己拼 utils 的底层调用——桌面端第三步的
            # 实时预览调的是同一个入口，两处组装逻辑分开写必然漂移，
            # 界面就会和最终产物对不上。
            final_arr = utils.rembg_page(
                img_arr,
                gray_arr,
                offset=int(offset),
                img_type=int(img_type),
                enable_seal=bool(enable_seal),
                seal_color=bool(seal_color),
                seal_area=int(seal_area),
                seal_min_sat=int(seal_min_sat),
            )

            # 保存为 PNG（300 DPI）
            # 注意：rembg 的输出格式**固定为 PNG**，不读 ext 参数。
            # type=2 是 1bit 单色位图，只有 PNG 能无损承载；JPEG 是 8bit
            # 有损格式，会把二值图重新糊成灰阶，二值化的意义就没了。
            # （历史模板里曾有一个 rembg.ext 键，那是无效配置，已删除。）
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
        """执行整图去底色：直接复用基类的并发图片处理引擎。"""
        return super().execute()
