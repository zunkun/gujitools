"""
工具函数包：图像处理、文件操作、PDF 渲染、YOLO 检测、排序、路径解析、帮助。

各模块职责:
- `image_utils`: Otsu 阈值计算、红色印章提取、区域/整图去底、border 参数解析。
- `image_io`: cv2 读写封装，规避中文路径下 `cv2.imread` 返回 None 的问题。
- `file_utils`: 图片文件收集与尺寸校验。
- `yolo_utils`: YOLO 模型加载与左右文本框检测。
- `pdf_utils`: PDF 页面渲染为图片（多线程批量处理）。
- `sort_utils`: 自然排序（封面/菜单优先，数字感知）。
- `path_utils`: 输出路径解析（extract 根目录、各命令最终输出目录）。
- `help`: man 风格帮助文本加载与分页显示。

加载策略:
- `sort_utils`、`file_utils`、`path_utils` 无重依赖，在包初始化时直接导入；
- `yolo_utils`（依赖 cv2/ultralytics）和 `image_utils`（依赖 cv2/numpy）
  使用 `__getattr__` 延迟加载，避免 `from utils.help import ...` 时触发不必要的导入。
"""

from utils.sort_utils import natural_sort_key
from utils.file_utils import collect_image_files, is_valid_image_size, IMAGE_EXTS
from utils.path_utils import resolve_final_output_dir, get_extract_output_root

# 重依赖模块的函数名 → (模块路径, 函数名) 映射，首次访问时按需加载
_LAZY = {
    "load_yolo_model": ("utils.yolo_utils", "load_yolo_model"),
    "detect_left_right_boxes": ("utils.yolo_utils", "detect_left_right_boxes"),
    "calculate_auto_threshold": ("utils.image_utils", "calculate_auto_threshold"),
    "extract_red_seal": ("utils.image_utils", "extract_red_seal"),
    "apply_otsu_to_region": ("utils.image_utils", "apply_otsu_to_region"),
    "apply_otsu_whole": ("utils.image_utils", "apply_otsu_whole"),
    "parse_border": ("utils.image_utils", "parse_border"),
    "parse_border_mm": ("utils.box_geometry", "parse_border_mm"),
    "compute_final_boxes": ("utils.box_geometry", "compute_final_boxes"),
    "imread": ("utils.image_io", "imread"),
    "imwrite": ("utils.image_io", "imwrite"),
}


def __getattr__(name):
    """延迟加载重依赖模块的函数，首次访问时才导入 cv2/numpy/ultralytics。"""
    entry = _LAZY.get(name)
    if entry is not None:
        import importlib

        module_path, attr_name = entry
        mod = importlib.import_module(module_path)
        return getattr(mod, name)
    raise AttributeError(f"module 'utils' has no attribute {name!r}")
