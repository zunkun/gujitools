# -*- coding: utf-8 -*-
"""由 PNG 源图生成 Windows 图标（.ico），并统一烧上圆角。

为什么需要它
------------
1. PyInstaller 的 ``icon=``（Windows）只认 .ico，而仓库里只保留 PNG 源图，
   .ico 在构建时生成。
2. **圆角只能烧进像素**——窗口/任务栏/快捷方式图标由 Windows 绘制，Qt 的
   ``setWindowIcon`` 管不了形状。所以源图保持直角即可，圆角在这里统一处理，
   换图标时不用再手工修图。

小尺寸帧为什么要特殊处理
------------------------
直接把大图 LANCZOS 缩到 16px，圆角外的透明会和图形颜色平均成**半透明**，
在浅色标题栏上叠出淡色晕边（实测红章 16px 帧四角 alpha=137，叠白底变成
(214,136,136) 的淡粉边，看着就是"一圈白边"）。

做法是**超采样 + alpha 阈值**：

* 先在 4 倍画布上合成圆角蒙版，再缩小——小尺寸仍能保留正确的圆角覆盖比例；
* 再把 ``alpha < ALPHA_CUT`` 的像素压成全透明，消除半透明晕边。

命令行::

    python tools/make_icon.py                     # 用默认 8% 圆角生成 icon.ico
    python tools/make_icon.py --radius 15         # 15% 圆角
    python tools/make_icon.py --png a.png --ico b.ico
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

# Windows 各场景（资源管理器/任务栏/Alt-Tab）会按需要挑选帧
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

DEFAULT_RADIUS_PCT = 8      # 圆角半径占边长百分比
SUPERSAMPLE = 4             # 超采样倍数：先在大画布做圆角，再缩到目标尺寸
ALPHA_CUT = 140             # alpha 低于此值压成全透明，消除小尺寸半透明晕边
# 小尺寸下固定百分比的圆角不到 1 像素，角像素仍落在图形内 → 四角不透明。
# 保证圆角半径至少 MIN_CORNER_PX 像素，裁掉的角才是真透明（16px 需 ~12%）。
MIN_CORNER_PX = 2.0


def effective_radius_pct(size: int, radius_pct: float) -> float:
    """按帧尺寸自适应圆角比例：小帧按比例放大，保证四角真的被裁掉。"""
    return max(radius_pct, MIN_CORNER_PX / size * 100)


def rounded_frame(
    src: Image.Image,
    size: int,
    radius_pct: float = DEFAULT_RADIUS_PCT,
    supersample: int = SUPERSAMPLE,
    alpha_cut: int = ALPHA_CUT,
) -> Image.Image:
    """把源图裁成 ``size × size`` 的圆角 RGBA 帧（透明底）。"""
    n = size * supersample
    pct = effective_radius_pct(size, radius_pct)
    hi = src.convert("RGBA").resize((n, n), Image.LANCZOS)
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, n - 1, n - 1], radius=int(n * pct / 100), fill=255
    )
    alpha = np.array(hi.getchannel("A")).astype(np.uint16) * np.array(mask)
    hi.putalpha(Image.fromarray((alpha // 255).astype("uint8")))

    out = hi.resize((size, size), Image.LANCZOS)
    arr = np.array(out)
    a = arr[..., 3].astype(int)
    a = np.where(
        a < alpha_cut, 0, np.clip((a - alpha_cut) * 255 // (255 - alpha_cut), 0, 255)
    ).astype("uint8")
    arr[..., 3] = a
    # 透明像素的 RGB 也清零：某些渲染路径按预乘 alpha 处理，残留颜色会透出淡边
    arr[..., :3] = np.where((a == 0)[..., None], 0, arr[..., :3])
    return Image.fromarray(arr)


def make_ico(
    png: Path, ico: Path, radius_pct: float = DEFAULT_RADIUS_PCT
) -> Path:
    """由 PNG 生成多尺寸 .ico（圆角 + 透明底），返回 ico 路径。"""
    src = Image.open(png)
    frames = [rounded_frame(src, s[0], radius_pct) for s in ICO_SIZES]
    frames[-1].save(ico, format="ICO", sizes=ICO_SIZES, append_images=frames[:-1])
    return ico


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="由 PNG 生成圆角透明底 .ico")
    parser.add_argument("--png", default=str(root / "desktop" / "static" / "icon.png"),
                        help="源图（默认 desktop/static/icon.png）")
    parser.add_argument("--ico", default="", help="输出 .ico（默认与源图同名同目录）")
    parser.add_argument("--radius", type=float, default=DEFAULT_RADIUS_PCT,
                        help=f"圆角半径占边长百分比（默认 {DEFAULT_RADIUS_PCT}）")
    args = parser.parse_args()

    png = Path(args.png)
    ico = Path(args.ico) if args.ico else png.with_suffix(".ico")
    if not png.is_file():
        print(f"⚠️ 未找到源图: {png}")
        return 1
    make_ico(png, ico, args.radius)
    print(f"✅ 生成图标: {ico}  （圆角 {args.radius}%，{len(ICO_SIZES)} 个尺寸）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
