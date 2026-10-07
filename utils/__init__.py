"""
工具函数包：图像处理、文件操作、PDF 渲染、YOLO 检测、排序、路径解析、帮助。

各模块职责:
- `image_utils`: Otsu 阈值计算、红色印章提取、区域/整图去底、border 参数解析。
- `image_io`: cv2 读写封装，规避中文路径下 `cv2.imread` 返回 None 的问题。
- `file_utils`: 图片文件收集与尺寸校验。
- `yolo_utils`: YOLO 模型加载与页面内容框检测（harfcontent 半幅 / fullcontent 整幅）。
- `pdf_extract`: PDF 页面渲染为图片（多线程批量处理）。
- `pdf_draw`: 生成 PDF 的绘制辅助（字体注册、竖排文字、页侧判定）。
- `pdf_stream`: 让 fpdf 的输出**边写边落盘**（顶替整本输出缓冲，`print` 专用）。
- `pdf_utils`: 上两者的**兼容 re-export 壳**，新代码请直接 import 具体模块。
- `sort_utils`: 自然排序（封面/菜单优先，数字感知）。
- `path_utils`: 输出路径解析（extract 根目录、各命令最终输出目录）。
- `color_utils`: 颜色 'r,g,b' 解析（非法值抛错，不静默降级为黑）。
- `margin_utils`: 边距 CSS 简写标准化（单/两/三/四值 → [上,右,下,左]）。
- `transparent_png`: 白底 → 透明底的 PNG 编码（第三步提交产物专用，自带最省形态选择）。
- `cage_warp`: 变换笼（GIMP 口径）——RBF（Wendland 紧支撑核）位移场 + 稀格求场 + 双线性取样，拖把手做局部形变（numpy 延迟导入）。与 `puppet_warp` **并存**：桌面「变换笼」工具走这条，「变形」工具走图钉那条。
- `puppet_warp`: 操控变形（PS Puppet Warp 口径）——ARAP 三角网格形变，图钉 + 隐式边框锚点（numpy/scipy 延迟导入）。
- `perspective`: 四点透视校正（古籍页形/拍摄角度摆正）——四点 DLT 单应矩阵 + 逆向采样（numpy 延迟导入）。
- `help`: man 风格帮助文本加载与分页显示。

`color_utils` 与 `margin_utils` 位于最低层，供 core 与 functions 共用，
以保证命令行、GUI 表单、PDF 生成三处对同一参数的解释完全一致。

加载策略:
- `path_utils`、`file_utils`、`sort_utils` 无重依赖，在包初始化时直接导入，
  以同时支持 `from utils import xxx` 与 `utils.xxx` 两种取用方式；
- 其余模块一律通过 `from utils.<module> import <name>` 直接导入；
- `yolo_utils`（依赖 cv2/ultralytics）和 `image_utils`（依赖 cv2/numpy）
  使用 `__getattr__` 延迟加载，避免 `from utils.help import ...` 时触发不必要的导入。
"""

# 无重依赖的模块在包初始化时直接导入，使 `utils.xxx` 与 `from utils import xxx`
# 两种取用方式都成立（functions/base.py、functions/rembg.py、
# desktop/stages/detect_stage.py 等均以 `utils.xxx` 形式取用）。
# 这些名字是包对外的公开别名，pyflakes 会报「未使用」——属预期，故整体禁用该检查。
# flake8: noqa: F401
from typing import TYPE_CHECKING

from utils.file_utils import IMAGE_EXTS, collect_image_files, is_valid_image_size
from utils.path_utils import get_extract_output_root, resolve_final_output_dir
from utils.sort_utils import natural_sort_key

# 重依赖模块的函数名 → (模块路径, 函数名) 映射，首次访问时按需加载
# ⚠️ 类型检查器看不见下面的 ``__getattr__``（PEP 562），缺了 _LAZY 的类型侧
# 声明会把这些名字全判成未定义，故补一段只在 TYPE_CHECKING 下生效的导入：
# **运行时的延迟加载一点没变**（`from utils import x` 仍不会拉进 cv2/numpy）。
if TYPE_CHECKING:
    from utils.cage_warp import (
        cage_moved, deform, deform_qimage, influence_radius, moved_handles,
        perimeter_cage, warp_region,
    )
    from utils.image_utils import (
        apply_otsu_to_region, apply_otsu_whole, calculate_auto_threshold,
        extract_red_seal, parse_border, rembg_page,
    )
    from utils.perspective import (
        homography, quad_moved, rectify, rectify_qimage, rectify_region,
        target_rect,
    )
    from utils.puppet_warp import (
        border_vertices, build_mesh, drag_cell, grid_cell, mesh_moved,
        mesh_region, nearest_vertex, puppet_warp, puppet_warp_qimage, solve_arap,
        solve_puppet,
    )
    from utils.yolo_utils import (
        detect_content_boxes, is_model_loaded, load_seconds_used, load_yolo_model,
        model_path,
    )

_LAZY = {
    "load_yolo_model": ("utils.yolo_utils", "load_yolo_model"),
    "detect_content_boxes": ("utils.yolo_utils", "detect_content_boxes"),
    # ⚠️ 下面三个是"状态查询"，也必须登记：否则调用方只能写
    # `utils.yolo_utils.is_model_loaded()`，而那是**靠偶然才成立**的——
    # 只有在某处恰好 `from utils.yolo_utils import ...` 过之后，子模块才会成为
    # utils 包的属性；没跑过那条路径就直接 AttributeError（真实踩过）。
    "model_path": ("utils.yolo_utils", "model_path"),
    "is_model_loaded": ("utils.yolo_utils", "is_model_loaded"),
    "load_seconds_used": ("utils.yolo_utils", "load_seconds_used"),
    "calculate_auto_threshold": ("utils.image_utils", "calculate_auto_threshold"),
    "extract_red_seal": ("utils.image_utils", "extract_red_seal"),
    "apply_otsu_to_region": ("utils.image_utils", "apply_otsu_to_region"),
    "apply_otsu_whole": ("utils.image_utils", "apply_otsu_whole"),
    "rembg_page": ("utils.image_utils", "rembg_page"),
    "parse_border": ("utils.image_utils", "parse_border"),
    "parse_border_mm": ("utils.box_geometry", "parse_border_mm"),
    "compute_final_boxes": ("utils.box_geometry", "compute_final_boxes"),
    "imread": ("utils.image_io", "imread"),
    "imwrite": ("utils.image_io", "imwrite"),
    "draw_boxes": ("utils.box_draw", "draw_boxes"),
    # ⚠️ 登记 `draw_slots` 与 `draw_boxes` **同等重要**：`draw_slots` 吃的是
    #    **槽位**（半幅 2 槽 / 整幅 1 槽，形态信息在里面），名/色由它自己按
    #    槽位给。CLI 的 `detect --save` 与 GUI 的「导出标注图」都走它，所以
    #    两边的标注外观不可能漂移。漏登记会让 `utils.draw_slots` 直接
    #    AttributeError（且报错点离原因很远）。
    "draw_slots": ("utils.box_draw", "draw_slots"),
    "slot_names_colors": ("utils.box_draw", "slot_names_colors"),
    # 第三步提交产物的透明底编码（唯一实现，自带编码形态选择）
    "save_white_as_transparent": ("utils.transparent_png", "save_white_as_transparent"),
    # 变换笼（GIMP 口径）：RBF 位移场局部形变（numpy 延迟导入）。
    # 与下面的 puppet_warp（ARAP 图钉）**并存**，桌面是两个独立工具。
    "perimeter_cage": ("utils.cage_warp", "perimeter_cage"),
    "influence_radius": ("utils.cage_warp", "influence_radius"),
    "moved_handles": ("utils.cage_warp", "moved_handles"),
    "warp_region": ("utils.cage_warp", "warp_region"),
    "cage_moved": ("utils.cage_warp", "cage_moved"),
    "deform": ("utils.cage_warp", "deform"),
    "deform_qimage": ("utils.cage_warp", "deform_qimage"),
    # 操控变形（PS Puppet Warp 口径）：ARAP 网格形变（scipy/numpy 延迟导入）
    "build_mesh": ("utils.puppet_warp", "build_mesh"),
    "grid_cell": ("utils.puppet_warp", "grid_cell"),
    "drag_cell": ("utils.puppet_warp", "drag_cell"),
    "solve_arap": ("utils.puppet_warp", "solve_arap"),
    "solve_puppet": ("utils.puppet_warp", "solve_puppet"),
    "border_vertices": ("utils.puppet_warp", "border_vertices"),
    "nearest_vertex": ("utils.puppet_warp", "nearest_vertex"),
    "puppet_warp": ("utils.puppet_warp", "puppet_warp"),
    "puppet_warp_qimage": ("utils.puppet_warp", "puppet_warp_qimage"),
    "mesh_moved": ("utils.puppet_warp", "mesh_moved"),
    "mesh_region": ("utils.puppet_warp", "mesh_region"),
    # 四点透视校正（古籍页形/拍摄角度摆正，numpy 延迟导入）
    "rectify": ("utils.perspective", "rectify"),
    "rectify_qimage": ("utils.perspective", "rectify_qimage"),
    "homography": ("utils.perspective", "homography"),
    "target_rect": ("utils.perspective", "target_rect"),
    "rectify_region": ("utils.perspective", "rectify_region"),
    "quad_moved": ("utils.perspective", "quad_moved"),
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
