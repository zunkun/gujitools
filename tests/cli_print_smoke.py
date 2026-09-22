# -*- coding: utf-8 -*-
"""CLI 冒烟：真跑一次 `guji run print`，验证生成的 PDF 与默认值。

为什么单独有这个脚本：`tests/gui_selftest.py` 覆盖桌面端、
`reporter_cli_parity.py` / `reporter_worker_e2e.py` 只跑
extract / detect / rembg——**print 一次都没跑过**。于是动了
`functions/print.py`（换 import 来源、改默认值兜底）时，三条回归
判据全绿，CLI 侧却没人验过。

用法：python tests/cli_print_smoke.py

⚠️ CLI 的两个坑（踩过）：
* `guji run print` **不接受 `-i/-o`**，参数全部来自 `--config <yaml>`；
* `--help` **不支持子命令**：`guji run print --help` 会输出
  "No help available for this topic: run."。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PY = sys.executable
TMP = Path(tempfile.gettempdir()) / "guji_cli_smoke"
IMG = TMP / "in"

_fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = "OK  " if cond else "FAIL"
    print(f"  [{tag}] {name}" + (f"   {detail}" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def run(args: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(
        [PY, "cli.py"] + args, cwd=str(ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return p.returncode, p.stdout, p.stderr


def _make_pages(count: int = 4) -> None:
    """造几张白底黑边框的假页，够 print 排版用。"""
    IMG.mkdir(parents=True, exist_ok=True)
    if list(IMG.glob("*.png")):
        return
    from PIL import Image, ImageDraw
    for i in range(1, count + 1):
        im = Image.new("RGB", (600, 900), "white")
        ImageDraw.Draw(im).rectangle([40, 40, 560, 860], outline="black", width=3)
        im.save(IMG / f"{i:04d}.png")


def main() -> int:
    _make_pages()

    print("== 1. 顶层 help ==")
    rc, out, err = run(["--help"])
    check("guji --help 退出码 0", rc == 0, f"rc={rc} err={err[-300:]}")
    check("帮助里列出 print", "print" in out)
    check("帮助里说明 print 只能 guji run print", "guji run print" in out)

    print()
    print("== 2. 真跑一次 guji run print（走 yaml 配置）==")
    out_dir = TMP / "out"
    cfg = TMP / "guji.yaml"
    cfg.write_text(
        "print:\n"
        f"  input: {IMG.as_posix()}\n"
        f"  output: {out_dir.as_posix()}\n"
        '  pdf_name: "smoke.pdf"\n'
        '  title_text: "冒烟书"\n'
        "  title_printing: true\n"
        "  page_number_printing: true\n",
        encoding="utf-8",
    )
    rc, out, err = run(["run", "print", "--config", str(cfg)])
    check("run print 退出码 0", rc == 0,
          f"rc={rc}\nSTDOUT:\n{out[-900:]}\nSTDERR:\n{err[-900:]}")

    found = sorted(out_dir.rglob("*.pdf")) if out_dir.exists() else []
    check("产出 PDF", bool(found), f"目录={[p.name for p in (out_dir.rglob('*') if out_dir.exists() else [])][:20]}")
    if found:
        pdf = found[0]
        check("PDF 文件名正确", pdf.name == "smoke.pdf", pdf.name)
        check("PDF 非空（>2KB）", pdf.stat().st_size > 2000, f"size={pdf.stat().st_size}")
        check("PDF 魔数 %PDF-", pdf.open("rb").read(5).startswith(b"%PDF-"))

    print()
    print("== 3. print 默认值（CLI 与 desktop 共用的唯一来源）==")
    from core.command_spec import PRINT_DEFAULTS

    check("title_font_size 默认 20", PRINT_DEFAULTS["title_font_size"] == 20,
          str(PRINT_DEFAULTS["title_font_size"]))
    check("page_number_font_size 默认 20", PRINT_DEFAULTS["page_number_font_size"] == 20,
          str(PRINT_DEFAULTS["page_number_font_size"]))
    check("title_margins 默认 [20,10,0,10]",
          list(PRINT_DEFAULTS["title_margins"]) == [20, 10, 0, 10],
          str(PRINT_DEFAULTS["title_margins"]))
    check("page_number_margins 默认 [0,10,20,10]",
          list(PRINT_DEFAULTS["page_number_margins"]) == [0, 10, 20, 10],
          str(PRINT_DEFAULTS["page_number_margins"]))
    # ⚠️ 两段文字的 margins 不能是同一个 list 对象（PRINT_FORM_DEFAULTS 各拷一份）
    check("两段 margins 不是同一 list 对象",
          PRINT_DEFAULTS["title_margins"] is not PRINT_DEFAULTS["page_number_margins"])

    print()
    print("=" * 60)
    if _fails:
        print(f"❌ {len(_fails)} 项失败：{_fails}")
        return 1
    print("CLI 冒烟全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
