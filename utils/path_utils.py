"""
路径工具函数，用于解析各种命令的输出目录。
"""

from pathlib import Path
from typing import Optional


def resolve_final_output_dir(
    input_path: Path,
    output_arg: Optional[str],
    is_file: bool,
    default_subdir: str,
) -> Path:
    """
    计算命令的最终输出目录（适用于 crop/rembg/cropremove 等）。

    规则：
    - 如果指定了 --output：
        - 若输出值不含路径分隔符，则视为简单名称：
            - 根目录 = 输入路径的父目录 / 名称
            - 无论输入是文件还是目录，都使用 `input_path.parent` 作为基准。
        - 若含分隔符，则解析为绝对/相对路径（基于当前工作目录）。
    - 如果未指定 --output：
        - 根目录 = 输入路径的父目录（即与输入文件/目录并列）。
    - 最终输出目录 = 根目录 / default_subdir

    这样设计确保：
        - 对于目录输入，输出默认与输入目录并列（而非在输入目录内部）。
        - 用户指定的 -o 作为根目录，其下自动追加 default_subdir。
        - 对于文件输入，输出默认在文件所在父目录下创建 default_subdir。

    参数:
        input_path: 原始输入路径（Path 对象，已解析为绝对路径）。
        output_arg: 用户传入的 --output 参数（原始字符串或 None）。
        is_file: 输入是否为单个文件（否则为目录）。本函数中主要用来区分是否使用 input_path.parent 作为基准。
        default_subdir: 默认子目录名（如 "crop"）。

    返回:
        最终的输出目录（Path 对象）。
    """
    if output_arg is not None:
        out_str = str(output_arg).strip()
        # 判断是否包含路径分隔符
        if "/" not in out_str and "\\" not in out_str:
            # 简单名称：相对于输入路径的父目录
            root = input_path.parent / out_str
        else:
            # 含分隔符，直接解析
            root = Path(out_str).expanduser().resolve()
    else:
        # 未指定 --output：根目录为输入路径的父目录
        root = input_path.parent

    # 最终目录 = 根目录 / default_subdir
    return root / default_subdir


def get_extract_output_root(
    input_path: Path,
    output_arg: Optional[str],
    is_file: bool,
) -> Path:
    """
    计算 extract 命令的输出根目录（out_root）。

    该目录下会为每个 PDF 创建以 PDF 文件名命名的子目录，并在其下存放图片。
    图片子目录名（如 "images"）由调用方在后续拼接时决定（通过 subdir_name 参数传递给 run_on_input_directory）。

    规则：
    - 如果指定了 --output：
        - 若输出值不含路径分隔符，则视为简单名称：
            - 输入为文件时，根目录 = 文件所在父目录 / 名称
            - 输入为目录时，根目录 = 输入目录 / 名称
        - 若含分隔符，则解析为绝对/相对路径（基于当前工作目录）。
    - 如果未指定 --output：
        - 输入为文件时，根目录 = 文件所在父目录
        - 输入为目录时，根目录 = 输入目录本身

    参数:
        input_path: 原始输入路径（Path 对象，已解析为绝对路径）。
        output_arg: 用户传入的 --output 参数（原始字符串或 None）。
        is_file: 输入是否为单个文件（否则为目录）。

    返回:
        输出根目录（Path 对象）。
    """
    if output_arg is not None:
        out_str = str(output_arg).strip()
        # 判断是否包含路径分隔符
        if "/" not in out_str and "\\" not in out_str:
            # 简单名称，相对于输入父目录（文件）或输入目录（目录）
            if is_file:
                root = input_path.parent / out_str
            else:
                root = input_path / out_str
        else:
            # 含路径分隔符，解析为绝对路径（相对路径基于当前工作目录）
            root = Path(out_str).expanduser().resolve()
    else:
        # 未指定 --output
        if is_file:
            root = input_path.parent
        else:
            root = input_path
    return root
