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
from utils.pdf_utils import run_on_input_directory
from utils.path_utils import get_extract_output_root


class ExtractFunction(FunctionBase):
    """PDF 提取功能实现类。

    直接重写 execute()，不使用基类的并发图片处理引擎。
    """

    def __init__(self, command_args, reporter=None):
        """调用基类完成输入解析后，立即计算输出根目录。"""
        super().__init__(command_args, reporter)
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
        # 默认与 CommandArgs 一致：True（自适应降级，见 pdf_utils._embedded_page_image）
        quick = self.command_args.get("quick", True)
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
                reporter=self.reporter,  # 结构化汇报：进度 + 页尺寸
            )
        except Exception as e:
            # 必须向上抛：原来只 print 后正常返回，CLI 会打印
            # "Process completed!" 并以退出码 0 结束，脚本里无法感知失败
            raise RuntimeError(f"提取失败：{e}") from e
