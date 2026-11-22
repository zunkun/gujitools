# -*- coding: utf-8 -*-
"""源图尺寸/可见内容框的读取与编辑后的 rect 刷新。

从 ``desktop/services/imposition.py`` 拆出（2026-11-22）：只读图头/alpha，
不解码整页。
"""

from __future__ import annotations

from desktop.services.imposition.sources import same_path

# ------------------------------------------------------------------ 源图与槽位
#: 模块级尺寸缓存：拼版反复读同一批源图的尺寸，缓存量级可控。
_SIZE_CACHE: dict[str, tuple[int, int]] = {}


def image_size(path) -> tuple[int, int]:
    """图片像素尺寸（读文件头，不解码整图）；读不到返回 (0, 0)。"""
    key = str(path)
    cache = _SIZE_CACHE
    if key in cache:
        return cache[key]
    try:
        from PIL import Image

        with Image.open(key) as img:
            size = (int(img.width), int(img.height))
    except Exception:  # noqa: BLE001 - 尺寸读不到交给上层判空
        size = (0, 0)
    cache[key] = size
    return size


def invalidate_size(path) -> None:
    """源图被外部覆盖（图片编辑器写回）后丢掉它的尺寸缓存。

    ⚠️ :func:`image_size` 的缓存**只进不出**：编辑器把图旋转/裁剪后覆盖回
    同一文件，不丢缓存的话后续 :func:`default_items` / :func:`refresh_rects_
    for_edited_source` 读到的还是旧尺寸。
    """
    _SIZE_CACHE.pop(str(path), None)


def image_content_bounds(path) -> tuple[int, int, int, int] | None:
    """源图**可见内容**框 ``(x, y, w, h)``；没有透明留白时返回 None。

    ⚠️ 为什么拼版要按"内容"而不是整张图摆框（2026-10-14 用户报障「弹窗
    编辑保存后，拼版页图片与虚线框错位」）：图片编辑器的**裁剪移动**会把
    位移编码成**透明边距**——像素图因此变大（实测 200×100 → 240×130），
    可见内容缩在其中一个角上。若版面 rect 按整张图尺寸刷，画出来的虚线框
    会把透明留白一并框进去（240×130），而图里看得见的只有 200×100 且偏离
    中心 ⇒ 框比图大一圈、位置也偏，正是截图里的现象。

    整幅不透明（普通扫描件）或读不出 alpha 时返回 ``None``＝"内容就是整
    张图"，调用方按旧口径走，不改变既有版面。读图失败也返回 None。
    """
    try:
        from PIL import Image

        with Image.open(str(path)) as img:
            if img.mode not in ("RGBA", "LA", "PA") and "transparency" not in img.info:
                return None                     # 无 alpha 通道：内容＝整张
            rgba = img.convert("RGBA")
            alpha = rgba.getchannel("A")
            box = alpha.getbbox()
            if box is None:
                return None                     # 全透明：没有可对齐的内容
            if box == (0, 0, img.width, img.height):
                return None                     # 四边都贴着内容：无留白
            x0, y0, x1, y1 = box
            return x0, y0, x1 - x0, y1 - y0
    except Exception:  # noqa: BLE001 - 读不到按"整张图"处理，不瞎改版面
        return None


def refresh_rects_for_edited_source(doc: dict, path_text: str) -> bool:
    """源图被编辑覆盖后，把文档里引用它的 ``rect`` 刷成**新图可见内容**的几何。

    ⚠️⚠️ 版面 ``rect`` 的宽高是**按源图像素**记的（见 :func:`default_items`）。
    编辑器把图旋转 90°（宽高互换）或裁剪后**覆盖回同一文件**，旧 rect 就成了
    压扁新图的"模子"：:func:`compose_page` 会把新图无条件 ``resize`` 回旧
    宽高——旋转 90° 的图被横向压扁（3500px 的宽压进 2480px），既变形又
    清晰度下降（用户 2026-10-10 报障："旋转后拼版里图片被压宽"）。

    规则：宽高取新图**可见内容**的尺寸（见 :func:`image_content_bounds`——
    裁剪移动会把位移编码成透明边距，按整张图刷会让虚线框比图大一圈，
    2026-10-14 报障）。位置＝**旧 rect 中心 + 内容在画布内的偏移**，即

        ``new_rect = [旧中心 - 新内容尺寸/2 + 内容偏移, 新内容尺寸]``

    两项各管一件事，互不干扰：

    - **尺寸变化绕旧中心**（旋转 90°／纯裁剪）：图还待在用户摆的地方，按新
      形状向四周长开/收拢（2026-10-10「旋转后被压宽」的既有口径，保持不变）；
    - **内容偏移量平移**（裁剪"移动"把位移编码成透明边距）：用户拖了 200px
      就整整平移 200px，大小不变。

    ⚠️⚠️ 偏移项**只能是内容框在画布里的左上角 ``(content_x, content_y)``**，
    不要再减 ``整图尺寸/2``（2026-10-14 用户报障「向下移 200px 后图变大了」：
    减掉半张图高把 200 砍成 100，rect 落在 Top1+100 ⇒ 顶部没跟着走、底部长
    出 200px，看着就是"顶部与右图平齐、底部多出一截、左右不等高"）。
    纯尺寸变化时内容偏移为 0，本式退化成既有的绕中心口径，不影响旧行为。
    尺寸与偏移都没变（普通修饰）就一个字节都不动。返回是否有 rect 被改过
    （调用方据此决定要不要落盘/刷视图）。
    """
    invalidate_size(path_text)
    width, height = image_size(path_text)
    if width <= 0 or height <= 0:
        return False                      # 读不到新尺寸：保持原状别瞎改
    # ⚠️ 内容框在**新图像素系**里的左上角与宽高（None = 内容＝整张图）
    bounds = image_content_bounds(path_text)
    if bounds is None:
        content_x, content_y = 0.0, 0.0
        new_w, new_h = float(width), float(height)
    else:
        content_x, content_y, new_w, new_h = (
            float(bounds[0]), float(bounds[1]),
            float(bounds[2]), float(bounds[3]),
        )
    changed = False
    for page in (doc or {}).get("pages") or []:
        for item in page.get("items") or []:
            rect = item.get("rect")
            if not rect or not same_path(item.get("file"), path_text):
                continue
            x, y, w, h = (float(v) for v in rect)
            if (abs(new_w - w) < 0.5 and abs(new_h - h) < 0.5
                    and abs(content_x) < 0.5 and abs(content_y) < 0.5):
                continue                  # 尺寸没变（旋转 0°/纯修饰）：不动
            center_x, center_y = x + w / 2.0, y + h / 2.0
            item["rect"] = [center_x - new_w / 2.0 + content_x,
                            center_y - new_h / 2.0 + content_y, new_w, new_h]
            changed = True
    return changed
