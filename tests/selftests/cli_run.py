# -*- coding: utf-8 -*-
"""CLI 入口级端到端：从 ``python cli.py <command>``（打包后即 ``guji``）真跑到产物落盘。

为什么必须有这个模块（2026-10-12 测试审计的最大缺口）
    之前六命令的断言全部落在「参数校验 / 几何 / 规格一致性」层，唯一真跑过
    CLI 入口的只有非转正的 ``tests/cli_print_smoke.py``（且仅 print）。动了
    ``functions/`` 或 ``cli/`` 时，L0/L1 判据全绿也可能把入口跑挂——本模块
    就是那道兜底网（判据原为 cli_print_smoke，2026-10-12 转正并入）。

覆盖：
1. 退出码/帮助约定：--help rc=0、guji help <cmd> rc=0、未知命令 rc!=0、
   拼错参数 rc!=0（2026-09-26 审计：拼错参数曾警告后照跑还 rc=0）；
2. extract 端到端：真 PDF → 页图落盘；
3. rembg：去底色产物为二值图；
4. cropremove：复合命令产物存在且为二值图；
5. print：yaml 配置 → 真生成 PDF（魔数/大小/文件名）；
6. detect / crop（需要 YOLO）：模型可用时真跑，不可用时**显式打印 SKIP**
   （跳过必须可见，不许静默）。

⚠️ 全部走 ``subprocess.run``——沙箱里 Qt QProcess 起不来是环境问题，但
   subprocess 不受影响，所以本模块在沙箱/本机都能跑。临时文件统一落
   tests/tmp/（tmpdir.install 已覆盖子进程环境）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

NAME = "cli_run"
DEPENDS: list[str] = []
TITLE = "CLI 入口端到端（六命令真跑到产物）"

W, H = 600, 900


def _run(args: list[str]) -> tuple[int, str, str]:
    """真跑一次 CLI：cwd 固定在仓库根（等价打包后的 guji <args>）。"""
    root = Path(__file__).resolve().parents[2]
    p = subprocess.run(
        [sys.executable, "cli.py"] + args, cwd=str(root),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return p.returncode, p.stdout, p.stderr


def _png(path: Path, color) -> Path:
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (W, H), color)
    # 画个黑边框 + 一块"墨字"，让 crop/rembg 有内容可处理
    ImageDraw.Draw(im).rectangle([40, 40, W - 40, H - 40], outline=(0, 0, 0), width=3)
    ImageDraw.Draw(im).rectangle([80, 100, 300, 160], fill=(0, 0, 0))
    im.save(path)
    return path


def _images(root: Path) -> list[Path]:
    """收集目录下全部页图（quick 模式提内嵌图是 jpg、整页渲染默认 png，别写死一种）。"""
    if not root.exists():
        return []
    out: list[Path] = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.tiff"):
        out.extend(root.rglob(ext))
    return sorted(out)


def run(ctx) -> None:
    from tests.selftests._context import ok
    from tests.selftests._context import make_pdf

    tmp = Path(ctx.tmp) / "cli_run"
    tmp.mkdir(parents=True, exist_ok=True)

    _check_conventions(ok)
    extract_dir = _check_extract(ok, tmp, make_pdf)
    _check_rembg(ok, tmp, extract_dir)
    _check_print(ok, tmp)
    _check_yolo_commands(ok, tmp, extract_dir)


def _check_conventions(ok) -> None:
    """退出码与帮助约定：拼错参数必须失败，帮助必须成功。"""
    rc, out, err = _run(["--help"])
    ok("guji --help 退出码 0", rc == 0, f"rc={rc} err={err[-200:]}")
    ok("帮助里列出六个命令",
       all(c in out for c in ("extract", "crop", "rembg", "cropremove", "print")),
       str(out[-300:]))

    rc, out, err = _run(["help", "crop"])
    ok("guji help crop 退出码 0（手册来自 docs/functions）", rc == 0, f"rc={rc} err={err[-200:]}")

    rc, out, err = _run(["no_such_command"])
    ok("未知命令退出码非 0", rc != 0, f"rc={rc}")

    # 2026-09-26 审计：拼错参数曾"警告后照跑 + rc=0"，必须当错误拒绝
    rc, out, err = _run(["rembg", "-i", "x.png", "--bordr", "1"])
    ok("拼错参数（--bordr）退出码非 0 且有提示", rc != 0,
       f"rc={rc} out={out[-200:]} err={err[-200:]}")


def _check_extract(ok, tmp: Path, make_pdf) -> Path:
    """extract：真 PDF → 页图落盘，返回页图目录（<out>/<PDF名>/images/）。

    ⚠️ 返回 images 子目录而非输出根：下游 crop/rembg 的**目录输入只认顶层
    图片**（不递归），实际使用就是把上一步 images 目录喂给下一步。
    """
    pdf = make_pdf(tmp / "古籍样例.pdf", 3)
    out_root = tmp / "e2e_extract"
    rc, out, err = _run([
        "extract", "-i", str(pdf), "-o", str(out_root),
        "--pages", "1-2", "--workers", "2",
    ])
    ok("guji extract 退出码 0", rc == 0,
       f"rc={rc}\nSTDOUT 尾部:\n{out[-600:]}\nSTDERR 尾部:\n{err[-600:]}")
    imgs = _images(out_root)
    ok("extract 产出 2 张页图（--pages 1-2），落 <out>/<PDF名>/images/",
       len(imgs) == 2, f"找到 {[p.name for p in imgs]}")
    from PIL import Image
    if imgs:
        with Image.open(imgs[0]) as im:
            ok("页图尺寸非空", im.width > 0 and im.height > 0, f"{im.size}")
    return imgs[0].parent if imgs else out_root


def _check_rembg(ok, tmp: Path, extract_dir: Path) -> None:
    """rembg：产物为二值图（type=1 = 8 位二值）。"""
    out_root = tmp / "e2e_rembg"
    rc, out, err = _run([
        "rembg", "-i", str(extract_dir), "-o", str(out_root), "--type", "1",
    ])
    ok("guji rembg 退出码 0", rc == 0,
       f"rc={rc}\nSTDOUT 尾部:\n{out[-600:]}\nSTDERR 尾部:\n{err[-600:]}")
    imgs = _images(out_root)
    ok("rembg 产物与输入页数一致", len(imgs) == 2,
       f"找到 {[p.name for p in imgs]}")
    if imgs:
        from PIL import Image
        with Image.open(imgs[0]) as im:
            vals = set(im.convert("L").getdata())
        ok("type=1 产物是二值图（灰度只含 0/255）",
           vals.issubset({0, 255}) and 255 in vals,
           f"去重后 {len(vals)} 个灰度值，样例 {sorted(vals)[:8]}")

    # 输入完好性：rembg 不许碰输入目录（output_dir_safety 的正向补集）
    src_after = _images(extract_dir)
    ok("rembg 跑完输入目录完好", len(src_after) == 2, str(src_after))


def _check_print(ok, tmp: Path) -> None:
    """print：yaml 配置 → 真生成 PDF（guji run print 不接受 -i/-o）。"""
    img_dir = tmp / "print_in"
    img_dir.mkdir(parents=True, exist_ok=True)
    for i in (1, 2):
        _png(img_dir / f"{i:04d}.png", (255, 255, 255))
    out_dir = tmp / "e2e_print"
    cfg = tmp / "guji_print.yaml"
    cfg.write_text(
        "print:\n"
        f"  input: {img_dir.as_posix()}\n"
        f"  output: {out_dir.as_posix()}\n"
        '  pdf_name: "e2e.pdf"\n',
        encoding="utf-8",
    )
    rc, out, err = _run(["run", "print", "--config", str(cfg)])
    ok("guji run print 退出码 0", rc == 0,
       f"rc={rc}\nSTDOUT 尾部:\n{out[-600:]}\nSTDERR 尾部:\n{err[-600:]}")
    pdfs = sorted(out_dir.rglob("*.pdf")) if out_dir.exists() else []
    ok("print 产出 PDF", bool(pdfs), f"目录内容={[p.name for p in out_dir.rglob('*')][:20]}")
    if pdfs:
        ok("PDF 文件名取自 pdf_name", pdfs[0].name == "e2e.pdf", pdfs[0].name)
        ok("PDF 非空且魔数正确",
           pdfs[0].stat().st_size > 2000
           and pdfs[0].open("rb").read(5).startswith(b"%PDF-"),
           f"size={pdfs[0].stat().st_size}")


def _check_yolo_commands(ok, tmp: Path, extract_dir: Path) -> None:
    """detect / crop / cropremove：需要 YOLO。模型不可用时显式 SKIP（不许静默）。

    ⚠️ torch 探测必须走**子进程**：在自测主进程（已加载 Qt）里 import torch
    会撞 OpenMP 双运行时直接把进程干崩（退出码 3，OMP: Error #15）。
    """
    probe = subprocess.run(
        [sys.executable, "-c", "import torch"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "KMP_DUPLICATE_LIB_OK": "TRUE"},
    )
    if probe.returncode != 0:
        print(f"  [SKIP] detect / crop / cropremove：本机 torch 不可用"
              f"（{probe.stderr.strip().splitlines()[-1] if probe.stderr.strip() else probe.returncode}），"
              "YOLO 类 CLI 端到端留待有模型的环境跑")
        return
    weights = sorted((Path(__file__).resolve().parents[2] / "static").rglob("*.pt"))
    if not weights:
        print("  [SKIP] detect / crop / cropremove：static/ 下（含 weights/）无权重文件")
        return

    out_root = tmp / "e2e_detect"
    rc, out, err = _run([
        "detect", "-i", str(extract_dir), "-o", str(out_root), "--save",
    ])
    ok("guji detect --save 退出码 0", rc == 0,
       f"rc={rc}\nSTDOUT 尾部:\n{out[-600:]}\nSTDERR 尾部:\n{err[-600:]}")
    annot = _images(out_root)
    ok("detect --save 产出标注图（每页一张）", len(annot) == 2,
       f"找到 {[p.name for p in annot]}")

    crop1 = tmp / "e2e_crop1"
    rc, out, err = _run(["crop", "-i", str(extract_dir), "-o", str(crop1)])
    ok("guji crop（真 YOLO 检测）退出码 0", rc == 0,
       f"rc={rc}\nSTDOUT 尾部:\n{out[-600:]}\nSTDERR 尾部:\n{err[-600:]}")
    imgs = _images(crop1)
    ok("crop 有产物（无框页也输出原图；有框页逐框输出）", len(imgs) >= 2,
       f"找到 {[p.name for p in imgs]}")

    croprm = tmp / "e2e_cropremove"
    rc, out, err = _run([
        "cropremove", "-i", str(extract_dir), "-o", str(croprm), "--type", "1",
    ])
    ok("guji cropremove（真 YOLO 检测）退出码 0", rc == 0,
       f"rc={rc}\nSTDOUT 尾部:\n{out[-600:]}\nSTDERR 尾部:\n{err[-600:]}")
    rm_imgs = _images(croprm)
    ok("cropremove 有产物", len(rm_imgs) >= 2,
       f"找到 {[p.name for p in rm_imgs]}")
    if rm_imgs:
        from PIL import Image
        with Image.open(rm_imgs[0]) as im:
            vals = set(im.convert("L").getdata())
        ok("cropremove type=1 产物是二值图", vals.issubset({0, 255}),
           f"去重后 {len(vals)} 个灰度值")
