# -*- coding: utf-8 -*-
"""测试临时文件的**唯一落点**：``tests/tmp/``。

⚠️ 约定（2026-10-07 定）：**测试代码产生的临时数据一律落在本目录下**，
不要落到系统临时目录（``%TEMP%`` / ``C:\\Users\\<用户>\\AppData\\Local\\Temp``）、
更不要落到项目外的固定路径（如 ``D:/tmp``）。

为什么：

1. 落系统临时目录 ⇒ 产物散在**项目外**，跑完看不见、清不干净，出问题没法复现现场；
2. 散落在仓库里（根目录、``tests/`` 顶层）⇒ 会被 git 当**普通文件**收进仓库
   （``git add -A`` 一把带走）。``tests/tmp/`` 已在 ``.gitignore`` 里，
   ``git check-ignore -v tests/tmp/`` 可自证——**既在项目内、又不会被追踪**。

用法（按场景选）：

- **新写的测试代码**：``from tests.tmpdir import temp_dir``，
  ``temp_dir("前缀_")`` 返回一个新建的独占子目录（等价 ``mkdtemp``）；
- **存量代码 / 需要覆盖子进程**：在测试入口最顶部调一次 :func:`install`，
  它把 ``tempfile.tempdir`` 与 ``TMPDIR``/``TEMP``/``TMP`` 一起指到
  ``tests/tmp/``，于是**本进程后续所有** ``tempfile.mkdtemp()`` /
  ``tempfile.TemporaryDirectory()``，以及 **worker 子进程**里的
  ``tempfile.gettempdir()``，全部落到这里。
- **收工清理**：``clean()`` 清空 ``tests/tmp/``（临时数据用完要清；
  排查问题时当然可以留着看现场）。

⚠️ 只设 ``tempfile.tempdir`` 是不够的：它是**进程内**变量、不会传给子进程，
而 ``desktop/stages/print_stage.py`` 这类「在 worker 里自己算暂存目录」的
代码会跟主进程指到两个不同的地方（主进程 ``tests/tmp``、worker 系统临时目录），
排查起来极难。所以 :func:`install` 必须同时写环境变量。

⚠️ :func:`install` **必须在任何 ``tempfile`` 调用之前调**：
``tempfile.gettempdir()`` 第一次算完就把结果缓存进 ``tempfile.tempdir``，
之后再改环境变量不会生效。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

#: 落点根：``<仓库根>/tests/tmp``（本文件就在 ``tests/`` 下）。
TMP_ROOT = Path(__file__).resolve().parent / "tmp"

_INSTALLED = False


def tmp_root() -> Path:
    """返回 ``tests/tmp`` 并确保目录存在。"""
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return TMP_ROOT


def temp_dir(prefix: str = "guji_") -> Path:
    """在 ``tests/tmp/`` 下新建一个独占子目录并返回。

    等价于 ``tempfile.mkdtemp(prefix=prefix)``，只是把落点钉在项目内。
    """
    return Path(tempfile.mkdtemp(prefix=prefix, dir=str(tmp_root())))


def install() -> Path:
    """把本进程（及其子进程）的临时目录重定向到 ``tests/tmp/``。

    幂等；返回落点根。详见模块文档——**必须在任何 ``tempfile`` 调用之前调**。
    """
    global _INSTALLED
    root = tmp_root()
    if _INSTALLED:
        return root
    text = str(root)
    # ① 进程内：让 tempfile.gettempdir() 直接返回这里（不吃环境变量的缓存）。
    tempfile.tempdir = text
    # ② 子进程：Python 的 gettempdir 在 Windows 上依次看 TMPDIR/TEMP/TMP，
    #    所以 TMPDIR 就能覆盖 worker（也是 Python）；TEMP/TMP 再兜住读它们
    #    的原生库，避免同一轮测试里"一半在项目内、一半在系统临时目录"。
    for name in ("TMPDIR", "TEMP", "TMP"):
        os.environ[name] = text
    _INSTALLED = True
    return root


def clean() -> int:
    """清空 ``tests/tmp/`` 下的内容（保留目录本身），返回删除的条目数。

    临时数据用完要清（跑完一轮、或者开工前清一次），免得几百 MB 的旧产物
    堆着。⚠️ 只动 ``tests/tmp/`` 里面的东西——目录本身与目录外一概不碰。
    """
    removed = 0
    for entry in tmp_root().iterdir():
        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            removed += 1
        except OSError:
            pass
    return removed
