# -*- coding: utf-8 -*-
"""图片拼版的派生与合成规则（纯函数 + PIL，无 Qt 依赖，便于独立测试）。

一句话职责：**把每页的两张源图按版面摆到指定底色上**（任务流程默认透明底，
独立拼图页「导出成品」白底，见 :data:`TRANSPARENT_BACKGROUND` /
:data:`WHITE_BACKGROUND`），落成 ``stages/imposition`` 里的成品页图，供第四步
「PDF排版」当整页图片直接用。

三件事在这里定死（别在别处再写一份）：

1. **槽位约定**：一页拼版恒两项，``items[0]`` = **右槽**、``items[1]`` = **左槽**。
   用户口径「序号排前面的在右侧、序号大的在左侧」——所以按源清单顺序取两张
   （序号小的在前）时，序号小的进右槽。
2. **坐标口径**：``rect`` 是**源图像素**，左上原点、x 向右、y 向下；
   ``rotation`` 是**顺时针角度**（Qt 口径；PIL 侧取负），绕该项 ``rect`` 的中心。
3. **没有"纸张"**（用户 2026-09-30：「这个拼版不需要设置纸张，只需要背景是白色的
   就行，后续提交的时候根据图片的四个区域合并出一张图片」；⚠️ 2026-10-10 修订：
   背景**不再铺白**，改透明底——白底会烙进成品页图，编辑器里统一变换/裁剪
   全都带着白底走。PDF 侧 ``functions/print._load_image`` 会把 RGBA 压平到
   白纸，成书效果不变；⚠️ 2026-10-13 再修订：独立拼图页「导出成品」是
   **白底**（``WHITE_BACKGROUND``）——singletask 导出的 PNG 就是交付物，
   透明底不合理；透明底仍只是任务流程的默认）：版面只有底，图可以随意
   移动/拉伸；
   **产出图 = 所有图外接框的紧裁**（``page_bounds`` → ``compose_page``），
   所以加多少留白、挪多远，用户自己说了算。

2026-11-22 起按职责拆成子包（与本仓 ``utils/pdf_extract/`` 同一模式）：

1. ``constants``：槽位/命名/底色/锁/形态键常量；
2. ``sources``  ：源图路径比较与形态判定；
3. ``document`` ：文档收敛、页级查询与成品命名；
4. ``images``   ：尺寸/可见内容框读取与编辑后的 rect 刷新；
5. ``layout``   ：默认版面与编辑器回传写回；
6. ``auto``     ：自动拼版的配对规则；
7. ``compose``  ：单页/整轮合成与落盘。

⚠️ 本 ``__init__`` 只做重导出：既有 ``from desktop.services.imposition
import X`` 全部不变，子模块之间不要反过来导入本包（会形成循环）。
"""

from desktop.services.imposition.auto import (
    auto_impose_pages,
    expand_role_aliases,
    source_kind,
)
from desktop.services.imposition.compose import (
    _BINARY_CACHE,
    _HARDEN_LUT,
    _drop_other_format,
    _flatten_white,
    _harden_alpha,
    _item_box,
    _looks_binary,
    _open_rgba,
    _report_page,
    _save_page_atomic,
    _sweep_stale,
    _trim_to_content,
    compose_doc,
    compose_page,
    flatten_onto_background,
    is_binary_source,
    page_bounds,
    source_stamp,
)
from desktop.services.imposition.constants import (
    FILE_FMT,
    ITEMS_PER_PAGE,
    JPEG_QUALITY,
    JPG_SUFFIX,
    PNG_SUFFIX,
    ROLE_SOURCES,
    SOURCE_FULL,
    SOURCE_HALF_UNSIDED,
    SOURCE_LEFT,
    SOURCE_RIGHT,
    TRANSPARENT_BACKGROUND,
    WHITE_BACKGROUND,
    _CN_DIGITS,
    _COMPOSE_LOCK,
    _JPG_SUFFIXES,
    _PRODUCT_SUFFIXES,
)
from desktop.services.imposition.document import (
    _num,
    _rect,
    cn_page_label,
    excluded_files,
    is_product_file,
    normalize_doc,
    normalize_page,
    page_product_suffix,
    page_source_stems,
    product_path,
    remaining_files,
    removed_source_files,
    used_source_files,
)
from desktop.services.imposition.images import (
    _SIZE_CACHE,
    image_content_bounds,
    image_size,
    invalidate_size,
    refresh_rects_for_edited_source,
)
from desktop.services.imposition.layout import (
    append_item_to_page,
    apply_editor_layout,
    default_items,
    make_page,
    make_single_page,
    page_has_file,
    pages_having_file,
    same_path,
    single_items,
)
from desktop.services.imposition.sources import (
    _path_key,
    _role_page_key,
    classify_source,
    source_page_number,
)

__all__ = [
    "FILE_FMT",
    "ITEMS_PER_PAGE",
    "JPEG_QUALITY",
    "JPG_SUFFIX",
    "PNG_SUFFIX",
    "ROLE_SOURCES",
    "SOURCE_FULL",
    "SOURCE_HALF_UNSIDED",
    "SOURCE_LEFT",
    "SOURCE_RIGHT",
    "TRANSPARENT_BACKGROUND",
    "WHITE_BACKGROUND",
    "append_item_to_page",
    "apply_editor_layout",
    "auto_impose_pages",
    "classify_source",
    "cn_page_label",
    "compose_doc",
    "compose_page",
    "default_items",
    "excluded_files",
    "expand_role_aliases",
    "flatten_onto_background",
    "image_content_bounds",
    "image_size",
    "invalidate_size",
    "is_binary_source",
    "is_product_file",
    "make_page",
    "make_single_page",
    "normalize_doc",
    "normalize_page",
    "page_bounds",
    "page_has_file",
    "page_product_suffix",
    "page_source_stems",
    "pages_having_file",
    "product_path",
    "refresh_rects_for_edited_source",
    "remaining_files",
    "removed_source_files",
    "same_path",
    "single_items",
    "source_kind",
    "source_page_number",
    "source_stamp",
    "used_source_files",
]
