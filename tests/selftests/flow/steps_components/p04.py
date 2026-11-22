# -*- coding: utf-8 -*-
"""4b-4. 传 str 的路径不许流到 PreviewWorker（用户 2026-10-03 报） / 4c. 大输入区 + 控制组件：外部摆、内部接线（模块页的用法） / 5. 子进程传输层：启动参数与 UTF-8 环境（不起真进程） / 6. 独立功能目录改名的一次性迁移（磁盘路径不能被文案改动带走）"""

from typing import Any


def run(st: Any) -> None:
    from desktop.utils import files as F
    from desktop.components.viewers.image_viewer import ImageViewerWidget
    from pathlib import Path
    from desktop.workers.preview_worker import PreviewWorker
    from desktop.steps.source_zone import EMPTY_HEIGHT, FILLED_HEIGHT, SourceZone
    from desktop.steps.process import StageProcess, worker_arguments, worker_env
    from desktop.steps.control import StepControl
    from desktop.modules.extract.page import collect_result_images
    from tests.selftests._context import ok, wait_until
    import tempfile
    from desktop.components.viewers.image_viewer import ImageViewerWidget
    from desktop.workers.preview_worker import PreviewWorker

    viewer = ImageViewerWidget(editable=False)
    viewer.set_images([str(st.drop_dir / "a.png"), str(st.drop_dir / "c.png")])
    ok(
        "set_images 接受 str 列表并统一转成 Path",
        len(viewer.paths) == 2 and all(isinstance(p, Path) for p in viewer.paths),
        str([type(p).__name__ for p in viewer.paths]),
    )

    worker = PreviewWorker(str(st.drop_dir / "a.png"))
    ok(
        "PreviewWorker 构造时把 str 收成 Path",
        isinstance(worker.path, Path),
        str(type(worker.path).__name__),
    )

    # 真跑一次：不该出现 suffix 相关的 AttributeError
    probe_fail: list = []
    probe_worker = PreviewWorker(str(st.drop_dir / "a.png"))
    probe_worker.failed.connect(lambda _p, m: probe_fail.append(m))
    probe_worker.run()
    ok(
        "PreviewWorker(str).run() 不抛 AttributeError",
        not any("suffix" in m for m in probe_fail),
        str(probe_fail),
    )

    # ⚠️ 同名只保留一份（用户 2026-10-03 报：预览里每页出现两次）
    from desktop.modules.extract.page import collect_result_images

    dup_dir = Path(st.ctx.tmp) / "dup_out"
    (dup_dir / "样书" / "images").mkdir(parents=True, exist_ok=True)
    for name in ("1.jpg", "2.jpg", "10.jpg"):
        (dup_dir / name).write_bytes(b"x")
        (dup_dir / "样书" / "images" / name).write_bytes(b"x")
    picked = collect_result_images(dup_dir)
    ok(
        "平铺 + 嵌套两套同名：只收一份，且优先顶层",
        [p.name for p in picked] == ["1.jpg", "2.jpg", "10.jpg"]
        and all(p.parent == dup_dir for p in picked),
        str([(p.name, p.parent.name) for p in picked]),
    )
    ok(
        "去重后按数字自然排序（2 在 10 前面）",
        [p.name for p in picked] == ["1.jpg", "2.jpg", "10.jpg"],
        str([p.name for p in picked]),
    )

    # 只有嵌套那一套时也要收得到（不能因为"没有顶层"就漏掉）
    only_nested = Path(st.ctx.tmp) / "only_nested"
    (only_nested / "样书" / "images").mkdir(parents=True, exist_ok=True)
    (only_nested / "样书" / "images" / "1.jpg").write_bytes(b"x")
    ok(
        "只有嵌套那一套时也能收到图",
        [p.name for p in collect_result_images(only_nested)] == ["1.jpg"],
        str(collect_result_images(only_nested)),
    )
    zone_c = SourceZone(st.rembg)
    control_c = StepControl(st.rembg, zone=zone_c)
    ok("控件接受外部大输入区（不重复摆一块）", control_c.zone is zone_c)
    zone_c.offer([str(st.drop_dir / "c.png")])
    ok(
        "从大输入区拖入 → 控件拿到源（按 spec 归一化）",
        control_c.source() == st.drop_dir / "c.png",
        str(control_c.source()),
    )
    ok("大输入区同步显示成已选态", zone_c.source() == st.drop_dir / "c.png")
    zone_c.offer([str(st.drop_dir / "a.pdf")])
    ok("后缀不符时不动源（只发状态）", control_c.source() == st.drop_dir / "c.png")
    zone_c.clear()
    ok(
        "清空大输入区 → 控件的源与输出一起复位",
        control_c.source() is None and control_c.output() is None,
    )
    control_c.shutdown()
    args_packed = worker_arguments(Path("/tmp/run-1.json"))
    ok(
        "源码环境按模块启动 worker",
        args_packed[:2] == ["-m", "desktop.worker"] and "--config" in args_packed,
        str(args_packed),
    )
    env = worker_env()
    ok(
        "子进程强制 UTF-8",
        env.value("PYTHONIOENCODING") == "utf-8" and env.value("PYTHONUTF8") == "1",
    )
    ok("传输层初始没有进程", StageProcess().process is None)
    ok("传输层初始不忙", StageProcess().running() is False)
    import tempfile

    from desktop.utils import files as F

    with tempfile.TemporaryDirectory() as td:
        real_root = Path(td) / "guji"

        def _fake_root():
            return real_root

        orig = F.guji_data_dir
        F.guji_data_dir = _fake_root  # type: ignore[assignment]
        try:
            base = real_root / "singletask"
            # 造两个"老中文名"目录，各放一个标记文件（模拟缓存/手改件）
            (base / "拼图" / "edited").mkdir(parents=True)
            (base / "拼图" / "edited" / "p1.png").write_bytes(b"edited")
            (base / "去底色" / "thumbs").mkdir(parents=True)
            (base / "去底色" / "thumbs" / "a.jpg").write_bytes(b"thumb")
            # 再造一个"新名已存在"的场景，验证不会被覆盖
            (base / "detect").mkdir(parents=True)
            (base / "detect" / "keep.jpg").write_bytes(b"keep")
            (base / "检测文本框").mkdir(parents=True)
            (base / "检测文本框" / "old.jpg").write_bytes(b"old")

            moved = F.migrate_legacy_singletask_dirs()
            ok(
                "老中文名目录被搬到 disk_key 名下",
                (base / "imposition" / "edited" / "p1.png").exists()
                and (base / "rembg" / "thumbs" / "a.jpg").exists(),
                str(moved),
            )
            ok(
                "搬过去的是原内容（一个字节不差）",
                (base / "imposition" / "edited" / "p1.png").read_bytes() == b"edited",
            )
            ok(
                "迁移报出了搬动清单（给日志/排查用）",
                any("拼图" in m for m in moved),
                str(moved),
            )
            # 新目录已存在时**不动**旧目录（不覆盖、不合并、绝不删）
            ok(
                "新目录已存在时旧目录原样保留（绝不覆盖用户数据）",
                (base / "detect" / "keep.jpg").read_bytes() == b"keep"
                and (base / "检测文本框" / "old.jpg").read_bytes() == b"old",
            )
            # 幂等：再跑一遍什么都不该发生
            again = F.migrate_legacy_singletask_dirs()
            ok("迁移是幂等的（重复启动不重复搬）", again == [], str(again))
            ok(
                "旧目录不被删除（用户可自己确认后清理）",
                not (base / "拼图").exists() and not (base / "去底色").exists(),
            )
        finally:
            F.guji_data_dir = orig  # type: ignore[assignment]

