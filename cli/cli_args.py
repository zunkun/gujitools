"""
File: cli/cli_args.py
命令行参数解析模块。

定义所有支持的子命令（extract/crop/rembg/cropremove/help）及其参数。

子命令与别名:
- extract (-e): 从 PDF 提取页面图片
- crop: 基于 YOLO 检测裁剪左右文本框
- rembg (-r): 整图去底色/二值化/印章保留
- cropremove (-cr): 复合流程（crop + rembg）
- print: 打印 PDF（仅支持通过 run 命令执行）
- help: 查看命令手册（guji help <command>，内容来自 docs/functions/*.md）

每个子命令的参数定义包含帮助文本（--help 时显示）和类型约束。
所有默认值统一在 CommandArgs._build_args 中维护，此处不设 default。
"""

import sys
import argparse
from pathlib import Path

from utils.help import process_help_command


class CliArgsParser:
    """包装 argparse，定义程序支持的子命令与参数。"""

    def __init__(self):
        self.parser: argparse.ArgumentParser = self.create_parser()

    def create_parser(self) -> argparse.ArgumentParser:
        """创建并配置 argparse.ArgumentParser 以及所有子命令。

        备注：使用 `add_help=False` 并自定义 `-h/--help`，以便统一使用 `utils.help` 中的帮助显示逻辑。
        """
        parser = argparse.ArgumentParser(
            prog="guji",
            add_help=False,  # 交由自定义帮助处理
            description="古籍处理命令行工具",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""使用 'guji help' 查看详细帮助\n使用 'guji help <command>' 查看命令手册""",
        )

        # 基本全局开关（帮助/版本）
        parser.add_argument("-h", "--help", action="store_true", help="显示帮助")
        parser.add_argument("-v", "--version", action="store_true", help="显示版本")

        # 子命令容器
        subparsers = parser.add_subparsers(dest="command", help="要执行的功能")

        # ============ extract ============
        extract_parser = subparsers.add_parser(
            "extract", aliases=["-e"], help="从PDF提取图片", add_help=False
        )
        extract_parser.add_argument("-i", "--input", type=Path, help="PDF文件路径")
        extract_parser.add_argument("-o", "--output", help="输出目录名称")
        extract_parser.add_argument("--zoom", type=int, help="缩放因子")
        extract_parser.add_argument("--quick", action="store_true", help="快速模式")
        extract_parser.add_argument(
            "--ext", choices=["jpg", "png", "tiff"], help="输出格式"
        )
        extract_parser.add_argument("--pages", help='页码: "1,2,5-7"')
        extract_parser.add_argument("--start", type=int, help="起始页码")
        extract_parser.add_argument("--end", type=int, help="结束页码")
        extract_parser.add_argument("--workers", type=int, help="线程数")
        extract_parser.add_argument("--batch-size", type=int, help="批量大小")
        extract_parser.add_argument("--clean", action="store_true", help="清空输出目录")
        # 注意：移除了 --config 参数，因为配置管理统一由 run 命令负责

        # ============ crop ============
        crop_parser = subparsers.add_parser("crop", help="裁剪文字区域", add_help=False)
        crop_parser.add_argument("-i", "--input", type=Path, help="图片文件或目录")
        crop_parser.add_argument("-o", "--output", help="输出目录名称")
        crop_parser.add_argument("--clean", action="store_true", help="清空输出目录")
        crop_parser.add_argument(
            "--ext", choices=["jpg", "png", "tiff"], help="输出格式"
        )
        crop_parser.add_argument(
            "--area",
            type=int,
            choices=[1, 2, 3],
            help="裁剪区域类型，默认1\n"
            "1 = 逐框独立裁剪，分别输出 -l/-r 两张图，无框时输出原图\n"
            "2 = 逐框独立裁剪，单图输出，border=None 保持原尺寸\n"
            "3 = 合并左右框为整体外边界裁剪，单图输出，border=None 保持原尺寸",
        )
        crop_parser.add_argument(
            "--border",
            help="文本框边界控制（mm），对 --area 1/2/3 均生效，默认None\n"
            "None = 裁剪到各框边界（area=1）；输出与原图同尺寸（area=2/3）\n"
            "0 = 裁剪到文本框外边界，丢弃外侧区域\n"
            "有值 = 裁剪到外边界并按该值外扩空白边距（mm->px @300dpi）\n"
            "支持4种写法（数字用英文逗号分隔）：\n"
            "1. 单值30 → 四边统一 [30,30,30,30]\n"
            "2. 两值20,30 → 上下20，左右30 [20,30,20,30]\n"
            "3. 三值20,30,25 → 上20，左右30，下25 [20,30,25,30]\n"
            "4. 四值20,30,20,25 → 上20 右30 下20 左25",
        )
        crop_parser.add_argument("--workers", type=int, help="线程数")
        # 移除 --config

        # ============ rembg ============
        rembg_parser = subparsers.add_parser(
            "rembg", aliases=["-r"], help="图片去底色", add_help=False
        )
        rembg_parser.add_argument("-i", "--input", type=Path, help="图片文件或目录")
        rembg_parser.add_argument("-o", "--output", help="输出目录名称")
        rembg_parser.add_argument("--clean", action="store_true", help="清空输出目录")
        rembg_parser.add_argument(
            "--offset",
            type=int,
            help="二值阈值偏移量，正数文字加粗变深，负数文字变细，默认0",
        )
        rembg_parser.add_argument(
            "--type",
            type=int,
            choices=[1, 2, 3],
            help="输出图片类型，默认1\n1 = 8位二值图\n2 = 1bit单色位图\n3 = 8位灰度图",
        )
        rembg_parser.add_argument(
            "--seal",
            action="store_true",
            help="【印章总开关】启用红色印章识别；程序默认关闭印章识别",
        )
        rembg_parser.add_argument(
            "--sealcolor",
            action="store_true",
            help="【印章色彩输出开关】检测到合格印章时输出RGB彩色PNG保留红色",
        )
        rembg_parser.add_argument(
            "--sealarea",
            type=int,
            help="【印章面积阈值】判定为有效印章的最小连通域像素面积，默认80",
        )
        rembg_parser.add_argument(
            "--sealmin-sat",
            type=int,
            help="【红色颜色下限阈值】红色识别最低饱和度(范围0~255)，默认50",
        )
        rembg_parser.add_argument("--workers", type=int, help="线程数")
        # 移除 --config

        # ============ cropremove ============
        cropremove_parser = subparsers.add_parser(
            "cropremove",
            aliases=["-cr"],
            help="图片识别并去底色， crop + rembg",
            add_help=False,
        )
        cropremove_parser.add_argument(
            "-i", "--input", type=Path, help="图片文件或目录"
        )
        cropremove_parser.add_argument("-o", "--output", help="输出目录名称")
        cropremove_parser.add_argument(
            "--clean", action="store_true", help="清空输出目录"
        )
        cropremove_parser.add_argument(
            "--offset",
            type=int,
            help="二值阈值偏移量，正数文字加粗变深，负数文字变细，默认0",
        )
        cropremove_parser.add_argument(
            "--type",
            type=int,
            choices=[1, 2, 3],
            help="输出图片类型，默认1\n1 = 8位二值图\n2 = 1bit单色位图\n3 = 8位灰度图",
        )
        cropremove_parser.add_argument(
            "--area",
            type=int,
            choices=[1, 2, 3],
            help="去底色文本区域识别类型，默认1\n"
            "1 = 逐框独立 Otsu（阈值取 left+right 合并），分别裁剪左右框输出 -l/-r 两张图，无框时输出原图\n"
            "2 = 逐框独立 Otsu（同1），单图输出，border=None 保持原尺寸\n"
            "3 = 合并左右框为整体外边界统一 Otsu，单图输出，border=None 保持原尺寸",
        )
        cropremove_parser.add_argument(
            "--border",
            help="文本框边界控制（mm），对 --area 1/2/3 均生效，默认None\n"
            "None = 裁剪到各框边界（area=1）；输出与原图同尺寸（area=2/3）\n"
            "0 = 裁剪到文本框外边界，丢弃外侧区域（area=1 各框，area=2/3 联合）\n"
            "有值 = 裁剪到外边界并按该值外扩空白边距（mm->px @300dpi），类比CSS margin\n"
            "支持4种写法（数字用英文逗号分隔）：\n"
            "1. 单值30 → 四边统一 [30,30,30,30]\n"
            "2. 两值20,30 → 上下20，左右30 [20,30,20,30]\n"
            "3. 三值20,30,25 → 上20，左右30，下25 [20,30,25,30]\n"
            "4. 四值20,30,20,25 → 上20 右30 下20 左25",
        )
        cropremove_parser.add_argument(
            "--seal",
            action="store_true",
            help="【印章总开关】启用红色印章识别；程序默认关闭印章识别",
        )
        cropremove_parser.add_argument(
            "--sealcolor",
            action="store_true",
            help="【印章色彩输出开关】检测到合格印章时输出RGB彩色PNG保留红色",
        )
        cropremove_parser.add_argument(
            "--sealarea",
            type=int,
            help="【印章面积阈值】判定为有效印章的最小连通域像素面积，默认80",
        )
        cropremove_parser.add_argument(
            "--sealmin-sat",
            type=int,
            help="【红色颜色下限阈值】红色识别最低饱和度(范围0~255)，默认50",
        )
        cropremove_parser.add_argument("--workers", type=int, help="线程数")
        # 移除 --config

        # ============ help ============
        # help 子命令：guji help [command] 查看命令手册，内容来自 docs/functions/<command>.md
        help_parser = subparsers.add_parser("help", help="查看命令手册")
        help_parser.add_argument(
            "topic",
            nargs="?",
            help="命令名称：extract / crop / rembg / cropremove / overview",
        )

        # ============ init ============
        init_parser = subparsers.add_parser(
            "init",
            help="交互式生成 guji.yaml 配置文件",
            add_help=False,
        )
        init_parser.add_argument(
            "--force", action="store_true", help="强制覆盖已有 guji.yaml"
        )

        init_parser.add_argument(
            "-i",
            "--input",
            type=Path,
            help="原始 PDF 或图片目录（用于配置中的 extract.input）",
        )
        init_parser.add_argument(
            "-o",
            "--output",
            type=Path,
            help="输出根目录（用于配置中的 extract.output 及其他命令的 input）",
        )

        # ============ run ============
        # run 子命令：从配置文件加载参数执行子命令
        run_parser = subparsers.add_parser(
            "run",
            help="从配置文件加载参数并执行子命令（例如：guji run crop）",
            add_help=False,
        )
        run_parser.add_argument(
            "subcommand",
            choices=["extract", "crop", "rembg", "cropremove", "print"],
            help="要执行的子命令名称",
        )
        run_parser.add_argument(
            "--config",
            type=Path,
            default=Path.cwd() / "guji.yaml",
            help="配置文件路径（默认 ./guji.yaml）",
        )
        # 注意：run 不接受其他业务参数，全部从配置读取

        # 在 create_parser 中添加 print 子命令
        print_parser = subparsers.add_parser(
            "print",
            help="打印PDF（仅支持通过 run 命令执行）",
            add_help=False,
        )

        return parser

    def parse_args(self):
        """解析命令行参数并处理别名/帮助命令。

        返回 argparse.Namespace。
        """
        args, unknown_args = self.parser.parse_known_args()
        if unknown_args:
            print(f"警告：忽略未定义参数: {' '.join(unknown_args)}")

        # -v/--version 标志
        if getattr(args, "version", False):
            process_help_command("version")

        # help 子命令：提取 topic 传给帮助系统（docs/functions/<topic>.md）
        if args.command == "help":
            topic = getattr(args, "topic", None)
            process_help_command(args.command, topic)

            sys.exit(1)
        # 处理命令别名映射，保持内部使用标准命令名
        alias_map = {
            "-e": "extract",
            "-r": "rembg",
            "-cr": "cropremove",
        }
        if args.command in alias_map:
            args.command = alias_map[args.command]

        return args
