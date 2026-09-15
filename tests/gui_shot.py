# -*- coding: utf-8 -*-
"""GUI 界面截图工具（离屏，用于视觉评审）。

真实运行环境里 Qt 能从系统字体库取到中文字体，但 offscreen 平台插件拿不到，
因此这里显式注册 Windows 字体，避免截图里全是豆腐块。

运行方式：
    QT_QPA_PLATFORM=offscreen python tests/gui_shot.py [输出目录]

产出（写入 <输出目录>，文件名与 docs/gui/screenshots/ 一致，可直接覆盖使用）：
    01-任务列表页.png
    02-详情页-提取.png
    03-详情页-检测.png
    04-详情页-去底色.png
    05-详情页-生成PDF.png
    06-详情页-日志浮层.png
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
sys.path.insert(0, str(Path(__file__).parents[1]))

FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
)


def load_fonts(app) -> list[str]:
    from PySide6.QtGui import QFont, QFontDatabase

    families: list[str] = []
    for path in FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        index = QFontDatabase.addApplicationFont(path)
        if index >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(index))
    if families:
        app.setFont(QFont(families[0], 10))
    return sorted(set(families))


def make_fake_page_image(path: Path, text: str, size=(560, 800), tone="#f3ead6",
                         frame: bool = True):
    """造一张"古籍页面"占位图，让预览区有内容可看。

    frame=False 用于去底色结果：不再画红色文本框边线。
    """
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

    image = QImage(size[0], size[1], QImage.Format.Format_RGB32)
    image.fill(QColor(tone))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#2b2b2b"))
    painter.setFont(QFont("SimSun", 15))
    painter.drawText(
        QRect(40, 40, size[0] - 80, size[1] - 80),
        int(Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
        text,
    )
    if frame:
        painter.setPen(QColor("#c0392b"))
        painter.drawRect(28, 28, size[0] - 56, size[1] - 56)
    painter.end()
    image.save(str(path))
    return path


def seed(repo) -> list[str]:
    """造 3 条任务：一条全流程完成、一条进行到一半、一条刚导入。"""
    from desktop.store import STAGES

    names = ["论语·学而篇", "孟子·梁惠王章句", "诗经·国风"]
    done_all = ["extract", "detect", "rembg", "print"]
    half = ["extract", "detect"]

    task_ids = []
    for index, name in enumerate(names):
        task_id = repo.create_task(Path(f"D:/samples/{name}.pdf"), f"hash{index}", name)
        task_ids.append(task_id)
        stages_done = done_all if index == 0 else (half if index == 1 else [])
        runs: dict[str, list] = {}
        for order, stage in enumerate(STAGES):
            if stage in stages_done:
                status = "success"
            elif index == 1 and stage == "rembg":
                status = "running"
            else:
                status = None
            if status is None:
                continue
            runs.setdefault(stage, []).insert(
                0,
                {
                    "run_id": f"{task_id}-{stage}",
                    "status": status,
                    "parameters": {},
                    "done": 24 if status == "success" else 9,
                    "total": 24,
                    "started_at": time.time() - 600,
                    "finished_at": time.time() - 300,
                    "output_path": None,
                },
            )
        if runs:
            repo._save_runs(task_id, runs)

    # 第一条任务铺满各阶段产物，供详情页预览
    main_id = task_ids[0]
    # 文字要铺满整页：半页缩略图会按"覆盖填充"居中裁切，只画顶部一行会裁成空白
    passages = [
        "道可道，非常道。名可名，非常名。无名天地之始，有名万物之母。",
        "故常无欲，以观其妙；常有欲，以观其徼。此两者同出而异名，同谓之玄。",
        "玄之又玄，众妙之门。天下皆知美之为美，斯恶已；皆知善之为善，斯不善已。",
        "有无相生，难易相成，长短相形，高下相倾，音声相和，前后相随。",
        "是以圣人处无为之事，行不言之教；万物作焉而不辞，生而不有，为而不恃。",
        "功成而弗居。夫唯弗居，是以不去。不尚贤，使民不争；不贵难得之货。",
    ]
    page_text = "\n".join(passages) * 2
    for stage in ("extract", "rembgpreview", "rembg"):
        directory = (
            repo.extract_output_dir(main_id)
            if stage == "extract"
            else repo.stage_dir(main_id, stage)
        )
        directory.mkdir(parents=True, exist_ok=True)
        for page in range(1, 7):
            # 去底色结果用白底无框，和原图区分开
            white = stage != "extract"
            make_fake_page_image(
                directory / f"{page:03d}.jpg",
                f"第 {page} 页\n\n{page_text}",
                tone="#ffffff" if white else "#f3ead6",
                frame=not white,
            )
    # 源页缩略图：命名必须 4 位补零（0001.jpg），与 _page_thumb_for 的约定一致。
    # 内容也要铺满——第三步条目缩略图是"源缩略图 + 检测框"裁出来的，
    # 只画一行字会被居中裁成空白。
    source_thumbs = repo.source_thumbnails_dir(main_id)
    for page in range(1, 7):
        make_fake_page_image(
            source_thumbs / f"{page:04d}.jpg",
            f"源 PDF 第 {page} 页\n\n{page_text}",
        )
    # 页面清单 / 尺寸 / 检测框：缺了这三样，详情页第 1~3 步预览会全是"暂无图片"
    extract_dir = repo.extract_output_dir(main_id)
    repo.save_pages(
        main_id,
        [{"file": str(extract_dir / f"{page:03d}.jpg"), "label": f"{page:03d}"}
         for page in range(1, 7)],
    )
    for page in range(1, 7):
        key = f"{page:03d}"
        repo.save_image_size(main_id, key, 560, 800)
        # 左右文本框各占半页 → 第三步 area=1 时拆成 -r / -l 两条目
        repo.save_detect_boxes(
            main_id, key, [[40, 40, 270, 760], [290, 40, 520, 760]], origin="auto"
        )
    return task_ids


def pump(app, times: int = 6) -> None:
    for _ in range(times):
        app.processEvents()
        time.sleep(0.05)


def main() -> int:
    import tempfile

    from PySide6.QtWidgets import QApplication

    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("shots")
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication([])
    families = load_fonts(app)
    print(f"已注册字体：{families}")

    from desktop.app import MainWindow
    from desktop.store import TaskStore
    from desktop.ui.style import apply_app_style

    apply_app_style(app)  # 与真实启动一致：字体/主题色/底色

    root = Path(tempfile.mkdtemp(prefix="guji_shot_"))
    repo = TaskStore(root)
    task_ids = seed(repo)

    window = MainWindow()
    window.store = repo
    window.list_page.store = repo
    window.detail_page.store = repo
    window.resize(1440, 920)
    window.show()
    window.list_page.refresh()
    pump(app)

    shots: list[Path] = []

    list_png = out_dir / "01-任务列表页.png"
    window.grab().save(str(list_png))
    shots.append(list_png)

    window._open_detail(task_ids[0])
    pump(app, 10)

    detail = window.detail_page
    stages = ("extract", "detect", "rembg", "print")
    labels = ("提取", "检测", "去底色", "生成PDF")
    for order, (stage, label) in enumerate(zip(stages, labels), start=2):
        detail._select_stage(stages.index(stage))
        if stage == "extract":
            # 演示任务的源 PDF 是伪造路径，PDF 预览必然是空占位；
            # 切到「提取结果」标签页，截图里才有实际内容可看。
            detail.extract_tabs.setCurrentIndex(1)
        pump(app, 10)
        png = out_dir / f"0{order}-详情页-{label}.png"
        window.grab().save(str(png))
        shots.append(png)

    # 第六张：日志浮层（底部常驻状态条 + 点击唤出的浮层），供布局文档引用
    detail._select_stage(0)
    detail.log_panel.set_expanded(False)
    detail.log_view.clear()
    detail.log_view.append("=== 开始执行 提取 ===")
    for page in range(1, 7):
        detail.log_view.append(f"[extract] 已提取第 {page}/6 页")
    detail.log_view.append("页面清单已刷新（6 页）。")
    detail.log_panel.set_expanded(True)
    pump(app, 10)
    log_png = out_dir / "06-详情页-日志浮层.png"
    window.grab().save(str(log_png))
    shots.append(log_png)
    detail.log_panel.set_expanded(False)

    for path in shots:
        print(f"已生成 {path}  ({path.stat().st_size // 1024} KB)")
    print(f"数据目录：{root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
