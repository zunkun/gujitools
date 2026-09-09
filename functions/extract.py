"""
File: functions/extract.py
从 PDF 中提取页面图片的功能实现。

此功能对应 `guji extract` 命令，将 PDF 每页渲染为图片并保存到输出目录。

处理流程：
1. 计算输出根目录（支持文件/目录两种输入，--output 统一作为根目录）；
2. 从命令参数收集 zoom、ext、pages、workers 等选项；
3. 委托给 `utils.pdf_utils.run_on_input_directory` 执行实际渲染。

注意：此功能不使用 FunctionBase 的并发执行引擎（不需要 _process_single_image），
因为 PDF 渲染的并发逻辑在 `pdf_utils` 内部实现。
"""

from functions.base import FunctionBase
from pathlib import Path
from utils.pdf_utils import run_on_input_directory
from utils.path_utils import get_extract_output_root


class ExtractFunction(FunctionBase):
    """PDF 提取功能实现类。

    直接重写 execute()，不使用基类的并发图片处理引擎。
    """

    def __init__(self, command_args):
        super().__init__(command_args)
        self._calc_outpath()

    def _calc_outpath(self):
        """计算输出根目录，结果保存在 self.outpath 中。"""
        self.outpath = get_extract_output_root(
            self.input,
            self.output_raw,
            self.is_file,
        )
        print(f"输出根目录：{self.outpath}")

    def execute(self):
        """执行 PDF 提取：收集参数并委托给 pdf_utils。

        输出规则：
        - 每个 PDF 的输出位置为 <out_root>/<pdf_name>/<default_temp_name>/，
          其中 <out_root> 即 self.outpath，<default_temp_name> 为类属性。
        - 不再区分单文件/目录，统一行为。
        """
        print(f"输入路径：{self.input}")
        print(f"输出根目录：{self.outpath}")

        # 收集命令行参数
        zoom = self.command_args.get("zoom", 1)
        quick = self.command_args.get("quick", False)
        ext = self.command_args.get("ext", "jpg")
        pages = self.command_args.get("pages")
        start = self.command_args.get("start")
        end = self.command_args.get("end")
        workers = self.command_args.get("workers")
        batch_size = self.command_args.get("batch_size")
        clean = self.command_args.get("clean", False)

        input_path = str(self.input)
        out_root = str(self.outpath)

        try:
            run_on_input_directory(
                input_path,
                out_root,
                zoom=zoom,
                ext=ext,
                workers=workers,
                quick=quick,
                pages=pages,
                start=start,
                end=end,
                batch_size=batch_size,
                clean=clean,
                subdir_name=self.default_temp_name,  # 传递图片子目录名
            )
        except Exception as e:
            print(f"❌ 提取失败: {e}")
