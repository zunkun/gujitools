"""
File: functions/__init__.py
功能模块包：每个命令对应一个功能实现类。

模块职责:
- `base.py`: FunctionBase 基类，提供输入路径解析、输出路径计算、并发执行引擎。
- `text_region.py`: TextRegionProcessor 基类，封装 YOLO 检测 + area/border 规则 + 输出构建。
- `extract.py`: 从 PDF 提取页面图片（ExtractFunction）。
- `detect.py`: 检测整页图片的左右文本框，只上报坐标不写盘（DetectFunction）。
- `crop.py`: 裁剪原图像素（CropFunction），继承 TextRegionProcessor。
- `rembg.py`: 整图去底色/二值化/印章保留（RembgFunction）。
- `crop_remove.py`: 裁剪 + 去底色（CropRemoveFunction），继承 TextRegionProcessor。

通过 `get_function(command, command_args)` 工厂方法获取对应实例。

加载策略:
- 各功能类延迟加载，`get_function('extract')` 只导入 extract.py（仅需 pymupdf/PIL），
  不会触发 crop.py 的 cv2 依赖。这使得 `guji extract` 在未安装 cv2 的环境也能运行。
"""

from core.args import ArgsProvider
from core.reporter import Reporter

# 命令名 → (模块路径, 类名) 映射
_COMMAND_MAP = {
    "extract": ("functions.extract", "ExtractFunction"),
    "detect": ("functions.detect", "DetectFunction"),
    "crop": ("functions.crop", "CropFunction"),
    "rembg": ("functions.rembg", "RembgFunction"),
    "cropremove": ("functions.crop_remove", "CropRemoveFunction"),
    "print": ("functions.print", "PrintFunction"),
    "init": ("functions.init", "InitFunction"),
}


def get_function(command: str, command_args: ArgsProvider, reporter: Reporter = None):
    """工厂函数：根据命令字符串返回对应的功能实例。

    延迟导入对应模块，避免未使用的命令触发重依赖（如 crop 触发 cv2）。

    参数:
        command: 命令名称（extract/detect/crop/rembg/cropremove/print）。
        command_args: 已解析的命令参数对象。
        reporter: 结构化汇报通道（进度 / 检测框 / 尺寸）。None 时功能模块用空实现，
            输出与历史「只 print」行为一致；desktop 传入 JSON Lines 实现。

    返回:
        FunctionBase 子类实例，或 None（命令不存在）。
    """
    entry = _COMMAND_MAP.get(command)
    if entry is None:
        return None
    import importlib

    module_path, class_name = entry
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls(command_args, reporter)


# 延迟加载 base.FunctionBase（外部需要继承时才导入）
def __getattr__(name):
    if name == "FunctionBase":
        from functions.base import FunctionBase

        return FunctionBase
    raise AttributeError(f"module 'functions' has no attribute {name!r}")


__all__ = [
    "FunctionBase",
    "ExtractFunction",
    "DetectFunction",
    "CropFunction",
    "CropRemoveFunction",
    "RembgFunction",
    "PrintFunction",
    "InitFunction",
    "get_function",
]
