# -*- coding: utf-8 -*-
"""源文件页面提取的常量（quick 判定 / 分辨率 / 后缀）。

从原 ``utils/pdf_extract.py`` 按职责拆出：常量集中在这里，其余子模块只读不写。
"""

from utils.file_utils import SOURCE_DOCUMENT_EXTS
from utils.units import DEFAULT_RENDER_DPI as DEFAULT_UNITS_DPI

# ------------------------------------------------------------------ quick
# quick 模式只在这几种内嵌格式上取巧：它们可以「原样落盘」，零解码零重编码。
# jp2/jbig2/CCITT/tiff 等必须解码再重编码，未必比整页渲染快，且 PIL 缺对应
# 解码器时会整页失败 —— 一律降级为整页渲染。
QUICK_SOURCE_EXTS = {"jpeg", "jpg", "png"}

#: 可以「绕过 MuPDF 整页渲染、直接解码内嵌码流」的格式（JPEG2000 家族）。
#:
#: ⚠️ JPX 解码本身是慢的，但**只解到目标分辨率所需的层数**可以快 2~4 倍
#:    （JPEG2000 的小波分级）；而 MuPDF 的 ``get_pixmap`` 无论目标多大都整帧
#:    解码。只在"整页就是这一张图、页面上没有别的内容"时才成立（见
#:    ``_jpx_page_source`` 的守卫）。
JPX_SOURCE_EXTS = {"jpx", "jp2", "j2k"}

#: JPX 降档解码允许的最低线性覆盖率（解码边长 / 目标边长）。
#: 低于它就别降了——再降会明显变糊；宁可全分辨率解码后缩放。
JPX_REDUCE_MIN_COVERAGE = 0.90

# 内嵌图尺寸低于整页渲染尺寸的这个比例，就认为它是低清缩略图，改用整页渲染
# （渲染不会凭空增加细节，但至少不会比内嵌图更糊）。
QUICK_MIN_COVERAGE = 0.9

# ------------------------------------------------------------------ 分辨率
# 单页输出宽度的硬上限（px）。再大的页面会吃光内存，且下游（rembg/print）
# 也处理不动，所以一律按宽度封顶。
MAX_OUTPUT_WIDTH_PX = 6000

# 页面宽度超过这个 pt 值就认为"已经够宽"，不再按 zoom 放大。
WIDE_PAGE_PT = 3000

# 整页渲染的**目标 DPI 下限**。
#
# 背景（72 DPI 陷阱）：PDF 的页面单位是 pt（1pt = 1/72 inch），PyMuPDF 在
# zoom=1 时 1pt 渲染成 1px —— 也就是 72 DPI。扫描古籍无所谓：quick 模式会
# 直接取内嵌的原图字节，分辨率由扫描件本身决定。但**普通矢量 PDF**（没有
# 内嵌图，或内嵌图不被 quick 接受）只能整页渲染，zoom=1 就只有 72 DPI，
# 去底色后再嵌回打印 PDF 必然发虚。
#
# 因此整页渲染时给一个 DPI 下限：实际 zoom = max(用户 zoom, dpi/72)，
# 仍然受 MAX_OUTPUT_WIDTH_PX 封顶。内嵌图路径不受影响（原图就是原图，
# 不做任何重采样）。
#: 默认渲染 DPI（唯一定义处在 utils/units.py）
DEFAULT_RENDER_DPI = DEFAULT_UNITS_DPI

#: extract 认的源文件后缀（唯一定义处在 utils/file_utils.py）
SOURCE_EXTS = SOURCE_DOCUMENT_EXTS

#: DjVu 后缀；渲染走 djvu-rs 而不是 PyMuPDF。
DJVU_EXTS = (".djvu", ".djv")

#: 允许"直接取内嵌图"的注释子类型：链接不产生像素，不影响产物。
#: 其余注释（高亮/便签/墨迹/图章/表单域）会被整页渲染画进去，必须回退。
IGNORABLE_ANNOT_TYPES = {"Link"}
