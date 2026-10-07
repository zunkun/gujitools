# -*- coding: utf-8 -*-
"""``image_zoom_dialog`` 拆成子包后的不变量守卫。

``desktop/components/viewers/image_zoom_dialog.py``（1246 行）已按**职责**
拆成子包（2026-10-07）：

```text
image_zoom_dialog/
├── consts.py   缩放档位/渲染密度/尺寸常量
├── icons.py    朝向变换矩阵 + 自绘翻转/旋转图标
├── io.py       下载另存 / 原子覆盖原图
├── canvas.py   ZoomTarget + ZoomableCanvas
├── dialog.py   ImageZoomDialog
└── popup.py    宿主侧 ZoomPopupMixin
```

这里钉三件事：**子包结构真的存在**、**对外 API 名字照旧可导入**、
**旧的单文件模块已不存在**（防止有人把文件又加回来造成"两份实现"）。
"""

from pathlib import Path

NAME = "image_zoom_dialog_split"
DEPENDS: list[str] = []
TITLE = "图片预览弹窗拆分（子包）"

_ROOT = Path(__file__).resolve().parents[2]
_VIEWERS = _ROOT / "desktop" / "components" / "viewers"
_PKG = _VIEWERS / "image_zoom_dialog"

#: 子包必须存在的模块。
_REQUIRED_FILES = [
    "__init__.py", "consts.py", "icons.py", "io.py",
    "canvas.py", "dialog.py", "popup.py",
]

#: 对外 API：外部（生产代码 + 测试）实际导入的名字，一个都不能少。
_PUBLIC_API = [
    "ImageZoomDialog", "ZoomPopupMixin", "ZoomTarget", "ZoomableCanvas",
    "MAX_RENDER_EDGE", "MAX_ZOOM", "MIN_RENDER_EDGE", "MIN_ZOOM",
    "PAN_MARGIN_RATIO", "RENDER_HEADROOM", "ZOOM_DIALOG_SIZE", "ZOOM_STOPS",
    "overwrite_image_file", "save_image",
]

#: 四个宿主查看器（混入 ZoomPopupMixin），拆包后仍要能导入。
_HOSTS = [
    ("image_viewer", "ImageViewerWidget"),
    ("pdf_viewer", "PdfViewerWidget"),
    ("rembg_viewer", "RembgPreviewWidget"),
    ("print_preview", "PrintPreviewWidget"),
]


def run(ctx) -> None:
    from tests.selftests._context import ok

    # ---- 0. 拆分是真的 ----
    missing = [p for p in _REQUIRED_FILES if not (_PKG / p).is_file()]
    ok("image_zoom_dialog 已是子包，且各拆分模块都在",
       not missing, f"缺={missing}")

    ok("旧的单文件 image_zoom_dialog.py 已不存在（避免两份实现）",
       not (_VIEWERS / "image_zoom_dialog.py").exists(), "旧文件又出现了")

    # ---- 1. 对外 API 不变 ----
    import desktop.components.viewers.image_zoom_dialog as mod

    absent = [n for n in _PUBLIC_API if not hasattr(mod, n)]
    ok("对外 API 名字照旧可导入", not absent, f"缺失={absent}")

    # ---- 2. 宿主查看器仍能导入，且 MRO 正常 ----
    import importlib

    bad: dict[str, str] = {}
    for fname, clsname in _HOSTS:
        try:
            host_mod = importlib.import_module(
                f"desktop.components.viewers.{fname}"
            )
            getattr(host_mod, clsname)
        except Exception as exc:  # noqa: BLE001
            bad[fname] = f"{type(exc).__name__}: {exc}"
    ok("四个宿主查看器仍能导入（含 ZoomPopupMixin）", not bad, f"失败={bad}")
