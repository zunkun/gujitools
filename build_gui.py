#!/usr/bin/env python
"""Build the GUI package independently from the CLI package.

Install dependencies first with:
    python -m pip install -r requirements.gui.txt
Then run:
    python build_gui.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    required = ("PySide6", "fitz", "PIL", "yaml", "cv2", "ultralytics")
    missing = []
    for module in required:
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        print(
            "缺少 GUI 打包依赖，请先执行: python -m pip install -r requirements.gui.txt"
        )
        print("缺少: " + ", ".join(missing))
        return 2

    for target in (ROOT / "build-gui", ROOT / "dist" / "guji-gui"):
        if target.exists():
            shutil.rmtree(target)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(ROOT / "guji_gui.spec"),
        "--noconfirm",
        "--clean",
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build-gui"),
    ]
    print("打包 GUI: " + " ".join(command))
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
