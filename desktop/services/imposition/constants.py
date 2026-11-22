# -*- coding: utf-8 -*-
"""拼版的常量：槽位/落盘命名、底色、锁、源图形态键与角色映射。

从 ``desktop/services/imposition.py`` 拆出（2026-11-22）：只放常量，不做
任何计算。槽位/坐标/底色的口径说明见本包 ``__init__``。
"""

from __future__ import annotations

import threading

#: 一页拼版固定两项（右槽、左槽）
ITEMS_PER_PAGE = 2

#: 落盘文件名：``0001.png`` …（列表顺序即页序，与第四步列表一致）
FILE_FMT = "{:04d}.png"
#: 成品页的两种后缀。用户 2026-10-17 口径：**「图片拼版」跟输入源图走**——
#: 输入是 png 就出 png、输入是 jpg 就出 jpg（见 :func:`page_product_suffix`）。
PNG_SUFFIX = ".png"
JPG_SUFFIX = ".jpg"
#: JPEG 成品的编码质量。95 实测与源图同量级观感，体积约为 RGBA PNG 的 40%
#: （6000×4409 的一页：PNG 13.4MB → JPEG 5.4MB）。
JPEG_QUALITY = 95
#: 「算 jpg 族」的源图后缀；**除它以外一律按 png 出**（保住 alpha）。
_JPG_SUFFIXES = frozenset({".jpg", ".jpeg"})
#: 成品页可能的后缀（含 jpeg 别名）：清扫/新鲜度判据都按它认。
_PRODUCT_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})


#: 合成画布的**透明底**（任务流程默认，2026-10-10 用户修订）：白底会烙进成品
#: 页图，编辑器里统一变换/裁剪全带着白底走；PDF 侧
#: ``functions/print._load_image`` 会把 RGBA 压平到白纸，成书效果不变。
TRANSPARENT_BACKGROUND = (0, 0, 0, 0)
#: 合成画布的**白底**（独立拼图页「导出成品」用，2026-10-13 用户）：singletask
#: 导出的 PNG 就是最终交付物，透明底在看图软件里不合理——铺白。
WHITE_BACKGROUND = (255, 255, 255, 255)

#: ``compose_doc`` 的**进程内**互斥锁：按目标目录串行化整轮合成。
#:
#: ⚠️ 为什么需要（用户 2026-10-03 报「程序容易跑崩溃」）：拼版合成有**两条**
#: 路径会打到同一个 ``stages/imposition`` 目录——
#:
#: - 后台防抖合成 ``ImpositionComposeWorker``（拖版面时反复触发）；
#: - 主线程同步合成 ``TaskDetailPage._compose_imposition_now``
#:   （改完版面立刻点「生成PDF」时补一轮）。
#:
#: 原先两条路径**没有任何互斥**：同一个 ``0003.png`` 可能被两个线程同时
#: ``image.save()``（非原子写），第四步 PDF 会读到半张图；更糟的是
#: :func:`_sweep_stale` 会 ``unlink`` 掉序号大的旧文件——一个线程按旧页数
#: 清理、另一个按新页数在写，好内容会被误删。
#:
#: 用**进程内**的模块级锁就够：两条路径都在本进程内（同源），不涉及跨进程。
_COMPOSE_LOCK = threading.Lock()

_CN_DIGITS = "零一二三四五六七八九"

#: 源图形态（``classify_source`` 的返回值）。
SOURCE_LEFT = "left"    # 左半幅：文件名以 ``-l`` / ``_l`` 结尾
SOURCE_RIGHT = "right"  # 右半幅：文件名以 ``-r`` / ``_r`` 结尾
SOURCE_FULL = "full"    # 整幅：无 -l/-r 后缀（fullcontent 页的裁剪产物
#                          不拆半幅，第三步提交产物就是无后缀单文件）
SOURCE_HALF_UNSIDED = "half-unsided"
#: 半幅但**侧别被归一化掉**（单栏书 / 窄页）：产物同样无后缀，与真整幅在
#: 文件名上不可区分。身份只存在于 ``boxes.json`` 的提交计划（``role``）里，
#: 拼版通过 ``auto_impose_pages(role_for=...)`` 查到它之后才敢配对。
#: ⚠️ 不能靠文件名判——这正是 ``-l``/``-r`` 缺失时旧实现把它当整幅的根因。

#: 提交计划里的角色 → 拼版侧的形态键（见 ``desktop.services.print_plan``）。
ROLE_SOURCES: dict[str, str] = {
    "full": SOURCE_FULL,
    "half-left": SOURCE_LEFT,
    "half-right": SOURCE_RIGHT,
    "half-unsided": SOURCE_HALF_UNSIDED,
}
