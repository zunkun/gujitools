# -*- coding: utf-8 -*-
"""提交产物透明底自测：白底必须转透明、编码取最省形态、缩略图不变黑。

契约来源（2026-09-30 用户要求）：「无论 type 是什么，提交产物的黑字白底里，
白底一律改成透明」。规则与编码形态的唯一实现在 ``utils/transparent_png.py``，
落盘在 ``desktop/stages/rembg_stage.py``（合成之后，因为合成画布是**不透明白**
填充，在去底计算处加透明会被它压掉）。

⚠️ 自测用的样例页是空白页（pymupdf 默认字体渲染不出中文），所以「墨色不透明」
只能在**合成数组**上验（见下方单元段），不能拿链路产物验。
"""

NAME = "rembg_transparent"
DEPENDS: list[str] = ["rembg"]
TITLE = "提交产物透明底"


def _ihdr(path) -> tuple[int, int]:
    """PNG 头里的 (位深, 颜色类型)：3=调色板、6=RGBA。"""
    head = path.read_bytes()[:26]
    return head[24], head[25]


def _source(rel: str) -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[2] / rel).read_text(encoding="utf-8")


def run(ctx) -> None:
    import shutil
    import tempfile
    from pathlib import Path
    from typing import cast

    import numpy as np
    from PIL import Image

    from tests.selftests._context import ok
    from utils.transparent_png import (
        describe_encoding, save_white_as_transparent,
    )

    repo = ctx.repo
    tid = ctx.tid
    finals = sorted(repo.rembg_output_dir(tid).glob("*.png"))
    ok("提交产物存在（依赖 rembg 模块已提交）", len(finals) > 0, str(len(finals)))

    # ---- 1. 真实产物：白底必须透明，且取最省形态 ----
    for path in finals:
        depth, ctype = _ihdr(path)
        with Image.open(path) as im:
            im.load()
            rgba = np.array(im.convert("RGBA"))
        white = (rgba[:, :, :3] == 255).all(axis=2)
        ok(f"{path.name} 白底像素 α=0", bool((rgba[:, :, 3][white] == 0).all()))
        ok(f"{path.name} 透明区 RGB 仍 255（第四步缩略图不会变黑底）",
           bool((rgba[:, :, :3][white] == 255).all()))
        ok(f"{path.name} 是调色板 PNG 且位深 ≤2（灰阶走最省编码）",
           ctype == 3 and depth <= 2, f"位深={depth} 颜色类型={ctype}")

    # ---- 2. 单元：四类输入的编码形态 + α 正确性（判据同源） ----
    h, w = 60, 80
    cases = [
        ("纯黑白", [(0, (0, 0, 0))], "P", 1),
        ("灰度", [(64, (64, 64, 64)), (128, (128, 128, 128))], "P", 2),
        ("彩色印章", [(178, (178, 34, 34))], "RGBA", 8),
    ]
    # 单元用例落系统临时目录：**不许写进任务目录**（那里任何多余文件都会干扰
    # 其它模块对 stages/ 与任务目录的枚举断言）。
    tmp_dir = Path(tempfile.mkdtemp(prefix="guji_alpha_case_"))
    for tag, ink, expect_enc, expect_bits in cases:
        arr = np.full((h, w, 3), 255, np.uint8)   # 白底
        for i, (_value, rgb) in enumerate(ink):
            arr[i * 10:(i + 1) * 10, 0:10] = rgb  # 若干块"墨"
        dst = tmp_dir / f"{tag}.png"
        info = save_white_as_transparent(arr, dst)
        depth, ctype = _ihdr(dst)
        with Image.open(dst) as im:
            im.load()
            rgba = np.array(im.convert("RGBA"))
        white = (rgba[:, :, :3] == 255).all(axis=2)
        wanted_ink = ~white
        _enc = describe_encoding(arr)
        assert _enc is not None
        ok(f"单元/{tag} 编码形态与判据同源",
           info["encoding"] == expect_enc and depth == expect_bits
           and (_enc["bits"] == info["bits"]),
           f"{info} 位深={depth}")
        ok(f"单元/{tag} 白底透明、墨色不透明且 RGB 逐位不变",
           bool((rgba[:, :, 3][white] == 0).all())
           and bool((rgba[:, :, 3][wanted_ink] == 255).all())
           and bool(np.array_equal(rgba[:, :, :3][wanted_ink], arr[wanted_ink])))

    # ---- 3. 单元：非连续（负步长）输入也必须正确 ----
    # 阶段侧传的就是 `[:, :, 2::-1]` 的视图；曾因返回 Qt 缓冲区的视图
    # 而读到已释放内存（产物混进随机彩色像素、重则段错误）。
    bgra = np.full((h, w, 4), 255, np.uint8)
    bgra[:, :, 1] = 128          # BGRA 的 G
    bgra[:, :, 0] = 0            # BGRA 的 B → 视图里变成 R=0
    view = bgra[:, :, 2::-1]
    dst_view = tmp_dir / "视图.png"
    dst_cont = tmp_dir / "连续.png"
    save_white_as_transparent(view, dst_view)
    save_white_as_transparent(np.ascontiguousarray(view), dst_cont)
    with Image.open(dst_view) as im:
        im.load()
        view_px = np.array(im.convert("RGBA"))
    ok("单元/负步长视图与连续数组产物逐字节一致",
       dst_view.read_bytes() == dst_cont.read_bytes())
    ok("单元/负步长视图像素为 (255,128,0) 而非随机彩色（不读已释放缓冲）",
       tuple(int(v) for v in view_px[0, 0][:3]) == (255, 128, 0)
       and int(view_px[0, 0][3]) == 255,
       str(tuple(int(v) for v in view_px[0, 0])))

    # ---- 4. 单一定义处：提交阶段不许绕过 utils.transparent_png 直接 save ----
    stage_src = _source("desktop/stages/rembg_stage.py")
    ok("rembg_submit 阶段不再直接 out.save(...PNG)",
       ".save(str(dst)" not in stage_src and 'out.save(' not in stage_src)
    ok("rembg_submit 阶段走 utils.save_white_as_transparent",
       "save_white_as_transparent" in stage_src)
    ok("透明底判据只有一个出处（阶段侧不自己写白值比较）",
       "WHITE_LEVEL" not in stage_src and "== 255" not in stage_src
       and "WHITE_LEVEL = 255" in _source("utils/transparent_png.py"))

    # ---- 5. 第四步缩略图仍是白底（透明底不许把加速件带黑） ----
    thumbs = sorted(repo.rembg_thumbnails_dir(tid).glob("*.jpg"))
    ok("第四步缩略图数量与最终图一致", len(thumbs) == len(finals) > 0)
    ok("缩略图底色为白（JPEG 丢 α 取 RGB，不能被清零成黑底）",
       all(min(cast(tuple[int, ...], Image.open(t).convert("RGB").getpixel((2, 2)))) > 200
           for t in thumbs))

    shutil.rmtree(tmp_dir, ignore_errors=True)
