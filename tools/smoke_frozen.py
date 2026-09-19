# -*- coding: utf-8 -*-
"""打包产物冒烟测试：确认瘦身后的 dist/guji 仍能完成真实工作。

瘦身（去掉 torch 源码副本、ffmpeg dll、opengl32sw 等）最大的风险是
「删了某个运行期真会读到的东西」，而这类问题只在 frozen 环境暴露。
本脚本在打包后跑真实链路，不把「import 成功」当作通过：

    python tools/smoke_frozen.py

关键项是 `crop`——它走 YOLO 推理（torch + torchvision.ops.nms），正好覆盖
「删除 _internal/torch 源码副本」这个风险最高的动作。

退出码非 0 表示有失败项。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PASSED = 0
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED
    if ok:
        PASSED += 1
        print(f"  [PASS] {name}")
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name}  {detail}")


def run_exe(exe: Path, args: list[str], timeout: int = 900):
    """运行打包后的可执行文件，返回 CompletedProcess。"""
    return subprocess.run(
        [str(exe), *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def make_pdf(path: Path, pages: int = 2) -> None:
    """用 PyMuPDF 造一个每页带一行文字的极简 PDF。"""
    import pymupdf

    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 160), f"smoke page {i + 1}", fontsize=28)
    doc.save(str(path))
    doc.close()


def main() -> int:
    dist = PROJECT_ROOT / "dist" / "guji"
    cli = dist / "guji.exe"

    print("== 产物存在性 ==")
    check("guji.exe 存在", cli.is_file())
    check("guji-desktop.exe 存在", (dist / "guji-desktop.exe").is_file())
    if not cli.is_file():
        print("\n❌ 缺少 guji.exe，请先执行 python build.py")
        return 1

    print("\n== CLI 基本可用 ==")
    r = run_exe(cli, ["--version"])
    check("guji --version 正常退出", r.returncode == 0, (r.stderr or "")[-200:])
    r = run_exe(cli, ["--help"])
    check("guji --help 正常退出", r.returncode == 0, (r.stderr or "")[-200:])

    # ⚠️ 这一段不能省：曾经只在 CLI 上冒烟，漏掉了 GUI 启动即崩的致命问题
    # （qfluentwidgets → qframelesswindow → win32api 被 excludes 排除）。
    # CLI 链不导入 Qt，永远测不出这类问题。
    print("\n== GUI 启动（win32api / Qt 依赖完整性）==")
    gui = dist / "guji-desktop.exe"
    if not gui.is_file():
        check("guji-desktop.exe 存在", False)
    else:
        # GUJI_GUI_SELFTEST=1：主窗口构造后自动退出（见 desktop/app.py）。
        # 不能用"进程还活着"判定成功——windowed 程序没有控制台，导入期崩溃
        # 会弹错误框并永久挂住，看起来和正常启动一模一样。必须看退出码。
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", GUJI_GUI_SELFTEST="1")
        proc = subprocess.Popen(
            [str(gui)],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            code = proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            code = None
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)
        if code is None:
            check(
                "GUI 自检退出（未挂起）",
                False,
                "90s 内未退出：导入期崩溃会弹错误框挂住，"
                "通常是被 excludes 删了必需模块（如 win32api）",
            )
        else:
            check("GUI 自检退出码为 0", code == 0, f"退出码 {code}")

    print("\n== 用户手册：构建期预生成的自包含 HTML ==")
    # ⚠️ 安装包**不含 docs/guide**（md + 截图都不进包），手册必须是单个自包含
    # 文件：截图内联成 data URI，任何外部引用到了用户机器上都是碎图。
    manual = dist / "_internal" / "desktop" / "static" / "manual.html"
    check("desktop/static/manual.html 存在", manual.is_file(), str(manual))
    if manual.is_file():
        doc = manual.read_text(encoding="utf-8", errors="replace")
        inlined = doc.count("data:image/")
        check("手册内联了 12 张截图", inlined == 12, f"实际 {inlined} 张")
        check("手册没有外部图片引用（装机后不会碎图）",
              'src="file:' not in doc and 'src="screenshots/' not in doc)
        check("手册不再引用 md 文档（包内没有 docs/guide）",
              'href="cli.md"' not in doc and 'href="user-guide.md"' not in doc)
    check("docs/guide 没有被打进包（省掉 md 与 6MB 截图）",
          not (dist / "_internal" / "docs" / "guide").exists())
    check("markdown 库没有被打进包（运行时不渲染手册）",
          not (dist / "_internal" / "markdown").exists())

    with tempfile.TemporaryDirectory(prefix="guji_smoke_") as tmp:
        tmp_path = Path(tmp)
        pdf = tmp_path / "src.pdf"
        make_pdf(pdf, pages=2)

        print("\n== extract：PDF → 图片 ==")
        images = tmp_path / "images"
        r = run_exe(cli, ["extract", "-i", str(pdf), "-o", str(images)])
        check("extract 正常退出", r.returncode == 0, (r.stderr or "")[-300:])
        # 输出按「输出根/<pdf名>/images/」分层，必须递归查找
        imgs = sorted(images.rglob("*.jpg")) + sorted(images.rglob("*.png"))
        check("extract 产出 2 张图片", len(imgs) == 2, f"实际 {len(imgs)} 张")

        # rembg/crop 不递归子目录，必须指向 extract 真正落图的那一层
        img_dir = imgs[0].parent if imgs else images

        print("\n== crop：YOLO 推理（torch 源码删除后的关键验证）==")
        cropped = tmp_path / "cropped"
        r = run_exe(cli, ["crop", "-i", str(img_dir), "-o", str(cropped)])
        check(
            "crop 正常退出（torch + YOLO 可用）",
            r.returncode == 0,
            (r.stderr or "")[-400:],
        )
        # 检测不到文本框时不产出文件也属正常，因此只报告数量、不做断言——
        # 「crop 正常退出」已经覆盖了 torch + YOLO 可用性
        outs = (
            list(cropped.rglob("*.jpg")) + list(cropped.rglob("*.png"))
            if cropped.exists()
            else []
        )
        print(f"       （crop 输出 {len(outs)} 个文件；无检测框时为 0 属正常）")

        print("\n== rembg：去底色（cv2 / numpy 路径）==")
        rembg_out = tmp_path / "rembg"
        r = run_exe(cli, ["rembg", "-i", str(img_dir), "-o", str(rembg_out)])
        check("rembg 正常退出", r.returncode == 0, (r.stderr or "")[-300:])
        outs = (
            list(rembg_out.rglob("*.png")) + list(rembg_out.rglob("*.jpg"))
            if rembg_out.exists()
            else []
        )
        check("rembg 产出 2 张结果图", len(outs) == 2, f"实际 {len(outs)} 个文件")

    print()
    if FAILED:
        print(f"❌ {len(FAILED)} 项失败，{PASSED} 项通过：{', '.join(FAILED)}")
        return 1
    print(f"✅ 全部 {PASSED} 项冒烟通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
