# -*- coding: utf-8 -*-
"""「存储位置」设置：位置指针与数据迁移的纯逻辑自测。

只测可脱离 Qt 的部分（``desktop.settings.location`` + ``desktop.utils.files``），
不构造设置页、不弹真实对话框。指针文件通过 ``GUJI_LOCATION_FILE`` 指到
``tests/tmp/``，**绝不碰**开发机真实的用户配置。
"""

from __future__ import annotations

import os

from tests.selftests._context import ok

NAME = "settings_storage"
DEPENDS: list[str] = []
TITLE = "设置页存储位置（指针与迁移）"


def run(ctx) -> None:
    from desktop.settings.location import (
        MigrationCanceled,
        copy_file_if_missing,
        destination_has_content,
        guard_destination,
        migrate_data,
        plan_migration,
        resolve_data_root,
    )
    from desktop.utils.files import (
        DATA_LOCATION_FILE_ENV,
        default_guji_data_dir,
        guji_data_dir,
        reload_guji_data_dir,
        set_guji_data_dir,
    )

    work = ctx.tmp / "settings_storage"
    work.mkdir(parents=True, exist_ok=True)
    old_root = work / "old_guji"
    new_root = work / "new_guji"
    pointer = work / "location.json"

    old_root.mkdir(parents=True, exist_ok=True)
    (old_root / "tasks").mkdir()
    (old_root / "tasks" / "tasks.json").write_text("[]", encoding="utf-8")
    (old_root / "config.json").write_text('{"x": 1}', encoding="utf-8")
    (old_root / "singletask" / "extract").mkdir(parents=True)
    (old_root / "singletask" / "extract" / "thumb.jpg").write_bytes(b"jpg")

    previous = os.environ.get(DATA_LOCATION_FILE_ENV)
    os.environ[DATA_LOCATION_FILE_ENV] = str(pointer)
    try:
        # ---- 1. 没有指针文件时用历史默认位置 ----
        reload_guji_data_dir()
        ok(
            "无指针文件时回落到 ~/Documents/guji",
            guji_data_dir() == default_guji_data_dir(),
            str(guji_data_dir()),
        )

        # ---- 2. 写入指针后全局数据目录跟着变 ----
        applied = set_guji_data_dir(new_root)
        ok("set 返回规范化后的绝对路径", applied == new_root.resolve(), str(applied))
        ok("指针文件落在指定位置", pointer.is_file(), str(pointer))
        ok(
            "读回缓存后指向新目录",
            reload_guji_data_dir() == new_root.resolve(),
            str(guji_data_dir()),
        )
        ok("指针内容可被重新解析", pointer.read_text("utf-8").find("new_guji") >= 0)

        # ---- 3. 所选目录 → 数据根：始终带 guji 包裹 ----
        ok(
            "选普通目录时自动补 guji 文件夹",
            resolve_data_root(work / "backup")
            == (work / "backup" / "guji").resolve(),
            str(resolve_data_root(work / "backup")),
        )
        ok(
            "选中的目录本身叫 guji 时不再嵌套",
            resolve_data_root(work / "guji") == (work / "guji").resolve(),
            str(resolve_data_root(work / "guji")),
        )

        # ---- 4. 目标目录合法性 ----
        ok("相同目录被拒绝", guard_destination(old_root, old_root) is not None)
        ok(
            "子目录被拒绝",
            guard_destination(old_root, old_root / "tasks") is not None,
        )
        ok(
            "上级目录被拒绝",
            guard_destination(old_root, work) is not None,
        )
        ok("独立的兄弟目录允许", guard_destination(old_root, new_root) is None)

        # ---- 5. 迁移是复制：内容一致、旧目录原样保留 ----
        empty = work / "empty"
        empty.mkdir()
        ok("空目录判定为无内容", not destination_has_content(empty))
        ok("有文件判定为已有内容", destination_has_content(old_root))

        plan = plan_migration(old_root, new_root)
        ok("计划里数出 3 个文件", plan.total_files == 3, str(plan.total_files))
        copied, copied_bytes = migrate_data(plan)
        ok("迁移复制了全部文件", copied == 3, str(copied))
        ok("迁移按字节累计", copied_bytes > 0, str(copied_bytes))
        ok(
            "目标文件内容一致",
            (new_root / "tasks" / "tasks.json").read_text("utf-8") == "[]",
        )
        ok("旧目录仍在（复制不是剪切）", (old_root / "tasks").is_dir())

        # ---- 6. 取消迁移抛 MigrationCanceled ----
        plan2 = plan_migration(old_root, work / "partial")
        try:
            migrate_data(plan2, should_cancel=lambda: True)
        except MigrationCanceled:
            ok("取消迁移抛 MigrationCanceled", True)
        else:
            ok("取消迁移抛 MigrationCanceled", False, "没有抛异常")

        # ---- 7. 文件级补拷不覆盖已有文件 ----
        target = work / "single" / "config.json"
        ok(
            "缺失时复制",
            copy_file_if_missing(old_root / "config.json", target),
        )
        ok("已存在时不覆盖", not copy_file_if_missing(old_root / "config.json", target))
    finally:
        if previous is None:
            os.environ.pop(DATA_LOCATION_FILE_ENV, None)
        else:
            os.environ[DATA_LOCATION_FILE_ENV] = previous
        reload_guji_data_dir()
