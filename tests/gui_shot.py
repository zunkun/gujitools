# -*- coding: utf-8 -*-
"""GUI 界面截图工具（离屏，用于视觉评审与操作手册配图）。

真实运行环境里 Qt 能从系统字体库取到中文字体，但 offscreen 平台插件拿不到，
因此这里显式注册 Windows 字体，避免截图里全是豆腐块。

运行方式：
    QT_QPA_PLATFORM=offscreen python tests/gui_shot.py [输出目录]

两种模式：

- **默认（界面总览）**：6 张，按「页面」组织，供布局文档引用：
    01-任务列表页.png
    02-详情页-提取.png
    03-详情页-检测.png
    04-详情页-去底色.png
    05-详情页-生成PDF.png
    06-详情页-日志浮层.png
  文件名与 `docs/guide/screenshots/` 下的同名文件一致，可直接覆盖。

- **`--guide`（操作步骤）**：写入 `<输出目录>/guide/`，按「用户操作」组织，
  供上手指南（docs/guide/user-guide.md）逐步引用。截图里的参数都是**真实控件
  状态**（拖框选中、改 area、填表单），不是凭空画的示意图。

两种模式都从同一套演示数据出发，所以界面改了重跑一次即可全部刷新。

## 演示数据：优先用真实古籍

默认会在 `$GUJI_SHOT_PDF` 或 `C:/Users/liuzu/Documents/test/` 下找真实古籍 PDF
（优先取「龍譚精舍叢刻」），把它的**真实页面图片、真实检测框**灌进演示任务，
这样截图里是货真价实的古籍版面，而不是占位图。

找不到真实 PDF 时自动回退到内置的合成占位页（`make_fake_page_image`），
因此本脚本在任何机器上都能跑。

## ⚠️ 演示页固定用第 4 页

`DEMO_PAGE = 4`。这个常量同时决定三件事：任务列表/详情页选中哪一页、
检测框按哪一页的真实坐标渲染、第四步 PDF 名称怎么取。
**改这个常量必须同步跑 `tests/gui_selftest.py --only gui_guide`**
（指南里引用了这些截图，护栏会核对页序与文件名）。

原本用第 3 页，但第 3 页正文只占右半栏、版面偏空，做演示不够典型；
第 4 页是左右两栏都排满的规整正文页，更适合展示检测框与去底色效果。
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
sys.path.insert(0, str(Path(__file__).parents[1]))

from PySide6.QtCore import Qt  # noqa: E402

FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
)

# 演示用古籍：优先「龍譚精舍叢刻」，其次该目录下任意 PDF。
REAL_PDF_DIRS = (
    Path(r"C:\Users\liuzu\Documents\test"),
    Path(r"C:\Users\liuzu\Documents\test\guji_work"),
)
REAL_PDF_PREFERRED = "龍譚精舍叢刻"

# 演示页：第 4 页（左右两栏都排满的规整正文页）。
# ⚠️ 改动此常量会改变截图内容，指南护栏会核对页序，改完必须重跑 gui_guide 自测。
DEMO_PAGE = 4


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


def find_real_pdf() -> tuple[Path, Path | None] | None:
    """找真实古籍 PDF 及配套的中间产物目录。

    返回 (pdf_path, work_dir|None)：
      - work_dir 是 `extract→detect→rembg` 已跑完的工作目录（含
        images/ detect/ rembg/ 三个子目录），拿它的真实产物当演示数据；
      - 只找到 PDF、没有产物时返回 None 作第二项，此时只喂源 PDF
        （PDF 预览是真的，其余阶段回退占位图）。

    优先级：环境变量 GUJI_SHOT_PDF > REAL_PDF_DIRS 里含「龍譚精舍叢刻」的
    > REAL_PDF_DIRS 里任意 PDF。找不到返回 None。
    """
    env = os.environ.get("GUJI_SHOT_PDF")
    if env and Path(env).exists():
        pdf = Path(env)
        return pdf, _sibling_work_dir(pdf)

    candidates: list[Path] = []
    for directory in REAL_PDF_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.pdf")):
            # 跳过工作目录里我们自己复制的那份，避免和自我递归
            if path.parent.name == "guji_work" and path.name == "book.pdf":
                continue
            candidates.append(path)
    if not candidates:
        return None

    preferred = [p for p in candidates if REAL_PDF_PREFERRED in p.name]
    pdf = (preferred or candidates)[0]
    return pdf, _sibling_work_dir(pdf)


def _sibling_work_dir(pdf: Path) -> Path | None:
    """找与 PDF 配套的已跑完产物目录（images/detect/rembg 三者齐全才算数）。"""
    probe = pdf.parent / "guji_work" / "book"
    if not probe.is_dir():
        probe = pdf.parent
    if all((probe / sub).is_dir() for sub in ("images", "detect", "rembg")):
        return probe
    return None


def _stage_images(work_dir: Path, stage: str) -> dict[int, Path]:
    """收集某阶段目录下按页码索引的图片：{页码: 路径}。"""
    out: dict[int, Path] = {}
    for path in (work_dir / stage).iterdir():
        if path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        if path.stem.isdigit():
            out[int(path.stem)] = path
    return out


def _copy_real_demo(repo, task_id: str, work_dir: Path, page: int) -> bool:
    """把真实古籍的第 page 页产物灌进演示任务，让截图显示真版面。

    复制三个东西，与真实的阶段目录一一对应：
      - extract 输出目录 ← work_dir/images/<page>.jpg；
        并造 6 页清单（真实页码 3~8），便于展示多页与翻页。
      - source 页缩略图 ← 同一批真实图（PDF 预览区与列表缩略图都读这里）。
      - 检测框 ← 用真实 detect 结果跑一遍 YOLO 取坐标，写进 boxes.json。

    返回 False 表示数据不足（缺图或检测失败），调用方应回退到占位图。
    """
    from PySide6.QtGui import QImage

    images = _stage_images(work_dir, "images")
    if page not in images:
        return False

    # 演示用连续 6 页：真实页码 page..page+5，界面上是第一页到第六页。
    total_available = max(images) if images else 0
    page_numbers = [n for n in range(page, page + 6) if n <= total_available]
    if len(page_numbers) < 2:
        page_numbers = [page]

    extract_dir = repo.extract_output_dir(task_id)
    extract_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir = repo.source_thumbnails_dir(task_id)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    for index, real_no in enumerate(page_numbers, start=1):
        source = images[real_no]
        # extract 输出用 3 位零填充的连续序号（001.jpg…），与真实阶段一致
        target = extract_dir / f"{index:03d}{source.suffix}"
        shutil.copy2(source, target)
        # ⚠️ image_size 必须记「阶段图（extract 产物）的真实尺寸」，不是缩略图尺寸。
        # _page_thumb_for 用 sx = 缩略图宽 / image_size 宽 把检测框（阶段图坐标）
        # 换算到缩略图上；若这里记成缩略图尺寸，sx 恒为 1，框就按阶段图坐标
        # 去裁缩略图 → 越界裁出全白，缩略图列表显示为"没加载出来"。
        original = QImage(str(source))
        if original.isNull():
            return False
        repo.save_image_size(
            task_id, f"{index:03d}", original.width(), original.height()
        )
        # source 缩略图必须 4 位零填充（0001.jpg），与 _page_thumb_for 约定一致
        thumb = thumbs_dir / f"{index:04d}.jpg"
        image = original
        if max(image.width(), image.height()) > 700:
            # ⚠️ QImage.scaled 的位置参数是 (w, h, aspectMode, transformMode)，
            # 没有 keep_aspect_ratio 关键字；写错会 TypeError 且被上层静默吞掉，
            # 表现为「真实数据灌入失败」而回退占位图。
            image = image.scaled(
                700, 700,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        image.save(str(thumb), "JPG", 88)
        entries.append({"file": str(target), "label": f"{index:03d}"})

    repo.save_pages(task_id, entries)

    if not _write_real_detect_boxes(repo, task_id, extract_dir, page_numbers):
        return False

    # 第一页作为各预览区的默认展示页
    return True


def _write_real_detect_boxes(repo, task_id: str, extract_dir: Path,
                             page_numbers: list[int]) -> bool:
    """对演示页跑真实 YOLO 检测，把坐标写进 boxes.json。

    为什么真跑检测而不是写死坐标：写死的坐标一旦换页/换书就与画面错位，
    截图上会出现"框飘在文字外面"的假象。真实检测保证框与版面严格对应。
    """
    import cv2

    from functions.detect import detect_page_boxes

    ok_any = False
    for index, _real_no in enumerate(page_numbers, start=1):
        key = f"{index:03d}"
        path = extract_dir / f"{key}.jpg"
        if not path.exists():
            continue
        image = cv2.imread(str(path))
        if image is None:
            continue
        try:
            left, right = detect_page_boxes(image)
        except Exception:  # noqa: BLE001 — 检测失败就跳过该页，不阻断截图
            continue
        # ⚠️ detect_page_boxes 返回的是 (left_box, right_box) **两个框**，
        # 各自可能是 None；而 save_detect_boxes 要的是**框的列表**。
        # 直接把返回值当列表传会把 int 当成框去解包 → TypeError。
        boxes = [box for box in (left, right) if box is not None]
        if boxes:
            repo.save_detect_boxes(task_id, key, boxes, origin="auto")
            ok_any = True
    return ok_any


def make_fake_page_image(path: Path, text: str, size=(560, 800), tone="#f3ead6",
                         frame: bool = True):
    """造一张"古籍页面"占位图，让预览区有内容可看。

    frame=False 用于去底色结果：不再画红色文本框边线。
    仅在找不到真实古籍 PDF 时作为回退使用。
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
    """造 3 条任务：一条全流程完成、一条进行到一半、一条刚导入。

    第一条（`--guide` 与总览模式的主角）优先灌**真实古籍**数据：
    源 PDF 用真文件（PDF 预览区显示真页面）、extract/detect 产物用真图片与
    真检测坐标。找不到真实 PDF 时回退为合成占位页。

    返回任务号列表，第一条是演示主角。
    """
    from desktop.store import STAGES

    real = find_real_pdf()
    real_pdf, work_dir = real if real else (None, None)
    used_real = False

    names = ["论语·学而篇", "孟子·梁惠王章句", "诗经·国风"]
    if real_pdf is not None:
        # 任务名取真实书名（去掉 Harvard 前缀与版本后缀），界面上更可信
        stem = real_pdf.stem
        if "龍譚精舍叢刻" in stem:
            names[0] = "龍譚精舍叢刻"
        else:
            names[0] = stem
    done_all = ["extract", "detect", "rembg", "print"]
    half = ["extract", "detect"]

    task_ids = []
    for index, name in enumerate(names):
        source = real_pdf if (index == 0 and real_pdf) else Path(f"D:/samples/{name}.pdf")
        task_id = repo.create_task(source, f"hash{index}", name)
        task_ids.append(task_id)
        # 真实任务把源 PDF 复制进任务目录，PDF 预览才能真正渲染出页面
        if index == 0 and real_pdf is not None:
            repo.copy_source_to_task(task_id, real_pdf)
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

    # ---- 首选：真实古籍第 DEMO_PAGE 页 ----
    if work_dir is None and real_pdf is not None:
        print(f"ℹ️ 找到 {real_pdf.name}，但没有配套的 images/detect/rembg 产物")
    if work_dir is not None:
        try:
            used_real = _copy_real_demo(repo, main_id, work_dir, DEMO_PAGE)
        except Exception as exc:  # noqa: BLE001 — 真实数据不可用时回退占位图
            print(f"⚠️ 真实古籍数据灌入失败，回退占位图：{exc!r}")
            used_real = False
        else:
            if used_real:
                print(f"✓ 演示数据：{real_pdf.name} 第 {DEMO_PAGE} 页起（真实版面）")

    if used_real:
        # 真实数据已铺好 extract：派生去底色结果后收工。
        # ⚠️ 这句**必须待在 extract 就绪之后**。原先它写在 if 之外、无条件调用，
        #    而回退分支要到下面才 mkdir(extract)，于是「真实数据灌入失败 →
        #    used_real=False」时必然 FileNotFoundError 把整个用例炸掉。
        _seed_rembg_outputs(repo, main_id)
        return task_ids

    # ---- 回退：合成占位页 ----
    print("ℹ️ 演示数据回退为合成占位页")
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
    extract_dir.mkdir(parents=True, exist_ok=True)
    for page in range(1, 7):
        make_fake_page_image(
            extract_dir / f"{page:03d}.jpg",
            f"第 {page} 页\n\n{page_text}",
        )
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
    # 去底色结果：从上面刚生成的 extract 真图派生（白底黑字），
    # 这样第三步预览与第四步瀑布流都有内容。
    _seed_rembg_outputs(repo, main_id)
    return task_ids


def _seed_rembg_outputs(repo, task_id: str) -> None:
    """从 extract 图片派生「去底色预览图」与「去底色成品图」。

    真实二值化（Otsu），白底黑字，与第三步真实产物一致；
    比合成白纸可信，也让第四步瀑布流有真内容。
    """
    import cv2

    extract_dir = repo.extract_output_dir(task_id)
    if not extract_dir.is_dir():
        # 防御：万一调用方在 extract 就绪前调过来，安静跳过而不是抛
        # FileNotFoundError（真数据分支不保证有该目录）。
        return
    sources = sorted(
        (p for p in extract_dir.iterdir()
         if p.suffix.lower() in (".jpg", ".jpeg", ".png") and p.stem.isdigit()),
        key=lambda p: int(p.stem),
    )
    if not sources:
        return
    for stage in ("rembgpreview", "rembg"):
        target_dir = repo.stage_dir(task_id, stage)
        target_dir.mkdir(parents=True, exist_ok=True)
        for source in sources:
            image = cv2.imread(str(source))
            if image is None:
                continue
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            ok, buf = cv2.imencode(".png", binary)
            if ok:
                (target_dir / f"{source.stem}.png").write_bytes(buf.tobytes())


def set_combo(combo, value: str) -> bool:
    """按 itemData 选中下拉项（这些下拉是「中文显示 / 英文值」的双列 combo）。

    ⚠️ 不能用 `setCurrentText("portrait")` —— 显示文案是「竖版」，
    英文值存在 itemData 里，按文本找会静默选不中。
    """
    index = combo.findData(value)
    if index < 0:
        return False
    combo.setCurrentIndex(index)
    return True


def pump(app, times: int = 6) -> None:
    """驱动事件循环，并**清掉 deleteLater 的旧控件**。

    ⚠️ 必须显式清 DeferredDelete：`setCellWidget` 换掉旧单元格控件走的是
    `deleteLater()`，而 `processEvents()` 不处理 DeferredDelete 事件——截图
    进程又从不真正回到主事件循环。不清的话旧标签会和新标签叠在同一格里，
    截图上就是"任务名重影"（两段文字互相压着，看着像界面坏了）。
    """
    from PySide6.QtCore import QCoreApplication, QEvent

    for _ in range(times):
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(0.05)


def wait_for_thumbnails(
    app,
    strips,
    timeout: float = 20.0,
    min_loaded: int | None = None,
) -> bool:
    """等缩略图条把占位图全部换成真实缩略图。

    ⚠️ 缩略图是**后台线程**逐张回填的（`ImageListWorker` → `thumbnail_ready`
    → `ThumbStrip.set_item_icon`）。固定次数的 `pump()` 只是「泵一会儿事件」，
    机器慢或图多时截图里会留下灰色虚线占位块——界面本身不报任何错。

    做法：每轮泵完事件就用 `QPixmap.cacheKey()` 比对当前图标与占位图，
    全部换掉即返回 True；超时返回 False 并打印剩余数量，便于发现退化。

    ⚠️ 注意本函数**只管「图标换了没有」，管不了「图标内容对不对」**。
    曾经遇到过：图标确实全部就绪（本函数立即返回 True），但内容是被
    越界裁出来的纯白图，界面看起来同样像「没加载完」。那种情况的根因是
    检测框坐标系与缩略图不一致，由 `gui_guide` 自测的
    「演示缩略图无全白」断言负责兜住，不要试图在这里判断。

    参数:
        app: QApplication。
        strips: ThumbStrip 实例或实例列表（可传多个，如同时等预览区与瀑布流）。
        timeout: 最长等待秒数。
        min_loaded: 至少加载多少条即算通过（默认要求全部）。
    """
    if not isinstance(strips, (list, tuple)):
        strips = [strips]
    strips = [s for s in strips if s is not None]
    if not strips:
        return True

    start = time.time()
    while time.time() - start < timeout:
        app.processEvents()
        time.sleep(0.05)
        pending = 0
        for strip in strips:
            # 占位图是模块级静态方法造的，cacheKey 与真实缩略图必然不同。
            # 尺寸取控件自己的 iconSize（别再写字面量：ThumbStrip 改过框尺寸，
            # 写死会让比对窗口与真实渲染尺寸不一致）。
            icon_size = strip.iconSize()
            placeholder_key = strip._placeholder.pixmap(icon_size).cacheKey()
            for row in range(strip.count()):
                item = strip.item(row)
                icon = item.icon()
                if icon.isNull():
                    continue  # 纯文字条目（如「缩略图加载中…」）不参与判定
                if icon.pixmap(icon_size).cacheKey() == placeholder_key:
                    pending += 1
        total = sum(s.count() for s in strips)
        if min_loaded is not None:
            if total - pending >= min_loaded:
                return True
        elif pending == 0:
            return True
    print(f"⚠️ 缩略图等待超时（{timeout}s），仍为占位的有 {pending} 条")
    return False


def _visible_strips(detail) -> list:
    """详情页里当前有内容的缩略图条（供 wait_for_thumbnails 使用）。

    只有部分阶段有缩略图条（去底色的左侧列表、PDF 预览的原件页条等），
    其余阶段返回空列表——`wait_for_thumbnails` 对空列表直接通过。
    """
    candidates = [
        getattr(detail, "rembg_viewer", None),
        getattr(detail, "source_pdf_viewer", None),
        getattr(detail, "extract_result_viewer", None),
        getattr(detail, "detect_viewer", None),
    ]
    found = []
    for widget in candidates:
        strip = getattr(widget, "strip", None)
        if strip is not None and strip.count() > 0:
            found.append(strip)
    return found


# --------------------------------------------------------------- 操作步骤截图

def shoot_guide(app, window, out_dir: Path, task_id: str,
                book_title: str = "龍譚精舍叢刻") -> list[Path]:
    """按「用户操作步骤」逐屏截图，供上手指南引用。

    与总览模式的差别：这里刻意**制造交互态**——选中检测框、改 area、
    填好表单、铺满日志——让读者看到「做对之后应该长什么样」，而不是
    空白表单。所有状态都通过真实控件 API 设置，与用户手点等价。

    参数:
        app: QApplication（用于 processEvents 泵消息）。
        window: 已打开详情页的 MainWindow。
        out_dir: 输出目录（自动创建）。
        task_id: 演示任务号（全流程完整的那一条）。
        book_title: 第四步表单里填的古籍名（取真实书名）。

    返回:
        写出的 PNG 路径列表。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    detail = window.detail_page
    shots: list[Path] = []

    def snap(filename: str, note: str = "", before=None) -> None:
        """泵消息 + 等缩略图加载完，再截图。

        ⚠️ 缩略图是后台线程逐张回填的，只 `pump()` 固定次数会拍到灰色占位块
        （界面不报错，纯视觉问题，最容易漏）。这里显式等到全部换掉。

        `before` 是「快门前最后施加的交互态」回调：Qt 的
        `ImageBoxView.set_boxes()` 会把 `_selected` 重置为 None，所以选中框
        这类状态必须在**所有刷新都跑完**之后、grab 之前设置，否则会被冲掉。
        """
        pump(app, 12)
        wait_for_thumbnails(app, _visible_strips(detail))
        if before is not None:
            before()
            pump(app, 4)  # 让重绘走一轮
            # 交互态可能触发新一轮图像加载（如切 area 后重算预览），再等一次
            wait_for_thumbnails(app, _visible_strips(detail))
        path = out_dir / filename
        window.grab().save(str(path))
        shots.append(path)
        print(f"已生成 {path.name}  {('— ' + note) if note else ''}")

    # ---- 步骤 0：任务列表页（起点）----
    window.pages.setCurrentWidget(window.list_page)
    window.list_page.refresh()
    pump(app, 10)
    snap("s0-任务列表.png", "起点：已导入的任务")

    window._open_detail(task_id)
    pump(app, 12)

    # ---- 步骤 1：提取图片 ----
    detail._select_stage(0)
    detail.extract_tabs.setCurrentIndex(1)  # 「提取结果」页，能看到产出
    snap("s1-提取-结果.png", "第一步：提取结果")

    extract_panel = detail.control_stack.widget(0)
    extract_panel.zoom.setValue(2)
    extract_panel.ext.setCurrentText("png")
    detail.extract_tabs.setCurrentIndex(0)  # 切回 PDF 预览，展示参数与源文件对照
    snap("s1-提取-参数.png", "第一步：调 zoom / dpi / ext 参数")

    # ---- 步骤 2：检测文本框 ----
    detail.extract_tabs.setCurrentIndex(0)
    detail._select_stage(1)
    viewer = detail.detect_viewer
    # ⚠️ 框状态在内层 `ImageView` 上（`detect_viewer.view`），不是外层
    # ImageViewerWidget；_selected / _boxes / _commit_edit 都在内层。
    inner = viewer.view
    pump(app, 14)
    snap("s2-检测-默认.png", "第二步：自动检测出的左右框")

    # 选中左框 → 四角出现手柄，右下角信息条显示坐标（真实的编辑态）。
    # ⚠️ 必须调 `_rerender()` 而不是 `update()`：框是画进 pixmap 的，
    # `update()` 只重绘既有 pixmap，改动不会体现；且 `set_boxes()` 会把
    # `_selected` 清空，所以要在所有刷新跑完之后（before 回调里）设。
    def _select_first_box() -> None:
        if inner._boxes:
            inner._selected = 0
            inner._rerender()

    snap("s2-检测-选中框.png", "第二步：点框选中，可拖动/缩放/删除",
         before=_select_first_box)

    # 手绘补充框：直接追加到查看器的框列表并提交，相当于用户在空白处拖了一笔。
    # 提交会写库（origin=manual）并触发一次重绘，因此同样放在 before 里做。
    # ⚠️ 坐标按演示页的实际像素尺寸算（真实古籍是 ~2400x2367，不是占位图的
    # 560x800）。写死小坐标会在真图上画出一个贴边的小框，看起来像 bug。
    def _draw_extra_box() -> None:
        if not inner._boxes:
            return
        # 以已检出的框为参照推算出画面尺寸，避免依赖具体书页尺寸
        xs = [c for box in inner._boxes for c in (box[0], box[2])]
        ys = [c for box in inner._boxes for c in (box[1], box[3])]
        w = max(xs) * 1.08
        h = max(ys) * 1.06
        # 在版心下方的空白处画一个横向小框（模拟补检漏掉的题跋/批注）
        inner._boxes.append([
            int(w * 0.30), int(h * 0.90),
            int(w * 0.72), int(h * 0.99),
        ])
        inner._selected = len(inner._boxes) - 1
        inner._commit_edit()
        inner._rerender()

    snap("s2-检测-手绘补充框.png", "第二步：空白处拖拽手绘补充框",
         before=_draw_extra_box)

    # ---- 步骤 3：去底色 ----
    detail._select_stage(2)
    rembg_panel = detail.control_stack.widget(2)
    rembg_panel.area.setCurrentText("2 (合并单图)")
    rembg_panel.border.setText("20,30")
    rembg_panel.seal.setChecked(True)
    rembg_panel.type.setCurrentText("1 (二值)")
    snap("s3-去底色-参数.png", "第三步：area/border/印章参数")

    rembg_panel.area.setCurrentText("1 (左右分开)")
    snap("s3-去底色-结果.png", "第三步：左右分开的去底色结果")

    # ---- 步骤 4：生成 PDF ----
    detail._select_stage(3)
    print_panel = detail.control_stack.widget(3)
    snap("s4-生成PDF-默认.png", "第四步：左侧待打印缩略图条 + 右侧打印效果预览")

    # 第四步的参数是**表单控件**（不是 YAML 文本框）：驱动真实控件，
    # 展示「填过参数之后」的样子。字段名来自 print_form.py 的构建代码。
    # ⚠️ 纸张尺寸/方向是「中文显示 / 英文值」的双列 combo，必须按 itemData 选，
    # 用 setCurrentText("portrait") 会静默选不中（显示文案是「竖版」）。
    def _fill_print_form() -> None:
        print_panel.title_text.setText(book_title)
        set_combo(print_panel.paper_size, "A4")
        set_combo(print_panel.orientation, "portrait")  # 古籍竖开本
        print_panel.page_margins.setText("20,30")
        print_panel.title_printing.setChecked(True)
        print_panel.title_font_size.setValue(20)
        print_panel.page_number_printing.setChecked(True)
        print_panel.page_number_base.setValue(1)
        print_panel.page_number_start.setValue(1)
        # 「距页边」：勾选"自定义"后按**两行、每行一个通栏输入框**填——
        # 第一行「左右边距：」（一个值管左页+右页），第二行「上边距：」/
        # 「下边距：」（标题填上、页码填下）。填了之后**不再收窄图片**，
        # 距离只决定文字画在哪儿（允许压在图上）。
        print_panel.set_inset("title", [2, 14, 2, 10])
        print_panel.set_inset("page_number", [2, 14, 2, 10])

    snap("s4-生成PDF-参数.png", "第四步：填好输出 / 纸张 / 边距 / 标题 / 页码",
         before=_fill_print_form)

    # ---- 执行中 + 日志 ----
    detail._select_stage(0)
    detail.log_view.clear()
    for text in sample_log_lines(book_title, DEMO_PAGE):
        detail.log_view.append(text)
    detail.log_panel.set_expanded(True)
    snap("s5-执行日志.png", "运行时的日志浮层")

    detail.log_panel.set_expanded(False)
    pump(app, 8)
    snap("s5-日志状态条.png", "收起后的底部常驻状态条")

    return shots


def sample_log_lines(book_title: str, demo_page: int, page_count: int = 6) -> list[str]:
    """日志浮层示例：模仿一次真实 extract 的输出节奏。

    ⚠️ 文案要与 functions 层真实打印的格式一致（`加载 PDF：...`、
    `quick：第 N 页...`、`已提取 N/M 页`），否则截图里的日志一眼假。
    """
    lines = [
        "=== 开始执行 提取 ===",
        f"加载 PDF：{book_title}.pdf",
        f"quick：第 {demo_page} 页命中内嵌图（jpg）",
        f"quick：第 {demo_page + 1} 页命中内嵌图（jpg）",
        f"quick：第 {demo_page + 2} 页无内嵌图，降级为整页渲染",
        f"已提取 1/{page_count} 页",
        f"已提取 3/{page_count} 页",
        f"已提取 {page_count}/{page_count} 页",
        f"页面清单已刷新（{page_count} 页）。",
        "Process completed!",
    ]
    return lines


def main() -> int:
    import tempfile

    from PySide6.QtWidgets import QApplication

    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    guide_mode = "--guide" in sys.argv

    out_dir = Path(argv[0]) if argv else Path("shots")
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

    # 演示主角的书名：取任务名（seed 已按真实 PDF 命名），第四步表单与日志都用它
    main_task = repo.get_task(task_ids[0]) or {}
    book_title = main_task.get("name") or "龍譚精舍叢刻"

    window = MainWindow()
    window.store = repo
    window.list_page.store = repo
    window.detail_page.store = repo
    window.resize(1440, 920)
    window.show()
    window.list_page.refresh()
    pump(app)

    if guide_mode:
        window._open_detail(task_ids[0])
        pump(app, 12)
        shots = shoot_guide(
            app, window, out_dir / "guide", task_ids[0], book_title=book_title
        )
        for path in shots:
            print(f"  {path.stat().st_size // 1024} KB")
        print(f"数据目录：{root}")
        return 0

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
            # 切到「提取结果」标签页，展示实际产出（PDF 预览页也能看真源文件，
            # 但这一步的主角是提取出来的页面图）。
            detail.extract_tabs.setCurrentIndex(1)
        pump(app, 10)
        # ⚠️ 与 guide 模式同理：缩略图是后台线程回填的，不等会拍到灰色占位块
        wait_for_thumbnails(app, _visible_strips(detail))
        png = out_dir / f"0{order}-详情页-{label}.png"
        window.grab().save(str(png))
        shots.append(png)

    # 第六张：日志浮层（底部常驻状态条 + 点击唤出的浮层），供布局文档引用
    detail._select_stage(0)
    detail.log_panel.set_expanded(False)
    detail.log_view.clear()
    for line in sample_log_lines(book_title, DEMO_PAGE)[:9]:
        detail.log_view.append(line)
    detail.log_panel.set_expanded(True)
    pump(app, 10)
    wait_for_thumbnails(app, _visible_strips(detail))
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
