# -*- coding: utf-8 -*-
"""第二轮审计修复的护栏（2026-09-26，工作区自查轮）。

本模块钉住本轮（继 workbuddy 生产就绪度审计之后的独立扫描）修掉的问题，
防止回退。各项对应关系：

1. ``pdf_name`` 用户输入直接拼输出文件名：非法字符 / 保留设备名（``con.pdf``
   会"写进设备、阶段报成功但磁盘无文件"）/ 超长（NTFS 255）必须有校验。
2. ``border`` 无上界：``border 2000``（mm）→ ~23622px 四周留白 → 数 GB 画布
   ×并发线程直接 OOM。与 page_margins 的 100mm 上界同一口径。
3. ``page_number_format`` 拼错的值被 ``format_page_number`` 静默回落中文数字。
4. CLI ``--area`` choices 写死 [1,2,3]：文档/GUI/spec 都支持的「4 = 整页模式」
   被直接拒绝（实测复现）。choices 必须从 ``CROP_AREAS`` 派生。
5. ``write_bytes_atomic`` 临时名固定（无 pid/tid）：两个生产者并发写同一
   缩略图时 B 截断 A 正在写的内容、A 提交半截 JPEG 进缓存且不自愈。
6. runs.json 历史存整份 ``_effects``/``files``/``page_rects``：2400 页的书
   单条 0.5MB × 20 条 × 每 200ms 全量重写 = 每秒几十 MB 写放大。入史前剥掉。
7. ``sides_for_pages`` 的起始页不夹进 [1, total]：start_page=50、图片 30 张
   时 offset 全负 → 每页左右侧整体翻转。
8. EXIF 方向：extract quick 路径上报的尺寸必须按 EXIF 转正（消费端 cv2/Qt
   都转正，sizes.json 不转则 GUI 叠框坐标系整体错位）。
9. print 的进度分母 = 实际写入页数（skip_pages 存在时原先进度到不了 100%）。
"""

NAME = "audit_round2"
# tasklist 依赖：第 10 条断言要走真正的 `_open_detail` 入口，需要已就绪的
# ctx.tid（任务列表模块创建的夹具任务）。
DEPENDS: list[str] = ["tasklist"]
TITLE = "第二轮审计护栏"


def run(ctx) -> None:
    import io
    import threading
    from pathlib import Path

    from tests.selftests._context import ok

    repo = Path(__file__).resolve().parents[2]

    # ------------------------------------------------ 1. pdf_name 校验
    from core.command_spec import validate_pdf_name, validate_border

    for bad in ("a:b.pdf", "x*y", "con.pdf", "NUL.PDF", "a/b.pdf", "a\\b.pdf",
                "x" * 201):
        try:
            validate_pdf_name(bad)
            raise AssertionError(f"pdf_name {bad[:24]!r} 应被拒绝")
        except ValueError:
            pass
    ok("pdf_name 非法字符/保留名/超长被拒绝", True)
    for good in (None, "", "print.pdf", "长短短经[重制].pdf", "Vol.1 题名.pdf"):
        validate_pdf_name(good)
    ok("pdf_name 合法值放行（None/空/中文/带点）", True)

    # ------------------------------------------------ 2. border 上界
    try:
        validate_border("2000")
        raise AssertionError("border 2000 应被拒绝")
    except ValueError:
        pass
    validate_border("100")
    validate_border("20,30,25,100")
    ok("border 单边 100mm 上界生效、合法值放行", True)

    # ------------------------------------------------ 3. 页码样式校验
    from core.command_spec import PAGE_NUMBER_FORMATS, COMMAND_SPECS

    ok("页码样式枚举与 format_page_number 一致",
       set(PAGE_NUMBER_FORMATS) == {"chinese", "arabic", "ganzhi"},
       str(PAGE_NUMBER_FORMATS))
    validators = COMMAND_SPECS["print"].validators
    try:
        args_stub = type("A", (), {"get": staticmethod(
            lambda k, d=None: "roman" if k == "page_number_format" else None)})()
        for check in validators:
            check(args_stub)
        raise AssertionError("page_number_format=roman 应被拒绝")
    except ValueError:
        pass
    ok("print 校验器拒绝未知页码样式", True)

    # ------------------------------------------------ 4. CLI --area 含 4
    source = (repo / "cli" / "cli_args.py").read_text(encoding="utf-8")
    # ⚠️ 只数 area 的 choices（crop + cropremove 两处）；--type 的 [1,2,3]
    #    是输出图型枚举，合法保留，不能用全文文本匹配误伤
    ok("CLI --area choices 从 CROP_AREAS 派生（不再写死 [1,2,3]）",
       source.count("choices=list(CROP_AREAS)") == 2)
    from core.command_spec import CROP_AREAS

    ok("CROP_AREAS 包含整页模式 4", 4 in CROP_AREAS, str(CROP_AREAS))

    # ------------------------------------------------ 5. 原子写临时名唯一
    import sys

    sys.path.insert(0, str(repo))
    from utils.file_utils import write_bytes_atomic, _unique_tmp_name

    target = Path(ctx.tmp) if hasattr(ctx, "tmp") else None
    if target is None:  # 兜底（不该发生）
        import tempfile

        target = Path(tempfile.mkdtemp(prefix="guji_audit2_"))
    target.mkdir(parents=True, exist_ok=True)
    dst = target / "conc.jpg"
    errors: list[str] = []

    def _writer(tag: str) -> None:
        try:
            for i in range(12):
                write_bytes_atomic(dst, (f"{tag}-{i} " * 400).encode("ascii"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{tag}: {type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=_writer, args=(f"t{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    data = dst.read_bytes()
    ok("并发原子写同一目标不炸、不落半截",
       bool(not errors and data and (data.startswith(b"t") or data.startswith(b"t"))),
       f"errors={errors[:2]}")
    ok("原子写临时名带 pid/线程号（并发不再共用一个 .part）",
       "-" in _unique_tmp_name(dst) and _unique_tmp_name(dst).endswith(".part"),
       _unique_tmp_name(dst))
    leftovers = [p.name for p in target.glob("*.part")]
    ok("原子写成功后不留 .part 残留", not leftovers, str(leftovers))

    # ------------------------------------------------ 6. runs 历史瘦身
    from desktop.store.json_io import read_json, write_json

    runs_src = (repo / "desktop" / "store" / "runs.py").read_text(encoding="utf-8")
    ok("入史前剥离大块运行时字段",
       '"_effects", "files", "page_rects"' in runs_src.replace("'", '"'))

    # ------------------------------------------------ 7. 起始页夹紧
    from utils.page_layout import sides_for_pages

    sides = sides_for_pages(30, [], 50)
    alternates = all(
        sides[i] != sides[i + 1] for i in range(len(sides) - 1)
    )
    ok("start_page 超出总页数时夹进范围、严格左右交替、锚点页为 left",
       len(sides) == 30 and set(sides) <= {"left", "right"}
       and alternates and sides[-1] == "left", str(sides[:4]))
    sides2 = sides_for_pages(4, [], 1)
    ok("正常起始页行为不变", sides2 == ["left", "right", "left", "right"],
       str(sides2))

    # ------------------------------------------------ 8. EXIF 尺寸换算
    from utils.pdf_extract import _exif_swap_dims
    from PIL import Image

    img = Image.new("RGB", (100, 50), (200, 30, 30))
    exif = img.getexif()
    exif[274] = 6  # 90° 旋转：横竖互换
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    ok("EXIF 6 → 宽高互换", _exif_swap_dims(buf.getvalue(), 100, 50) == (50, 100))
    buf2 = io.BytesIO()
    img.save(buf2, format="JPEG")  # 无方向标签
    ok("无 EXIF 方向 → 尺寸原样", _exif_swap_dims(buf2.getvalue(), 100, 50) == (100, 50))

    # ------------------------------------------------ 9. print 进度分母
    print_src = (repo / "functions" / "print.py").read_text(encoding="utf-8")
    ok("print 进度分母为实际写入页数（total_written）",
       "total_written = max(0, total - len(skip_indices))" in print_src
       and "processed_count == total_written" in print_src)

    # ------------------------------------------------ 10. 详情页真的能进
    # ⚠️ 回归钉子（2026-09-27 事故）：set_task 改返回 bool 后漏写末尾
    #    `return True`，_open_detail 把 None 当"拒绝"→ 点「详情」永远停在
    #    列表页。既有测试都直接调 d.set_task() 不看返回值，抓不到这条——
    #    必须走真正的 _open_detail 入口断言切页结果。
    from PySide6.QtWidgets import QStackedWidget

    _w, _d = ctx.w, ctx.d
    _pages = _w.findChild(QStackedWidget, "pageRoot")
    _w._open_detail(ctx.tid)
    ok("点击「详情」真的切到详情页（set_task 返回 bool 契约）",
       _pages is not None and _pages.currentWidget() is _d
       and _d.task_id == ctx.tid,
       f"current={_pages.currentWidget() if _pages is not None else None}"
       f" / task_id={_d.task_id}")
