#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""帮助与手册加载模块。

实现 man 风格帮助：从 `docs/functions/<command>.md` 加载 Markdown 文档，
轻量转换为终端可读纯文本后，通过 less/more 分页显示。

文档来源单一：`docs/functions/` 下的 .md 文件即为帮助手册内容，无需维护额外 .txt 副本。

支持的帮助主题:
    guji help                # 显示命令总览
    guji help extract        # 查看 extract 命令手册
    guji help crop           # 查看 crop 命令手册
    guji help rembg          # 查看 rembg 命令手册
    guji help cropremove     # 查看 cropremove 命令手册
    guji help overview       # 查看功能模块概览
"""

import os
import re
import sys
import shutil
import subprocess
from pathlib import Path

from config import VERSION

# ---------- Markdown → 纯文本转换 ----------


def markdown_to_text(md: str) -> str:
    """将 Markdown 轻量转为终端可读纯文本。

    转换规则:
    - 代码围栏 (``` ```python) → 移除围栏行，保留代码内容并缩进；
    - 标题 (# / ## / ###) → 移除 # 标记，一级标题加 === 下划线，二级加 --- 下划线；
    - 粗体 **text** → text；
    - 行内代码 `text` → text；
    - 链接 [text](url) → text（不含 URL）；
    - 表格、列表、流程图等保留原样（等宽字体下可读）。
    """
    lines = md.split("\n")
    result = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()

        # 代码围栏：``` 或 ```python 等
        if stripped.startswith("```"):
            if not in_code_block:
                in_code_block = True
                continue  # 跳过围栏开始行
            else:
                in_code_block = False
                continue  # 跳过围栏结束行

        if in_code_block:
            # 代码块内容保留原样，缩进 2 空格便于区分
            result.append("  " + line if line else line)
            continue

        # 标题：# text / ## text / ### text
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            # 去掉标题中的粗体/行内代码标记
            title = re.sub(r"\*\*(.+?)\*\*", r"\1", title)
            title = re.sub(r"`([^`]+)`", r"\1", title)
            if level == 1:
                result.append(title)
                result.append("=" * _display_width(title))
            elif level == 2:
                result.append("")
                result.append(title)
                result.append("-" * _display_width(title))
            else:
                result.append(f"  {title}")
            continue

        # 去掉行内粗体 **text** → text
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        # 去掉行内斜体 *text* → text（避免误伤列表标记 * ）
        line = re.sub(r"(?<![\*\s])\*(?![\*\s])(.+?)\*(?!\*)", r"\1", line)
        # 去掉行内代码 `text` → text
        line = re.sub(r"`([^`]+)`", r"\1", line)
        # 链接 [text](url) → text
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)

        result.append(line)

    return "\n".join(result)


def _display_width(s: str) -> int:
    """估算字符串在终端中的显示宽度（中文字符占 2 列）。"""
    width = 0
    for ch in s:
        width += 2 if ord(ch) > 127 else 1
    return max(width, 1)


# ---------- 快速帮助 ----------


def print_quick_help():
    """打印内置的快速帮助信息（命令总览）。"""
    help_text = """
=========================================
  guji - 古籍处理命令行工具 v{VERSION}
=========================================

用法:
  guji <command> [options]
  guji help <command>          查看命令详细手册

可用命令:
  extract  (-e)   从 PDF 提取页面为图片
  crop           基于 YOLO 裁剪左右文本框
  rembg    (-r)   整图去底色 / 二值化 / 印章保留
  cropremove (-cr)  裁剪 + 去底色（复合流程）

全局选项:
  -h, --help     显示此帮助信息
  -v, --version  显示版本信息

获取详细帮助:
  guji help                显示命令总览
  guji help extract        查看 extract 手册
  guji help cropremove     查看 cropremove 手册
  guji help overview       查看功能模块概览

常用示例:
  guji extract -i book.pdf -o ./images --zoom 2
  guji crop -i ./images -o ./cropped
  guji rembg -i ./images -o ./output --seal --sealcolor
  guji cropremove -i ./images -o ./output --area 1

更多信息: https://github.com/zunkun/gujitools
""".format(VERSION=VERSION)
    print(help_text)


def print_version():
    """打印版本信息"""
    print(f"guji tools version {VERSION}")


# ---------- 帮助文本加载 ----------

# 命令名 → docs/functions 下的文档文件名映射
_DOC_MAP = {
    "extract": "extract.md",
    "crop": "crop.md",
    "rembg": "rembg.md",
    "cropremove": "cropremove.md",
    "overview": "overview.md",
    "print": "print.md",
}


def get_help_text(command=None) -> str:
    """获取帮助文本。

    优先级:
    1. `docs/functions/<command>.md` — Markdown 文档（转为纯文本）；
    2. `docs/man/guji-<command>.txt` — man 风格文本（兼容旧文件）；
    3. 内置快速帮助。

    参数:
        command: 命令名（extract/crop/rembg/cropremove/overview），None 表示总览。

    返回:
        帮助文本字符串。
    """
    project_root = Path(__file__).resolve().parent.parent
    functions_dir = project_root / "docs" / "functions"

    # 有指定命令 → 查找 docs/functions/<command>.md
    if command and command in _DOC_MAP:
        md_file = functions_dir / _DOC_MAP[command]
        if md_file.exists():
            with open(md_file, "r", encoding="utf-8") as f:
                return markdown_to_text(f.read())

    # 兼容旧 man 文本文件
    if command:
        man_file = project_root / "docs" / "man" / f"guji-{command}.txt"
        if man_file.exists():
            with open(man_file, "r", encoding="utf-8") as f:
                return f.read()

    # 无指定命令 → 总览
    if command is None:
        overview = functions_dir / "overview.md"
        if overview.exists():
            with open(overview, "r", encoding="utf-8") as f:
                return markdown_to_text(f.read())

    # 最终回退：快速帮助
    return f"No help available for this topic: {command}.\n"


# ---------- 分页显示 ----------


def show_help_page(command=None):
    """分页显示帮助页面（尝试使用 less/more，无分页器则直接打印）。"""
    text = get_help_text(command)

    if text is None:
        # 找不到文档 → 提示可用主题后回退到快速帮助
        if command:
            print(f"未知主题: {command}")
            print(f"可用主题: {', '.join(_DOC_MAP.keys())}\n")
        print_quick_help()
        return

    # 非交互终端（管道/重定向/IDE 输出捕获）直接打印，不启动分页器
    if not sys.stdout.isatty():
        print(text)
        return

    # 交互终端：尝试使用分页器
    if shutil.which("less"):
        args = ["less", "-R"]  # -R 保留颜色
    elif shutil.which("more"):
        args = ["more"]
    else:
        print(text)
        return

    # 使用分页器显示文本（显式指定 UTF-8，避免 Windows 默认 cp936 乱码）
    try:
        p = subprocess.Popen(args, stdin=subprocess.PIPE, text=True, encoding="utf-8")
        p.communicate(text)
        p.wait()
    except KeyboardInterrupt:
        pass
    except Exception:
        # 分页器失败则回退到直接打印
        print(text)


def show_command_help(command=None):
    """别名：显示指定命令的帮助页面。"""
    show_help_page(command)


def process_help_command(command: str, topic: str | None = None):
    """处理 CLI 层传来的 help/version 命令并在需要时退出进程。

    参数:
        command: argparse 解析出的子命令名。特殊值:
            None    — 未指定子命令，显示总览
            'help'  — help 子命令，显示 topic 指定的手册
            'version' — 显示版本
            '-h'/'--help' — 显示总览
        topic: 当 command='help' 时，要查看的命令名（如 'extract'）。
    """
    if command is None:
        print_quick_help()
        sys.exit(0)
    elif command == "help":
        show_help_page(topic)
        sys.exit(0)
    elif command == "version":
        print_version()
        sys.exit(0)
    elif command in ["-h", "--help"]:
        show_help_page(None)
        sys.exit(0)
    else:
        # 正常命令（extract/crop/rembg/cropremove/print），不退出，交给后续流程
        return


if __name__ == "__main__":
    # 测试：python help.py [topic]
    if len(sys.argv) > 1:
        show_help_page(sys.argv[1])
    else:
        show_help_page()
