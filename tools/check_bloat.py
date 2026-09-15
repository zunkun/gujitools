# -*- coding: utf-8 -*-
"""打包产物瘦身校验：确认 dist/guji/_internal 不含已判定无用的内容。

与 build.py 的 prune_bloat() 配套。单测只能守住源码，守不住打包产物——
hook 的行为会随 PyInstaller / torch 版本变化，很容易悄悄把几十 MB 无用
内容带回来。构建后跑一次这个脚本即可发现：

    python tools/check_bloat.py              # 检查并打印体积
    python tools/check_bloat.py --json       # 机器可读输出

退出码非 0 表示存在应被清理的内容。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 这些文件一旦出现，说明瘦身没生效或又被引回来了
FORBIDDEN_FILES = [
    ("cv2/opencv_videoio_ffmpeg500_64.dll",
     "cv2 视频编解码：项目只用 imread/imwrite 等图像 API，不碰视频"),
    ("PySide6/opengl32sw.dll",
     "Qt 软件 OpenGL 回退：界面不依赖 OpenGL"),
    ("torch/bin/protoc.exe",
     "protobuf 编译器：构建期工具，运行期不执行"),
    ("sqlite3.dll",
     "SQLite：旧数据迁移已移除，存储一直是纯 JSON"),
    ("_sqlite3.pyd",
     "SQLite：同上"),
]

# torch 源码副本：hook-torch.py 把它们当 data 收进 _internal，
# 而运行时由 FrozenImporter 从 PYZ 加载，磁盘这份是纯重复。
FORBIDDEN_GLOBS = [
    ("torch/*.py", "torch 源码副本（真实加载走 PYZ）"),
]

# 反向守卫：瘦身不能把**运行期必需**的模块也瘦掉。
# 曾经把 win32api 写进 excludes → GUI 启动即崩
# （qframelesswindow/utils/win32_utils.py:9 顶层 import win32api）。
# 这里在构建产物里逐个核对其存在性，比等用户双击才崩要早得多。
REQUIRED_GLOBS = [
    ("win32/win32api.pyd", "pywin32：qframelesswindow/utils/win32_utils.py 顶层依赖"),
    ("win32/win32gui.pyd", "pywin32：同上"),
    ("pywin32_system32/pywintypes*.dll", "pywin32 运行时：pywintypes"),
]


def _torch_source_allowed(rel: str) -> bool:
    """torch 源码是否属于「允许保留」的那几个（与 build.py 的规则一致）。"""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import build

        return build._keep_torch_source(rel)
    except Exception:  # noqa: BLE001
        # 兜底：与 build.py 的 TORCH_SOURCE_KEEP / config.py 规则保持一致
        name = rel.rsplit("/", 1)[-1]
        return name in ("config.py", "config_comms.py") or rel in {
            "utils/_config_module.py",
            "utils/serialization/config.py",
            "_sources.py",
            "fx/experimental/_config.py",
            "fx/experimental/symbolic_shapes.py",
            "fx/experimental/sym_node.py",
        }


def dir_size(path: Path) -> tuple[int, int]:
    """返回（总字节数，文件数）。"""
    total = 0
    count = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
                count += 1
            except OSError:
                pass
    return total, count


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    dist_dir = project_root / "dist" / "guji"
    internal = dist_dir / "_internal"

    if not internal.is_dir():
        msg = f"未找到 {internal} —— 请先执行 python build.py"
        print(msg)
        return 0 if "--json" in sys.argv else 1

    problems: list[str] = []

    for rel, reason in FORBIDDEN_FILES:
        if (internal / rel).exists():
            problems.append(f"{rel} —— {reason}")

    for pattern, reason in FORBIDDEN_GLOBS:
        hits = []
        for p in internal.glob(pattern):
            rel = p.relative_to(internal).as_posix()   # 形如 torch/xxx.py
            if rel.startswith("torch/") and _torch_source_allowed(rel[len("torch/"):]):
                continue                                # 允许保留的源码
            hits.append(rel)
        hits.sort()
        if hits:
            problems.append(f"{pattern} 命中 {len(hits)} 个（{hits[0]}…）—— {reason}")

    # 反向守卫：必需模块被瘦掉 → 同样算失败
    for pattern, reason in REQUIRED_GLOBS:
        if not any(internal.glob(pattern)):
            problems.append(f"缺少 {pattern} —— {reason}（被 excludes 误删？）")

    total, count = dir_size(dist_dir)
    mb = 1024 * 1024

    if "--json" in sys.argv:
        print(json.dumps({
            "dist_mb": round(total / mb, 1),
            "file_count": count,
            "problems": problems,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"打包产物: {dist_dir}")
        print(f"体积: {total / mb:.1f} MB / {count} 个文件")
        if problems:
            print(f"\n❌ 发现 {len(problems)} 项应被清理的内容：")
            for p in problems:
                print(f"   - {p}")
            print("\n请检查 build.py 的 prune_bloat() 是否执行。")
        else:
            print("✅ 瘦身检查通过：未发现无用内容")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
