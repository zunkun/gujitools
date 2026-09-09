"""
File: functions/__init__.py
功能模块包：每个命令对应一个功能实现类。

模块职责:
- `base.py`: FunctionBase 基类，提供输入路径解析、输出路径计算、并发执行引擎。
- `text_region.py`: TextRegionProcessor 基类，封装 YOLO 检测 + area/border 规则 + 输出构建。
- `extract.py`: 从 PDF 提取页面图片（ExtractFunction）。
- `crop.py`: 裁剪原图像素（CropFunction），继承 TextRegionProcessor。
- `rembg.py`: 整图去底色/二值化/印章保留（RembgFunction）。
- `crop_remove.py`: 裁剪 + 去底色（CropRemoveFunction），继承 TextRegionProcessor。

通过 `get_function(command, command_args)` 工厂方法获取对应实例。

加载策略:
- 各功能类延迟加载，`get_function('extract')` 只导入 extract.py（仅需 pymupdf/PIL），
  不会触发 crop.py 的 cv2 依赖。这使得 `guji extract` 在未安装 cv2 的环境也能运行。
"""

from cli.command_args import CommandArgs

# 命令名 → (相对模块路径, 类名) 映射
_COMMAND_MAP = {
    "extract": (".extract", "ExtractFunction"),
    "crop": (".crop", "CropFunction"),
    "rembg": (".rembg", "RembgFunction"),
    "cropremove": (".crop_remove", "CropRemoveFunction"),
    "print": (".print", "PrintFunction"),
    "init": (".init", "InitFunction"),
}


def get_function(command: str, command_args: CommandArgs):
    """工厂函数：根据命令字符串返回对应的功能实例。

    延迟导入对应模块，避免未使用的命令触发重依赖（如 crop 触发 cv2）。

    参数:
        command: 命令名称（extract/crop/rembg/cropremove）。
        command_args: 已解析的命令参数对象。

    返回:
        FunctionBase 子类实例，或 None（命令不存在）。
    """
    entry = _COMMAND_MAP.get(command)
    if entry is None:
        return None
    import importlib

    rel_module, class_name = entry
    mod = importlib.import_module(rel_module, __name__)
    cls = getattr(mod, class_name)
    return cls(command_args)


# 延迟加载 base.FunctionBase（外部需要继承时才导入）
def __getattr__(name):
    if name == "FunctionBase":
        from .base import FunctionBase

        return FunctionBase
    raise AttributeError(f"module 'functions' has no attribute {name!r}")


__all__ = [
    "FunctionBase",
    "ExtractFunction",
    "CropFunction",
    "CropRemoveFunction",
    "RembgFunction",
    "PrintFunction",
    "InitFunction",
    "get_function",
]
