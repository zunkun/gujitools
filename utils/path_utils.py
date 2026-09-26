"""
路径工具函数，用于解析各种命令的输出目录。
"""

from pathlib import Path
from typing import Optional


def assert_output_not_input(input_path, out_path) -> None:
    """确认输出目录不会撞上输入目录：撞上就抛 `ValueError`。

    为什么必须有这道闸（2026-09-26 实测，硬证据）
        `resolve_final_output_dir` 在「目录输入 + 不给 `--output`」时返回
        ``input.parent / <该命令的子目录名>``。当**输入目录的 basename 恰好等于
        该命令的子目录名**时（`.../rembg` 跑 rembg、`.../crop` 跑 crop、
        `.../detect` 跑 `detect --save`、`.../images` 跑 extract），输出目录
        就是**输入目录本身**。实测把两张可辨认的 PNG 放进一个叫 `rembg` 的目录：

        | `clean` | 结果 |
        |---|---|
        | False | `1.png`/`2.png` **被原地覆盖**（rembg 输出名与输入同名） |
        | True  | `rmtree(outpath)` 把**输入目录连同图片全部删除**，目录被重建为空，**退出码仍是 0** |

        后者是静默丢数据：用户的原图没了，命令还报成功。
        "重跑自己上一步的输出目录"是极常见的操作（`.../rembg`、`.../crop`），
        所以不能靠用户小心。

    判据（两条都要挡）
        1. 输出 == 输入（原地覆盖 / 删掉输入）；
        2. 输出是输入的**祖先**（`rmtree(输出)` 同样会连输入一起删）。

    输入是**文件**时按它的父目录看待——对 extract 这类「输出根目录 = PDF 所在目录、
    产物落在其子目录」的命令，`out_path == input.parent` 是合法的，那种情况由
    「输出是否是输入的祖先」这条判据排除（父目录不是祖先关系里的 out 侧）。

    参数:
        input_path: 输入路径（文件或目录）。
        out_path: 计算出的输出目录。

    抛出:
        ValueError: 输出会撞上输入时，附上可照做的修法（改用 `-o` 指到别处）。
    """
    try:
        src = Path(input_path).resolve()
        dst = Path(out_path).resolve()
    except OSError:  # 路径过长/无权限等：交给真正的 IO 去报，别在这里拦
        return
    src_dir = src.parent if src.is_file() else src
    if dst == src_dir:
        raise ValueError(
            f"输出目录与输入目录相同：{dst}\n"
            "这会让本命令原地覆盖自己的输入（并且在 --clean 时把输入整个删掉）。\n"
            "请用 -o/--output 指到一个不同的目录，例如："
            f" -o {src_dir.parent / (src_dir.name + '-out')}"
        )
    if dst in src_dir.parents:
        raise ValueError(
            f"输出目录是输入目录的上级：{dst}\n"
            "清理输出目录时会连输入一起删掉。请用 -o/--output 指到输入目录之内"
            "或并列的其它目录。"
        )


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
    final = root / default_subdir
    # ⚠️ 出口处必须过闸：输入目录名恰好等于 default_subdir 时，final 就是输入本身，
    #    不加 --clean 会原地覆盖、加 --clean 会把输入整个删掉（实测，见函数文档）。
    assert_output_not_input(input_path, final)
    return final


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
