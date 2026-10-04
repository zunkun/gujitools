# -*- coding: utf-8 -*-
"""图片拼版护栏：版面规则、操作画布、页面结构、与第四步取图的联动。

用户口径：
1. 左侧一列「第一页 / 第二页 / …」，**虚线的「＋ 选择拼版」固定钉在左列
   最底部**（不跟在页码下面）；页条目**缩略图在上、文字在下**（用户
   2026-10-04），勾选框钉左上角、「✕」钉右上角；勾选页后清单下沿
   浮出「取消选择 / 批量删除」悬浮条，取消选择即收起；
2. 点「选择拼版」弹窗，从**剩余未被选择拼版的图片**里勾选（**只有三种
   可选形态**：1 张单独成页；2 张拼一页；1 张半幅 + 自动拼版；勾 0/≥3 张
   「开始拼版」不可点），点「开始拼版」生效——自动拼版规则见
   ``services.imposition.auto_impose_pages``（前一个左半幅+当前右半幅、
   **页号连续**才配对；整幅单独一页；首位/落单的半幅单独一页）；
   还能「删除图片」移出选择范围、进入已删除视图批量恢复；
3. 右侧操作区可拖动 / 缩放拉伸 / 旋转；**序号在前的排在右侧、序号大的在左侧**；
4. 拼版一旦生效，最后一步「生成 PDF」的取图来源就从第三步去底色换成拼版结果；
5. **点击选中**某张图后它带一圈**常显细虚线**（选中状态）；**按住鼠标操作
   期间**升级为带手柄的完整虚线框，松手回到细框；切页/点空白取消选中，
   右侧「当前图片样式」区只在有选中图时激活高亮。

⚠️ 本模块**自建任务与独立详情页**（不借 ctx.d）：拼版会往任务目录写产物、
改 print.json，跟其它模块共用一个页面会互相串状态。独立页在结尾整体销毁。
"""

NAME = "imposition"
DEPENDS: list[str] = []
TITLE = "图片拼版"

import shutil
import tempfile
from pathlib import Path

from tests.selftests._context import make_pdf, ok, pump

RED = (220, 40, 40)
GREEN = (30, 160, 60)
BLUE = (40, 80, 220)
YELLOW = (230, 190, 30)

#: 选中框/手柄的颜色（与 imposition_canvas.FRAME_COLOR 一致），像素判据用
FRAME_RGB = (0x0E, 0x7C, 0x8B)
#: 红色对齐线（与 imposition_canvas.SPINE_COLOR 一致），像素判据用
SPINE_RGB = (0xE0, 0x20, 0x20)
#: 灰色成品截图范围框（与 imposition_canvas.CROP_COLOR 一致），像素判据用
CROP_RGB = (0x5F, 0x63, 0x68)


def _mk(path: Path, color, size=(400, 600)) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


#: 编辑结果用的工作色：挑两个夹具色系里没有的颜色，像素断言不会被"本来就
#: 是这个颜色"糊弄过去
EDIT_ITEM_COLOR = (12, 200, 180)
EDIT_SPREAD_COLOR = (200, 30, 200)


def _solid_qimage(color, width: int = 64, height: int = 48):
    """纯色 QImage（编辑结果的替身）。"""
    from PySide6.QtGui import QColor, QImage

    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(QColor(*color))
    return image


def _qimage_pixel(path: Path, x: int, y: int):
    """读文件里一个像素的 (r, g, b)；读不到返回 None。"""
    from PySide6.QtGui import QImage

    image = QImage(str(path))
    if image.isNull():
        return None
    c = image.pixelColor(x, y)
    return (c.red(), c.green(), c.blue())


def _names(paths) -> list[str]:
    return [Path(p).name for p in paths]


def _count_near(image, rgb, tol: int = 28, step: int = 2) -> int:
    """数一数画面上有多少像素接近 ``rgb``（隔点取样，够用且快）。"""
    total = 0
    for y in range(0, image.height(), step):
        for x in range(0, image.width(), step):
            color = image.pixelColor(x, y)
            if (abs(color.red() - rgb[0]) <= tol
                    and abs(color.green() - rgb[1]) <= tol
                    and abs(color.blue() - rgb[2]) <= tol):
                total += 1
    return total


def _count_non_white(image, tol: int = 12, step: int = 2) -> int:
    """数一数有多少像素不接近纯白（确认缩略图**真的画上了内容**）。"""
    total = 0
    for y in range(0, image.height(), step):
        for x in range(0, image.width(), step):
            color = image.pixelColor(x, y)
            if (color.red() < 255 - tol or color.green() < 255 - tol
                    or color.blue() < 255 - tol):
                total += 1
    return total


def run(ctx) -> None:
    from PySide6.QtCore import QPointF, QSize, Qt

    from desktop.components.imposition.canvas import ImpositionCanvas
    from desktop.components.imposition.picker import (
        DIALOG_H, DIALOG_W, THUMB_H, THUMB_W, ImpositionPickerDialog,
    )
    from desktop.components.imposition.page_list import _AddEntry, _PageEntry
    from desktop.components.imposition.view import ImpositionViewWidget
    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.services import imposition as S
    from desktop.store import IMPOSITION_INDEX, TaskStore

    tmp = Path(tempfile.mkdtemp(prefix="guji_imposition_"))
    page = None
    try:
        # ---------------- 1. 版面规则（纯逻辑，无 Qt）----------------
        src = tmp / "src"
        a = _mk(src / "1-r.png", RED)
        b = _mk(src / "1-l.png", GREEN)
        c = _mk(src / "2-r.png", BLUE)
        d = _mk(src / "2-l.png", YELLOW)

        made = S.make_page([a, b])
        ok("make_page 能造出一页拼版", made is not None)
        right, left = made["items"]
        ok("序号在前的图片落在**右侧**槽位",
           Path(right["file"]).name == "1-r.png"
           and Path(left["file"]).name == "1-l.png")
        ok("右侧槽位的 x 大于左侧（版面左右就位）",
           right["rect"][0] > left["rect"][0],
           f"{right['rect']} vs {left['rect']}")
        ok("页面里**没有纸张**（sheet 键已删除）",
           "sheet" not in made, str(list(made)))
        ok("默认版面按**原始像素**摆放（不改动用户的图）",
           right["rect"][2:] == [400.0, 600.0]
           and left["rect"][2:] == [400.0, 600.0],
           f"{right['rect']} / {left['rect']}")
        ok("只给一张图造不出一页拼版", S.make_page([a]) is None)

        composed = S.compose_page(made)
        ok("产出图 = 两张图外接框的紧裁（无纸张：图上多大就多大）",
           composed.size == (800, 600), str(composed.size))
        ok("合成后：左侧是 1-l、右侧是 1-r（像素级）",
           composed.getpixel((700, 300)) == RED
           and composed.getpixel((100, 300)) == GREEN,
           f"{composed.getpixel((700, 300))} / {composed.getpixel((100, 300))}")

        # 旋转是**顺时针**口径：PIL 侧取负，两边必须一致。
        # ⚠️ 判据必须用**非均匀**图案，否则 ±90° 的中心像素一样，注入翻转方向
        # 也测不出来（第一版就是这么假绿的）。用「左半蓝 / 右半绿」的图：
        # 顺时针 90° 后左半应转到**上边**、右半转到下边。
        from PIL import Image

        striped = Image.new("RGB", (400, 600), GREEN)
        striped.paste(BLUE, (0, 0, 200, 600))
        striped_path = tmp / "rotate-probe.png"
        striped.save(striped_path)
        rotated_page = S.normalize_page({
            "items": [{"file": str(striped_path), "rect": [0.0, 0.0, 400.0, 600.0],
                       "rotation": 90.0}],
        })
        shot = S.compose_page(rotated_page)
        # 无纸张：产出图 = 旋转后的外接框（400×600 转 90° → 600×400）
        ok("旋转后的产出图按外接框紧裁",
           shot.size == (600, 400), str(shot.size))
        ok("旋转 90° 是**顺时针**（左半转到上边、右半转到下边）",
           shot.getpixel((300, 80)) == BLUE
           and shot.getpixel((300, 320)) == GREEN,
           f"上={shot.getpixel((300, 80))} 下={shot.getpixel((300, 320))}")

        ok("坏页被过滤（项为空 / 无文件 / 非字典）",
           all(S.normalize_page(bad) is None for bad in (
               {"items": []},
               {"items": [{"file": "", "rect": [0, 0, 9, 9]}]},
               "垃圾",
           )))
        # 老任务存过 "sheet"：读进来要**忽略**它，不能因此判成坏页
        legacy = S.normalize_page(
            {"sheet": [800, 600],
             "items": [{"file": "x.png", "rect": [0, 0, 9, 9]}]}
        )
        ok("老文档里的 sheet 被忽略（老任务照样能读）",
           legacy is not None and "sheet" not in legacy, str(legacy))
        ok("中文页码标签",
           [S.cn_page_label(i) for i in (0, 1, 9, 10, 19)] ==
           ["第一页", "第二页", "第十页", "第十一页", "第二十页"])

        # ---------------- 2. 落盘与清理 ----------------
        out = tmp / "sweep"
        out.mkdir()
        _mk(out / "0009.png", (0, 0, 0), (8, 8))  # 上一轮多出来的页
        written = S.compose_doc({"pages": [made, made]}, out)
        ok("落盘按页码命名 0001/0002",
           _names(written) == ["0001.png", "0002.png"], str(_names(written)))
        ok("上一轮多出来的 0009.png 被清掉", not (out / "0009.png").exists())
        S.compose_doc({"pages": []}, out)
        ok("清空拼版后产物目录也清空", list(out.glob("*.png")) == [])

        # 清理基准是**页数**而不是"写成功的文件数"：中间某页合成失败会留下编号
        # 空洞（0001/0003），按写成功数去清会把 0003 这页好内容误删。
        gap = tmp / "sweep_gap"
        gap.mkdir()
        for name in ("0001.png", "0003.png", "0004.png"):
            _mk(gap / name, (0, 0, 0), (8, 8))
        S._sweep_stale(gap, 3)
        ok("编号空洞里的页不会被误删（只清超出页数的）",
           sorted(p.name for p in gap.glob("*.png")) == ["0001.png", "0003.png"],
           str(sorted(p.name for p in gap.glob("*.png"))))

        # ---------------- 2b. 并发合成（用户 2026-10-03 报「程序容易跑崩溃」）----
        # 根因：后台防抖合成（ImpositionComposeWorker）与生成 PDF 前的同步合成
        # （_compose_imposition_now）打到**同一个目录**且原先**无任何互斥**，
        # 写盘又是 `image.save()` **就地截断重写**。实测 8 线程并发时老实现直接
        # 抛 PermissionError（一个线程正写 another's 文件句柄），页面就崩。
        # 现在是「整轮持锁 + 原子写（临时文件 + os.replace）」。
        #
        # ⚠️ 源图必须**够大**：400×600 的图 save 只需几毫秒，窗口太窄，
        #    即便去掉锁与原子写也可能假绿（第一版就栽在这）。1400×1800 才
        #    能稳定撞上"一个线程正写 another's 文件句柄"。
        #    实测（8 线程 × 6 页）：老实现抛 PermissionError；只加锁 ⇒ 绿；
        #    只加原子写 ⇒ 仍绿；两道都有 ⇒ 绿。它们挡的是不同故障，见
        #    services/imposition.py 里 _COMPOSE_LOCK 与 _save_page_atomic 的注释。
        import threading

        big = _mk(tmp / "big.png", GREEN, (1400, 1800))
        big_page = S.normalize_page({
            "items": [{"file": str(big), "rect": [0.0, 0.0, 1400.0, 1800.0],
                       "rotation": 0}]
        })
        race_dir = tmp / "compose_race"
        race_dir.mkdir()
        doc_race = {"pages": [big_page] * 6}
        errors: list = []

        def _compose_many():
            try:
                S.compose_doc(doc_race, race_dir)
            except Exception as exc:  # noqa: BLE001 - 自测要看到任何炸
                errors.append(f"{type(exc).__name__}: {exc}")

        threads = [threading.Thread(target=_compose_many) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=180)
        ok("多线程并发合成不抛异常（老实现这里会 PermissionError）",
           not errors, str(errors[:3]))

        from PIL import Image as _PILImage

        def _decodable(path) -> bool:
            """真解码一遍：半张 PNG 会在这里抛或给出异常尺寸。"""
            try:
                with _PILImage.open(path) as im:
                    im.load()
                return True
            except Exception:  # noqa: BLE001 - 打不开就是坏图
                return False

        ok("并发合成后每页都是完整可解码的 PNG（不是半张图）",
           all(_decodable(race_dir / n)
               for n in ("0001.png", "0003.png", "0006.png")),
           str(sorted(p.name for p in race_dir.glob("*.png"))))
        ok("并发合成不留 .part 临时文件",
           list(race_dir.glob("*.part")) == [],
           str(list(race_dir.glob("*.part"))))
        ok("并发合成页数正确（没被 _sweep_stale 误删）",
           len(list(race_dir.glob("*.png"))) == 6,
           str(len(list(race_dir.glob("*.png")))))

        # ---------------- 3. 剩余未选清单 ----------------
        remaining = S.remaining_files([a, b, c, d], {"pages": [made]})
        ok("剩余未拼版的图片 = 未被任何页引用的那些",
           _names(remaining) == ["2-r.png", "2-l.png"], str(_names(remaining)))
        # 「删除图片」黑名单（removed 字段）：软删除，恢复即回到候选
        norm = S.normalize_doc({"enabled": True, "pages": [made],
                                "removed": [str(c), str(c), "", "  "]})
        ok("normalize_doc 保留黑名单（去重、丢空项、保序）",
           norm["removed"] == [str(c)], str(norm.get("removed")))
        ok("老文档没有 removed 键也能读",
           S.normalize_doc({"enabled": False, "pages": []})["removed"] == [])
        ok("remaining_files 同时排除已用与已删除的图",
           _names(S.remaining_files([a, b, c, d],
                  {"pages": [made], "removed": [str(c)]})) == ["2-l.png"],
           str(_names(S.remaining_files([a, b, c, d],
                      {"pages": [made], "removed": [str(c)]}))))
        ok("excluded_files 按源清单顺序列出被删除的图",
           _names(S.excluded_files([a, b, c, d], {"removed": [str(d), str(c)]}))
           == ["2-r.png", "2-l.png"],
           str(_names(S.excluded_files([a, b, c, d],
                      {"removed": [str(d), str(c)]}))))

        # ---------------- 3b. 自动拼版规则（用户 2026-09-30）----------------
        # 1. 默认两张半栏拼一页：配对必须是「前一个左半幅 + 当前右半幅」；
        # 2. 页号必须连续（不连续的图片不可以合并在一页）；
        # 3. 整幅(fullcontent)标注的图单独一页；等配对的上一张因此落单；
        #    整幅后拼版重开；首位/整幅后的右半幅单独一页。
        full = _mk(src / "3.png", (128, 128, 128))

        def _page_shapes(pages):
            return [tuple(Path(i["file"]).name for i in p["items"])
                    for p in pages]

        ok("classify_source 按文件名后缀分形态（-r/-l/无后缀）",
           S.classify_source(a) == S.SOURCE_RIGHT
           and S.classify_source(b) == S.SOURCE_LEFT
           and S.classify_source(full) == S.SOURCE_FULL,
           f"{S.classify_source(a)}/{S.classify_source(b)}/"
           f"{S.classify_source(full)}")
        single = S.make_single_page(full)
        ok("整幅图自成一页（版面只有一项、原始尺寸）",
           single is not None and len(single["items"]) == 1
           and Path(single["items"][0]["file"]).name == "3.png"
           and single["items"][0]["rect"][2:] == [400.0, 600.0],
           str(single))
        ok("单图页产出 = 原图尺寸紧裁",
           S.compose_page(single).size == (400, 600),
           str(S.compose_page(single).size))

        auto = S.auto_impose_pages([a, b, c, d])
        ok("自动拼版（r,l,r,l）：首位 -r 单独一页，左半幅与下一个右半幅配对",
           _page_shapes(auto) == [("1-r.png",), ("1-l.png", "2-r.png"),
                                  ("2-l.png",)],
           str(_page_shapes(auto)))
        ok("自动配对同样序号在前的进右槽",
           Path(auto[1]["items"][0]["file"]).name == "1-l.png")
        ok("自动拼版：末尾落单的左半幅单独一页",
           len(auto[-1]["items"]) == 1
           and Path(auto[-1]["items"][0]["file"]).name == "2-l.png")

        auto_full = S.auto_impose_pages([full, a, b, c, d])
        ok("整幅后拼版重开：整幅单独一页、随后首位 -r 单独一页、再左+右配对",
           _page_shapes(auto_full) == [("3.png",), ("1-r.png",),
                                       ("1-l.png", "2-r.png"), ("2-l.png",)],
           str(_page_shapes(auto_full)))
        ok("上一张等配对时遇到整幅 → 上一张单独一页（整幅不与它拼）",
           _page_shapes(S.auto_impose_pages([b, full])) == [("1-l.png",),
                                                            ("3.png",)],
           str(_page_shapes(S.auto_impose_pages([b, full]))))
        ok("整幅夹在中间同样断开配对",
           _page_shapes(S.auto_impose_pages([a, b, full, c, d]))
           == [("1-r.png",), ("1-l.png",), ("3.png",), ("2-r.png",),
               ("2-l.png",)],
           str(_page_shapes(S.auto_impose_pages([a, b, full, c, d]))))

        # 页号必须连续（用户 2026-09-30：不连续的图片不可以合并在一页）
        e = _mk(src / "5-r.png", RED)
        f2 = _mk(src / "4-l.png", GREEN)
        ok("source_page_number 按文件名前缀解析（1-r→1、004-l→4、cover→None）",
           S.source_page_number(a) == 1
           and S.source_page_number(src / "004-l.png") == 4
           and S.source_page_number(src / "cover.png") is None,
           f"{S.source_page_number(a)}/"
           f"{S.source_page_number(src / '004-l.png')}/"
           f"{S.source_page_number(src / 'cover.png')}")
        ok("页号不连续（1-l 之后直接 5-r）→ 不配对、各自单独一页",
           _page_shapes(S.auto_impose_pages([b, e])) == [("1-l.png",),
                                                         ("5-r.png",)],
           str(_page_shapes(S.auto_impose_pages([b, e]))))
        ok("断口后重新开始：5-r 等不到 4-l（序号也不连续）、4-l 落单",
           _page_shapes(S.auto_impose_pages([a, b, e, f2]))
           == [("1-r.png",), ("1-l.png",), ("5-r.png",), ("4-l.png",)],
           str(_page_shapes(S.auto_impose_pages([a, b, e, f2]))))
        ok("同一页号的 l→r 不配对（必须跨页号：前一左＋后一右）",
           _page_shapes(S.auto_impose_pages([d, c]))
           == [("2-l.png",), ("2-r.png",)],
           str(_page_shapes(S.auto_impose_pages([d, c]))))
        ok("读不到尺寸的图跳过（不产出残页）",
           S.auto_impose_pages([tmp / "missing.png"]) == [])
        ok("空清单自动拼版 = 空页清单", S.auto_impose_pages([]) == [])

        # ---------------- 4. 操作画布（拖动 / 缩放 / 旋转 / 复位）----------------
        from PySide6.QtGui import QImage

        canvas = ImpositionCanvas()
        canvas.resize(600, 600)
        canvas.set_page(made["items"])
        ok("画布载入两张图、默认不选中（切页后图片操作区不激活）",
           len(canvas.items()) == 2 and canvas.selected() == -1,
           str(canvas.selected()))
        ok("画布能从文件解出图（不是空图）",
           not QImage(made["items"][0]["file"]).isNull())
        # 图缓存必须随换页清掉：一页两张几千像素见方的原图，一路翻页会吃到 GB 级
        canvas._image(made["items"][0]["file"])
        ok("画布按需缓存当前页的图", len(canvas._images) == 1)
        canvas.set_page(made["items"])
        ok("换页丢掉上一页的图缓存（内存有界）", canvas._images == {})

        canvas.select(1)
        knob = canvas._rotate_knob(1)
        ok("选中项上方有旋转钮（在框外、水平居中）",
           abs(knob.x() - canvas._rect_px(1).center().x()) < 0.01
           and knob.y() < canvas._rect_px(1).y(),
           f"{knob.x():.1f},{knob.y():.1f}")
        hit = canvas._hit_handle(1, knob)
        local = canvas._to_local_px(1, knob)
        klocal = canvas._rotate_knob_local(1)
        ok("旋转钮能被命中", hit == 8,
           f"hit={hit} local=({local.x():.2f},{local.y():.2f}) "
           f"knob_local=({klocal.x():.2f},{klocal.y():.2f})")
        corners = [QPointF(x, y) for x, y in canvas._handle_positions(1)]
        ok("四角手柄能按位置命中（左上=0 / 右上=1 / 右下=2 / 左下=3）",
           [canvas._hit_handle(1, pos) for pos in corners[:4]] == [0, 1, 2, 3],
           str([canvas._hit_handle(1, pos) for pos in corners[:4]]))
        ok("四边命中带落在边上（上边=4 / 右边=5）",
           canvas._hit_handle(1, corners[4]) == 4
           and canvas._hit_handle(1, corners[5]) == 5)
        canvas.rotate_selected(90.0)
        ok("旋转 90° 写进 items",
           abs(canvas.items()[1]["rotation"] - 90.0) < 0.01,
           str(canvas.items()[1]["rotation"]))
        # 默认版面（复位用）：按两张图的**原始像素**并排，旋转归零
        reset = S.default_items([str(a), str(b)])
        ok("默认版面 = 原始尺寸并排 + 无旋转（复位用）",
           reset is not None
           and reset[0]["rect"] == [400.0, 0.0, 400.0, 600.0]
           and reset[1]["rect"] == [0.0, 0.0, 400.0, 600.0]
           and all(item["rotation"] == 0.0 for item in reset),
           str(reset))

        events: list[list] = []
        canvas.items_changed.connect(events.append)
        canvas.select(0)
        rect0 = canvas.items()[0]["rect"][0]
        canvas._items[0]["rect"][0] += 25.0
        canvas._dirty = True
        ok("未松手时还不发信号（拖动过程只重绘）", not events)
        canvas.flush_pending()
        ok("flush_pending 补齐未松手的改动",
           len(events) == 1
           and abs(events[0][0]["rect"][0] - (rect0 + 25.0)) < 0.01,
           str(events[0][0]["rect"] if events else None))
        ok("松手后不再重复发（dirty 已清）", not canvas.flush_pending())

        # ---------------- 4b. 选中态常显 + 操作框只在按住期间（用户 2026-09-30）
        # 「点击某一张图，某一张图选中状态」：选中的图带常显细虚线；按住操作
        # 期间升级为带手柄的完整虚线框，松手回到细框。
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QMouseEvent

        def _mouse(kind, pos):
            return QMouseEvent(
                kind, QPointF(pos[0], pos[1]),
                Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
            )

        canvas.select(1)
        selected_px = _count_near(canvas.grab().toImage(), FRAME_RGB)
        ok("只选中（没按住）也画**细选中框**（选中状态常显）",
           selected_px > 20 and not canvas.frame_visible(),
           f"选中框像素={selected_px}")
        center = canvas._rect_px(1).center()
        canvas.mousePressEvent(
            _mouse(QEvent.Type.MouseButtonPress, (center.x(), center.y()))
        )
        ok("按下鼠标 → 升级为带手柄的完整操作框", canvas.frame_visible())
        pressed_px = _count_near(canvas.grab().toImage(), FRAME_RGB)
        ok("按住时确实画出了虚线框 + 手柄 + 旋转钮",
           pressed_px > selected_px + 100,
           f"选中框 {selected_px} → 按住 {pressed_px} 像素")
        canvas.mouseReleaseEvent(
            _mouse(QEvent.Type.MouseButtonRelease, (center.x(), center.y()))
        )
        released_px = _count_near(canvas.grab().toImage(), FRAME_RGB)
        ok("松手 → 手柄全框消失、回到常显选中细框",
           not canvas.frame_visible() and 0 < released_px < pressed_px,
           f"选中={selected_px} 按住={pressed_px} 松手={released_px}")
        # 虚线是**样式常量**层面的要求（像素级"是不是虚线"太脆，改查定义处）
        canvas_src = (
            Path(__file__).resolve().parents[2]
            / "desktop" / "components" / "imposition" / "canvas.py"
        ).read_text(encoding="utf-8")
        ok("选中框用的是 Qt.DashLine（虚线）",
           "FRAME_STYLE = Qt.DashLine" in canvas_src
           and "FRAME_STYLE," in canvas_src,
           "框线样式定义/使用处不匹配")

        # ---------------- 4c. 无纸张 + 不限制图片位置/大小（用户 2026-09-30）------
        # 「拼版不需要设置纸张，只需要背景是白色的」「拉伸、移动后可能超出原本
        # 界限，现在是不显示了，现在不要限制」
        outside = ImpositionCanvas()
        outside.resize(600, 600)
        far = [{"file": str(a), "rect": [700.0, 0.0, 400.0, 600.0],
                "rotation": 0.0}]
        outside.set_page(far)
        scene = outside._scene_rect()
        ok("可视范围就是图的外接框（没有纸张框着）",
           abs(scene.x() - 700.0) < 0.01 and abs(scene.width() - 400.0) < 0.01,
           f"x={scene.x():.0f} w={scene.width():.0f}")
        ok("摆到很远的图**照常画出来**（不再被裁掉）",
           _count_near(outside.grab().toImage(), RED) > 50,
           f"红色采样={_count_near(outside.grab().toImage(), RED)}")

        # 拖动没有任何范围夹取：拖多远就停多远
        outside.select(0)
        start = outside._rect_px(0).center()
        outside.mousePressEvent(
            _mouse(QEvent.Type.MouseButtonPress, (start.x(), start.y()))
        )
        outside.mouseMoveEvent(
            _mouse(QEvent.Type.MouseMove, (start.x() + 200, start.y() + 120))
        )
        outside.mouseReleaseEvent(
            _mouse(QEvent.Type.MouseButtonRelease, (start.x() + 200, start.y() + 120))
        )
        moved = outside.items()[0]["rect"]
        ok("拖动不设范围限制（拖多远就停多远）",
           moved[0] > 900.0 and moved[1] > 100.0, f"x={moved[0]:.0f} y={moved[1]:.0f}")

        # 缩放/拉伸同样不设上限
        outside._items[0]["rect"] = [0.0, 0.0, 400.0, 600.0]
        outside._grab_rect = [0.0, 0.0, 400.0, 600.0]
        outside._handle = 5  # 右边
        big = outside._resize_from_handle(
            _mouse(QEvent.Type.MouseMove, (1400.0, 300.0)), False
        )
        ok("缩放不设上限（想拉多宽就多宽）",
           big[2] > 1000.0, f"宽={big[2]:.0f}")
        outside.deleteLater()
        canvas.deleteLater()

        # ---------------- 5. 左列结构与选择弹窗 ----------------
        view = ImpositionViewWidget()
        view.resize(900, 600)
        view.set_pages([made, made])
        ok("左列 = 每页一个条目",
           len(view.page_list.entries()) == 2
           and all(isinstance(e, _PageEntry) for e in view.page_list.entries()))
        ok("左列条目是中文页码",
           [e.title_label.text() for e in view.page_list.entries()] == ["第一页", "第二页"])
        ok("末格是虚线「＋ 选择拼版」", isinstance(view.page_list.add_entry, _AddEntry))
        # 「＋ 选择拼版」钉在左列最底部（滚动区之外，页多页少都看得见）
        ok("虚线格钉在左列最底部（滚动区之外、列内最后一格）",
           view.page_list.layout().itemAt(view.page_list.layout().count() - 1).widget()
           is view.page_list.add_entry
           and view.page_list.add_entry.parent() is view.page_list
           and view.page_list.list_box.indexOf(view.page_list.add_entry) == -1)
        view.show()
        pump(ctx.app, times=6)

        # 「✕」只在当前页右侧显示；点它发 remove_requested（释放该页图片）
        view.set_current(1)
        ok("「✕」只在当前页右侧显示",
           not view.page_list.entries()[0].remove_button.isVisibleTo(view.page_list)
           and view.page_list.entries()[1].remove_button.isVisibleTo(view.page_list))
        removed = []
        view.page_remove_requested.connect(removed.append)
        view.page_list.entries()[1].remove_button.click()
        ok("点「✕」发 remove_requested(该页下标)", removed == [1], str(removed))

        # ---- 勾选多选 + 悬浮批量操作框（用户 2026-09-30）----
        # 每个条目左上角是勾选框（2026-10-04 起：缩略图在上、文字在下，
        # 勾选框钉左上、「✕」钉右上）；勾了页，悬浮框（「已选 N 页」+
        # 「取消选择」「批量删除」）悬在页码栏右侧中部（可拖动），勾选数
        # 归零自动收起；勾选框点击不触发切页/排序；重建清单时勾选按副标题
        # 跨重建保留。
        entries = view.page_list.entries()
        ok("条目左上有勾选框（缩略图在上、文字在下、勾选框贴左上角）",
           all(e.checkbox.isVisibleTo(e) for e in entries)
           and all(e.checkbox.x() < e.width() // 2 for e in entries)
           and all(e.checkbox.y() < e.thumb.y() for e in entries)
           and all(e.thumb.y() < e.title_label.y() <= e.caption_label.y()
                   for e in entries),
           str([(e.checkbox.x(), e.checkbox.y(), e.thumb.y(),
                 e.title_label.y()) for e in entries]))
        ok("没勾选 → 悬浮批量条收起",
           not view.page_list.select_bar.isVisibleTo(view.page_list))
        clicks = []
        view.page_selected.connect(clicks.append)
        entries[0].checkbox.click()
        ok("点勾选框不触发切页", clicks == [], str(clicks))
        ok("勾 1 页 → 悬浮条浮出、计数正确",
           view.page_list.checked_indexes() == [0]
           and view.page_list.select_bar.isVisibleTo(view.page_list)
           and view.page_list.select_bar.count_label.text() == "已选 1 页",
           view.page_list.select_bar.count_label.text())
        entries[1].checkbox.setChecked(True)
        ok("第二个也勾上 → 升序两页",
           view.page_list.checked_indexes() == [0, 1]
           and view.page_list.select_bar.count_label.text() == "已选 2 页",
           view.page_list.select_bar.count_label.text())
        view.page_list.set_pages(
            [" · ".join(S.page_source_stems(p)) for p in (made, made)],
            current=0,
        )  # 同样两页重建（caption 不变）→ 勾选跨重建保留
        ok("重建清单后勾选保留（拖动排序不丢勾）",
           view.page_list.checked_indexes() == [0, 1]
           and view.page_list.select_bar.isVisibleTo(view.page_list),
           str(view.page_list.checked_indexes()))
        view.page_list.set_pages(["甲右 · 甲左", "乙右 · 乙左"], current=0)
        # 两页副标题都换了 → 保留集合里没有它们的 caption → 全部落选
        ok("重建后只保留仍在的勾选（悬浮条随之收起）",
           view.page_list.checked_indexes() == []
           and not view.page_list.select_bar.isVisibleTo(view.page_list),
           str(view.page_list.checked_indexes()))
        entries = view.page_list.entries()
        batches = []
        view.pages_batch_delete_requested.connect(lambda: batches.append(1))
        entries[0].checkbox.setChecked(True)
        view.page_list.select_bar.delete_button.click()
        ok("点悬浮条「批量删除」发批量删除信号",
           batches == [1] and view.page_list.checked_indexes() == [0],
           str(batches))
        view.page_list.select_bar.clear_button.click()
        ok("点「取消选择」清空勾选、悬浮条收起",
           view.page_list.checked_indexes() == []
           and not view.page_list.select_bar.isVisibleTo(view.page_list),
           str(view.page_list.checked_indexes()))

        # ---- 悬浮框摆位与拖动（用户 2026-09-30：页码栏右侧中部、可拖）----
        bar = view.page_list.select_bar
        entries[0].checkbox.setChecked(True)
        col = view.page_list.geometry()  # 页码栏在视图坐标系里的位置
        geo = bar.geometry()
        ok("悬浮框悬在页码栏右缘（浮到右侧画布上，不压底部）",
           geo.x() + geo.width() > col.right() - 12
           and geo.y() + geo.height() < col.bottom(),
           f"bar={geo} col={col}")
        ok("悬浮框垂直居中于页码栏",
           abs(geo.center().y() - col.center().y()) <= 2,
           f"{geo.center().y()} vs {col.center().y()}")
        ok("「批量删除」红底高亮、「取消选择」主色标记",
           "#E02020" in bar.delete_button.styleSheet()
           and "#E6F2F4" in bar.clear_button.styleSheet())
        # 合成鼠标拖一下：光标全局位置走 mapToGlobal 口径，delta 可预期
        bar.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, (5, 5)))
        bar.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, (5, 65)))
        bar.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, (5, 65)))
        ok("按住可拖动悬浮框（拖过就不再自动摆位）",
           bar._user_moved and bar.geometry().y() == geo.y() + 60,
           str(bar.geometry()))
        bar.clear_button.click()
        ok("拖动后「取消选择」照常清空并收起",
           view.page_list.checked_indexes() == []
           and not bar.isVisibleTo(view.page_list),
           str(view.page_list.checked_indexes()))

        # 拖动排序：按住移动进入拖动态、松手不算单击；落点换算口径（移除后）
        selection = []
        view.page_selected.connect(selection.append)
        entry = view.page_list.entries()[0]
        entry.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, (10, 10)))
        entry.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, (10, 60)))
        ok("按住上下拖进入拖动态", entry._dragging)
        entry.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, (10, 60)))
        ok("拖动松手不算单击切页", selection == [], str(selection))
        reorders = []
        view.page_reorder_requested.connect(
            lambda a, b: reorders.append((a, b)))
        view.page_list._drag_from = 0
        view.page_list._drag_drop = 2
        view.page_list._finish_drag()
        ok("拖动排序：0 拖到末尾 → (0, 1)", reorders == [(0, 1)], str(reorders))
        view.page_list._drag_from = 1
        view.page_list._drag_drop = 0
        view.page_list._finish_drag()
        ok("拖动排序：1 拖到最前 → (1, 0)", reorders == [(0, 1), (1, 0)],
           str(reorders))
        view.page_list._drag_from = 1
        view.page_list._drag_drop = 2  # 落回原位（自己后面一格也是原位）
        view.page_list._finish_drag()
        ok("落回原位不发排序信号", len(reorders) == 2, str(reorders))

        # ---- 选中态（用户 2026-09-30：点图才有选中；切页后图片操作区不激活）
        made2 = S.make_page([c, d])
        view.set_pages([made, made2], current=0)
        ok("载页后默认不选中", view.canvas.selected() == -1,
           str(view.canvas.selected()))
        view.canvas.select(1)
        view.set_pages([made, made2], current=0)
        ok("同页数据回灌不清选中（拖动落盘后的刷新不掉选中态）",
           view.canvas.selected() == 1, str(view.canvas.selected()))
        view.set_current(1)
        ok("切到另一页后选中清空",
           view.canvas.selected() == -1, str(view.canvas.selected()))

        # ---- 拖动排序（2026-09-30 三稿口径：拖动中清单一动不动、不留空档
        # ——本体置灰留原位，幽灵卡跟光标走，细线指示落点；松手滑进落点才发信号）
        view.set_pages([made, made2], current=0)
        pl = view.page_list
        live = []
        view.page_reorder_requested.connect(lambda a, b: live.append((a, b)))
        drag = pl.entries()[0]
        other = pl.entries()[1]
        y_drag, y_other = drag.y(), other.y()
        # 合成环境没有真实按住的鼠标键，先把轮询架空（否则 _poll_drag
        # 检测到无按键立刻收尾），只验证状态流转本身
        pl._poll_drag = lambda: None
        pl._on_drag_started(0)
        del pl._poll_drag
        ok("拖动开始：本体置灰留原位、幽灵卡跟进（不是本体自己动）",
           drag._dimmed and not drag._drag_active
           and pl._ghost is not None and pl._ghost is not drag
           and pl._ghost._drag_active and pl._flow == [other],
           f"ghost={pl._ghost}")
        ok("清单纹丝不动、无空档（原位置不被空出来）",
           drag.y() == y_drag and other.y() == y_other,
           f"drag.y={drag.y()} vs {y_drag} other.y={other.y()} vs {y_other}")
        ok("落点还在原位 → 指示线藏着", not pl._indicator.isVisible())
        pl._drag_drop = 1
        pl._place_indicator()
        ok("落点变了 → 指示线画在落点条目下缘",
           pl._indicator.isVisible() and pl._indicator.y() > other.y(),
           f"y={pl._indicator.y()} other.y={other.y()}")
        pl._finish_drag()  # 幽灵卡滑进落点的动画启动，动画走完才发信号
        ok("松手瞬间未发信号（先滑进落点）", live == [], str(live))
        ok("落位动画进行中", pl._committing)
        pump(ctx.app, times=6, interval=0.05)  # 等落位动画走完（140ms）
        ok("落位完成发信号 (0,1)", live == [(0, 1)], str(live))
        ok("收尾干净：幽灵卡消散、本体回亮、流程态清零",
           not drag._dimmed and pl._ghost is None
           and not pl._committing and pl._flow == [],
           f"dim={drag._dimmed} ghost={pl._ghost} committing={pl._committing}")

        # 拖回原位：不发信号、无残留
        pl._poll_drag = lambda: None
        pl._on_drag_started(1)
        del pl._poll_drag
        pl._finish_drag()  # drop 仍是原位 → 幽灵卡就地消散，不发信号
        pump(ctx.app, times=4, interval=0.05)
        ok("拖回原位不发信号、无残留",
           len(live) == 1 and pl._ghost is None and not pl._committing
           and pl._drag_entry is None and not other._dimmed,
           f"live={live} ghost={pl._ghost}")

        view.hide()
        view.deleteLater()

        dialog = ImpositionPickerDialog([c, d])
        ok("弹窗列出两张候选",
           dialog.count() == 2
           and dialog.cards[0].path.name == "2-r.png",
           f"count={dialog.count()}")
        # 「选择图片采用 GRID 模式或者 flex 模式，一行好几个，选框宽一些」
        dialog.resize(820, 640)
        dialog.show()
        pump(ctx.app, times=10)
        ok("卡片网格按宽度自动排成多列（flex 换行）",
           dialog.body.columns() >= 3, f"列数={dialog.body.columns()}")
        ok("卡片够宽够高（≥ 180×240）",
           dialog.cards[0].width() >= 180 and dialog.cards[0].height() >= 240,
           f"{dialog.cards[0].width()}x{dialog.cards[0].height()}")
        ok("弹窗够宽（≥ 760px）", dialog.width() >= 760, str(dialog.width()))
        # 用户截图报过「图片没有正常显示、也没有文字」：缩略图必须是**固定尺寸**
        # 且真的画进了内容（不是空白小条），名字标签必须有文字。
        pump(ctx.app, times=20)
        card = dialog.cards[0]
        ok("缩略图是固定尺寸的图（不是一小条）",
           card.thumb.size() == QSize(THUMB_W, THUMB_H),
           f"{card.thumb.size()}")
        ok("缩略图真的画上了内容（不是全白/空图）",
           card._pixmap.width() == THUMB_W and card._pixmap.height() == THUMB_H
           and _count_non_white(card._pixmap.toImage()) > 0,
           f"pixmap={card._pixmap.size()} 非白像素={_count_non_white(card._pixmap.toImage())}")
        ok("卡片有名字文字（用户报过『没有显示文字』）",
           card.name.text() == "2-r.png".removesuffix(".png")
           and not card.name.isHidden(),
           f"{card.name.text()!r}")
        ok("没勾选时「开始拼版」不可点", not dialog.ok_button.isEnabled())
        # 「只有三种可选形态」（用户 2026-09-30）：1 张单独成页 / 2 张拼一页 /
        # 1 张半幅 + 自动拼版
        dialog.cards[0].toggle()
        ok("只勾 1 张：「开始拼版」可点（单张单独成页），提示单独成一页",
           dialog.ok_button.isEnabled() and "单独成一页" in dialog.status.text(),
           dialog.status.text())
        dialog.cards[1].toggle()
        ok("勾满两张：「开始拼版」可点，提示拼成一页",
           dialog.ok_button.isEnabled() and "拼成一页" in dialog.status.text(),
           dialog.status.text())
        ok("点卡片即可勾选（整张卡片都是热区）",
           dialog.cards[0].is_checked() and dialog.cards[1].is_checked())
        ok("勾选结果按**源清单顺序**返回（不是点击顺序）",
           _names(dialog.picked_files()) == ["2-r.png", "2-l.png"],
           str(_names(dialog.picked_files())))
        dialog.cards[0].toggle()
        ok("取消勾选回到 1 张 → 仍可点（单张单独成页）",
           not dialog.cards[0].is_checked() and dialog.ok_button.isEnabled())
        dialog.cards[1].toggle()
        ok("两张都取消 → 「开始拼版」变灰",
           not dialog.cards[1].is_checked() and not dialog.ok_button.isEnabled())
        dialog.cards[0].toggle()
        ok("勾中的卡片进入选中态（浅底 + 对勾）", dialog.cards[0].is_checked())

        # ---- 「从这张图片开始自动拼版」复选框（用户 2026-10-01：恰好勾 1 张
        #      就出现，**不限整幅/半幅**；勾上后「开始拼版」走自动拼版）----
        # （当前状态：只勾 cards[0] 一张半幅）
        ok("只勾 1 张：下方出现「从这张图片开始自动拼版」复选框（默认未勾）",
           dialog.auto_checkbox.isVisibleTo(dialog)
           and not dialog.auto_checkbox.isChecked(),
           f"visible={not dialog.auto_checkbox.isHidden()} "
           f"checked={dialog.auto_checkbox.isChecked()}")
        ok("复选框没勾时「开始拼版」也可点（单张单独成页）",
           dialog.ok_button.isEnabled())
        dialog.auto_checkbox.setChecked(True)
        ok("勾上自动拼版后「开始拼版」可点",
           dialog.ok_button.isEnabled())
        ok("auto_mode_file = 勾选的那张",
           dialog.auto_mode_file() is not None
           and dialog.auto_mode_file().name == "2-r.png",
           str(dialog.auto_mode_file()))
        ok("auto_sequence = 从勾选那张起到候选末尾（源清单顺序）",
           _names(dialog.auto_sequence()) == ["2-r.png", "2-l.png"],
           str(_names(dialog.auto_sequence())))
        dialog.cards[1].toggle()
        ok("勾到 2 张：复选框隐藏并复位（走手动拼一页）",
           not dialog.auto_checkbox.isVisibleTo(dialog)
           and not dialog.auto_checkbox.isChecked()
           and dialog.ok_button.isEnabled())
        dialog.cards[1].toggle()
        ok("回到只勾 1 张：复选框重新出现（未勾），「开始拼版」可点",
           dialog.auto_checkbox.isVisibleTo(dialog)
           and not dialog.auto_checkbox.isChecked()
           and dialog.ok_button.isEnabled())
        dialog.deleteLater()

        # 勾 3 张：可以勾，但「开始拼版」不可点（用户 2026-09-30：最多 2 张）
        third = ImpositionPickerDialog([a, b, c])
        ok("三张候选时全部可勾", third.count() == 3)
        third.cards[0].toggle()
        third.cards[1].toggle()
        third.cards[2].toggle()
        ok("勾 3 张 → 「开始拼版」不可点，提示最多勾 2 张",
           len(third.checked_files()) == 3 and not third.ok_button.isEnabled()
           and "最多勾 2 张" in third.status.text(),
           f"勾中 {_names(third.checked_files())} / {third.status.text()}")
        third.cards[1].toggle()
        ok("回到勾 2 张 → 可点，提示拼成一页",
           third.ok_button.isEnabled() and "拼成一页" in third.status.text(),
           third.status.text())
        third.deleteLater()

        # 1 张整幅：单独成页可点，自动拼版选项同样出现（用户 2026-10-01：
        # 不再限制半幅，整幅起自动 = 整幅单独一页后继续往下配）
        full_only = ImpositionPickerDialog([full])
        full_only.cards[0].toggle()
        ok("只勾 1 张整幅：「开始拼版」可点、自动拼版选项同样出现",
           full_only.ok_button.isEnabled()
           and full_only.auto_checkbox.isVisibleTo(full_only)
           and "整幅" in full_only.status.text(),
           full_only.status.text())
        full_only.auto_checkbox.setChecked(True)
        ok("勾上后整幅也能走自动拼版（auto_mode_file 生效）",
           full_only.auto_mode_file() == full,
           str(full_only.auto_mode_file()))
        full_only.deleteLater()

        # ---- 「删除图片」/「查看删除的图片」（用户 2026-09-30）----
        del_dlg = ImpositionPickerDialog([a, b, c, d])
        ok("「确定」按钮已改为「开始拼版」",
           del_dlg.ok_button.text() == "开始拼版", del_dlg.ok_button.text())
        ok("没勾选时「删除图片」不可点", not del_dlg.delete_button.isEnabled())
        del_dlg.cards[0].toggle()
        del_dlg.cards[1].toggle()
        ok("勾选后「删除图片」可点", del_dlg.delete_button.isEnabled())
        del_dlg.delete_button.click()
        ok("删除后两张移出候选（候选剩 2 张）",
           del_dlg.count() == 2
           and _names(del_dlg.removed_files()) == ["1-r.png", "1-l.png"],
           f"count={del_dlg.count()} removed={_names(del_dlg.removed_files())}")
        ok("「查看删除的图片」入口带数量提示",
           "(2)" in del_dlg.removed_entry_button.text(),
           del_dlg.removed_entry_button.text())
        del_dlg.removed_entry_button.click()
        ok("切到已删除视图：列出两张被删卡片",
           del_dlg.stack.currentIndex() == 1 and len(del_dlg.removed_cards) == 2)
        del_dlg.removed_cards[0].toggle()
        ok("勾选已删除卡片后「恢复选中」可用", del_dlg.restore_button.isEnabled())
        del_dlg.restore_button.click()
        ok("恢复一张：候选 3 张、黑名单剩 1 张",
           del_dlg.count() == 3 and _names(del_dlg.removed_files()) == ["1-l.png"],
           f"count={del_dlg.count()} removed={_names(del_dlg.removed_files())}")
        ok("黑名单与打开时不同（宿主需落盘）", del_dlg.removed_changed())
        del_dlg.restore_all_button.click()
        ok("全部恢复：候选 4 张、黑名单清空、视为未变化",
           del_dlg.count() == 4 and not del_dlg.removed_files()
           and not del_dlg.removed_changed())
        del_dlg.deleteLater()

        # 打开时就带黑名单：已删除的不占候选，可一键恢复
        preset = ImpositionPickerDialog([a, b, c, d], removed_files=[a])
        ok("打开时已删除的图不占候选",
           preset.count() == 3 and _names(preset.removed_files()) == ["1-r.png"],
           f"count={preset.count()}")
        preset.removed_entry_button.click()
        ok("黑名单视图列出打开时已删除的卡片", len(preset.removed_cards) == 1)
        preset.restore_all_button.click()
        ok("一键恢复后回到候选",
           preset.count() == 4 and not preset.removed_files())
        preset.deleteLater()
        # ⚠️ 立刻驱动一轮事件：延迟删除在这里处理完，别拖到详情页的 pump 里
        pump(ctx.app, times=10)

        # ---- 真实产物形态：第三步提交产物是「白底透明」的 1bit 调色板 PNG
        # （2026-09-30 改动）。用户报过「图片没有正常显示」——缩略图必须在这种
        # 真实格式上也正常出图，不能只在合成的不透明测试图上成立。
        import numpy as np

        from utils.transparent_png import save_white_as_transparent

        rgb = np.full((600, 400, 3), 255, dtype=np.uint8)
        rgb[80:520, 120:220] = 20
        transparent = tmp / "transparent-1-r.png"
        save_white_as_transparent(rgb, transparent)
        real = ImpositionPickerDialog([transparent])
        real.resize(DIALOG_W, DIALOG_H)
        real.show()
        pump(ctx.app, times=20)
        card_real = real.cards[0]
        ink = _count_non_white(card_real._pixmap.toImage()) if (
            card_real._pixmap.size() == QSize(THUMB_W, THUMB_H)
        ) else -1
        ok("白底透明 PNG（1bit 调色板 + tRNS）也能正常出缩略图",
           ink > 20, f"缩略图={card_real._pixmap.size()} 非白采样={ink}")
        ok("缩略图与卡片尺寸是固定值（不受源图尺寸影响）",
           card_real.thumb.size() == QSize(THUMB_W, THUMB_H)
           and card_real.size().width() >= 180,
           f"thumb={card_real.thumb.size()} card={card_real.size()}")
        real.deleteLater()


        # ---------------- 6. 详情页接线：取图来源切换 ----------------
        repo = TaskStore(tmp / "data")
        pdf = make_pdf(tmp / "拼版源.pdf", 2)
        tid = repo.create_task(pdf, "imposition-hash", "拼版测试")
        repo.copy_source_to_task(tid, pdf)
        # 拼版节点只认「已知」的区域模式（2026-09-30）：草稿确定 area=1，
        # 否则 _select_stage(拼版) 会因节点不在流程里被退回第一步
        repo.save_draft(tid, "rembg", {"area": 1})
        # 第三步去底色产物（拼版的源图 = 「提交本次任务」的成品图）
        rembg_dir = repo.rembg_output_dir(tid)
        for name, color in (("1-r", RED), ("1-l", GREEN),
                            ("2-r", BLUE), ("2-l", YELLOW)):
            _mk(rembg_dir / f"{name}.png", color)
        # 顺带铺好上游夹具（提取清单 / 去底预览 / 检测框）：它们已不参与第四步
        # 合成（2026-10-01 起只透传提交产物），但保留成"真实任务该有的样子"，
        # 免得测试跑在空目录上。
        extract = repo.extract_output_dir(tid)
        preview = repo.rembg_preview_output_dir(tid)
        boxes = []
        for stem, color in (("1", RED), ("2", BLUE)):
            item = _mk(extract / f"{stem}.png", color)
            _mk(preview / f"{stem}.png", color)
            boxes.append({"file": str(item), "label": stem})
        repo.save_pages(tid, boxes)
        repo.save_detect_boxes(tid, "1", [[20, 40, 390, 560], [410, 40, 780, 560]])
        repo.save_detect_boxes(tid, "2", [[20, 40, 390, 560], [410, 40, 780, 560]])

        page = TaskDetailPage(repo)
        page.resize(1080, 720)
        page.show()
        pump(ctx.app, times=12)
        ok("进入拼版测试任务", page.set_task(tid))
        pump(ctx.app, times=8)

        ok("详情页控制栈/预览栈都多了拼版这一位",
           page.control_stack.count() == 5 and page.preview_stack.count() == 5)
        ok("默认未启用拼版时，第四步取图 = 第三步去底色",
           page.print_source_dir() == rembg_dir
           and not page.imposition_active())

        page._select_stage(IMPOSITION_INDEX)
        pump(ctx.app, times=8)
        ok("切到拼版详情：两栈都在第 %d 位" % IMPOSITION_INDEX,
           page.control_stack.currentIndex() == IMPOSITION_INDEX
           and page.preview_stack.currentIndex() == IMPOSITION_INDEX)
        ok("拼版详情隐藏执行按钮组",
           not page.run_button.isVisible() and not page.submit_button.isVisible()
           and not page.resume_button.isVisible()
           and not page.cancel_button.isVisible())
        ok("详情里的拼版视图就是刚验证的那个控件",
           isinstance(page.imposition_view, ImpositionViewWidget))

        # 未生效时：第四步也只排版第三步「提交本次任务」的成品图（整图透传）。
        # 2026-10-01 起不再拿去底图按 area/border 现算——见 submit.py。
        base_entries, _doc = page._print_entries()
        base_effects = page._build_print_effects(base_entries)
        ok("未生效时也整图透传提交产物（不再按 area/border 现算）",
           len(base_effects) == 4
           and all(e["effect"] is None for e in base_effects)
           and {str(Path(e["file"]).parent) for e in base_effects} == {str(rembg_dir)},
           str(base_effects[:1]))

        pages = None
        import desktop.components.imposition.picker as _ipick

        real_dialog = _ipick.ImpositionPickerDialog

        class _FakeDialog:
            """替身弹窗：直接认下前两张候选（真实弹窗是模态的，测试里不能 exec）。"""

            def __init__(self, files, parent=None, removed_files=None):
                self.files = list(files)
                self.initial_removed = list(removed_files or [])

            def exec(self) -> int:
                return 1

            def picked_files(self):
                return self.files[:2]

            def auto_mode_file(self):
                return None

            def removed_files(self):
                return list(self.initial_removed)

            def removed_changed(self):
                return False

        class _FakeManyDialog(_FakeDialog):
            """替身弹窗：勾选全部候选——「开始拼版」按每两张一页配对。"""

            def picked_files(self):
                return list(self.files)

        class _FakeRemoveDialog(_FakeDialog):
            """替身弹窗：把第一张候选「删除」（移出选择范围），不开始拼版。"""

            def picked_files(self):
                return []

            def removed_files(self):
                return [self.files[0]]

            def removed_changed(self):
                return True

        class _FakeRestoreDialog(_FakeRemoveDialog):
            """替身弹窗：把黑名单全部恢复（removed 变空）。"""

            def removed_files(self):
                return []

        class _FakeOneDialog(_FakeRemoveDialog):
            """替身弹窗：只勾一张——单张单独成页（用户 2026-09-30）。"""

            def picked_files(self):
                return self.files[:1]

            def removed_changed(self):
                return False

        # ---- 「删除图片」黑名单：落盘 + 移出候选（取消也生效）----
        _ipick.ImpositionPickerDialog = _FakeRemoveDialog
        try:
            page._on_imposition_add_requested()
            page._imposition_timer.stop()
            pump(ctx.app, times=4)
            doc = page._imposition_doc()
            ok("弹窗里删除的图片落盘到 removed 字段",
               [Path(f).name for f in doc.get("removed") or []] == ["1-r.png"],
               str(doc.get("removed")))
            ok("被删除的图片不再进入「选择拼版」候选",
               "1-r.png" not in _names(S.remaining_files(
                   page.imposition_source_files(), doc)))
            # 全部恢复：黑名单清空，图片回到候选范围
            _ipick.ImpositionPickerDialog = _FakeRestoreDialog
            page._on_imposition_add_requested()
            page._imposition_timer.stop()
            pump(ctx.app, times=4)
            ok("恢复后黑名单清空（重新进入候选范围）",
               page._imposition_doc().get("removed") == [])
            # 只勾一张 → 单图单独一页（用户 2026-09-30：单张允许拼版）
            _ipick.ImpositionPickerDialog = _FakeOneDialog
            page._on_imposition_add_requested()
            page._imposition_timer.stop()
            pump(ctx.app, times=6)
            one_pages = page._imposition_pages()
            ok("只勾一张 → 单图单独一页（1 项、原图 1-r）",
               len(one_pages) == 1 and len(one_pages[0]["items"]) == 1
               and Path(one_pages[0]["items"][0]["file"]).name == "1-r.png",
               str([[Path(i["file"]).name for i in p["items"]]
                    for p in one_pages]))
            # 清空，接原有「手动两张」流程
            page._save_imposition_pages([])
            page._imposition_timer.stop()
            pump(ctx.app, times=4)
        finally:
            _ipick.ImpositionPickerDialog = real_dialog

        # ---- 多选配对：勾 4 张 →「开始拼版」两两成页（用户 2026-09-30）----
        _ipick.ImpositionPickerDialog = _FakeManyDialog
        try:
            page._on_imposition_add_requested()
            page._imposition_timer.stop()
            pump(ctx.app, times=6)
            pages = page._imposition_pages()
            ok("多选 4 张：开始拼版两两成页（共 2 页）",
               len(pages) == 2 and all(len(p["items"]) == 2 for p in pages)
               and Path(pages[0]["items"][0]["file"]).name == "1-r.png"
               and Path(pages[1]["items"][0]["file"]).name == "2-r.png",
               str([[Path(i["file"]).name for i in p["items"]] for p in pages]))
            ok("多选拼版后左列两页、停在第一页",
               len(page.imposition_view.page_list.entries()) == 2
               and page.imposition_view.current_index() == 0,
               str(page.imposition_view.current_index()))
            # 清空，接原有「手动两张」流程
            page._save_imposition_pages([])
            page._imposition_timer.stop()
            pump(ctx.app, times=4)
        finally:
            _ipick.ImpositionPickerDialog = real_dialog

        # ---- 自动拼版接线：勾 1 张 + 「从这张图片开始自动拼版」→ 规则引擎接管
        # （用户 2026-09-30：1-r 单独一页、左半幅+右半幅配对、落单单页）----
        class _FakeAutoDialog(_FakeDialog):
            """替身弹窗：只勾第一张 + 自动拼版（UI 行为已在真实弹窗测过）。"""

            def picked_files(self):
                return self.files[:1]

            def auto_mode_file(self):
                return self.files[0]

            def auto_sequence(self):
                return list(self.files)

        _ipick.ImpositionPickerDialog = _FakeAutoDialog
        try:
            page._on_imposition_add_requested()
            page._imposition_timer.stop()
            pump(ctx.app, times=6)
            auto_pages = page._imposition_pages()
            ok("自动拼版落盘：首位 1-r 单独一页、(1-l,2-r) 配对、末尾 2-l 单独",
               len(auto_pages) == 3
               and [tuple(Path(i["file"]).name for i in p["items"])
                    for p in auto_pages]
               == [("1-r.png",), ("1-l.png", "2-r.png"), ("2-l.png",)],
               str([[Path(i["file"]).name for i in p["items"]]
                    for p in auto_pages]))
            ok("自动拼版后左列 3 页、停在第一页",
               len(page.imposition_view.page_list.entries()) == 3
               and page.imposition_view.current_index() == 0,
               str(page.imposition_view.current_index()))
            # 清空，接原有「手动两张」流程
            page._save_imposition_pages([])
            page._imposition_timer.stop()
            pump(ctx.app, times=4)
        finally:
            _ipick.ImpositionPickerDialog = real_dialog

        _ipick.ImpositionPickerDialog = _FakeDialog
        try:
            page._on_imposition_add_requested()
            page._imposition_timer.stop()
            pump(ctx.app, times=6)
            pages = page._imposition_pages()
            ok("「选择拼版」→ 追加一页并要求两张",
               len(pages) == 1 and len(pages[0]["items"]) == 2, str(pages))
            ok("落盘后左列同步成 1 页并停在该页",
               len(page.imposition_view.page_list.entries()) == 1
               and page.imposition_view.current_index() == 0,
               str(page.imposition_view.current_index()))
            ok("加页后自动启用（否则第四步根本用不到它）",
               page._load_imposition_enabled())
            ok("跳过已用过的图：第二页拿到的是剩下那两张",
               [Path(i["file"]).name for i in pages[0]["items"]]
               == ["1-r.png", "1-l.png"],
               str([Path(i["file"]).name for i in pages[0]["items"]]))
            page._on_imposition_add_requested()
            page._imposition_timer.stop()
            pump(ctx.app, times=6)
            pages = page._imposition_pages()
            ok("再加一页 → 共两页，左列两条 + 虚线格",
               len(pages) == 2 and len(page.imposition_view.page_list.entries()) == 2)
            # 四张都用完了：再点只能提示，不许造出半页
            page._on_imposition_add_requested()
            page._imposition_timer.stop()
            ok("没有剩余图片时不会造出残页",
               len(page._imposition_pages()) == 2)
        finally:
            _ipick.ImpositionPickerDialog = real_dialog

        # ---- 左列缩略图（用户 2026-10-04）----
        # 「任务流程里拼板缩略图没显示、只看到占位」：这条链此前**从没喂过
        # 缩略图**（占位符是硬编码的初始值，没有任何代码会替换它）。现在每页
        # 取第一张源图，后台渲进**任务目录**（tasks/<id>/thumbnails/
        # imposition/）后贴到条目上——⚠️ 与独立拼图页共用组件与 worker 但
        # **不共用缓存根**（用户 2026-10-04 明确「singletask 和 taskdetail
        # 不是一回事」）。
        import time as _time

        _reps = page._imposition_page_reps(page._imposition_pages())
        for _ in range(100):  # 后台线程回填：轮询到全部到位或超时（约 5s）
            _got = getattr(page, "_imposition_source_thumbs", {}) or {}
            if all(r in _got for r in _reps if r):
                break
            ctx.app.processEvents()
            _time.sleep(0.05)
        _thumbs = page._imposition_source_thumbs
        ok("左列缩略图：每页代表图（第一张源图）都渲出",
           bool(_reps) and all(r in _thumbs for r in _reps if r),
           f"reps={[Path(r).name for r in _reps]} got={sorted(_thumbs)}")
        _entries = page.imposition_view.page_list.entries()
        ok("左列缩略图：贴到条目上（pixmap 非空，不再是占位）",
           len(_entries) == 2
           and all(not e.thumb.pixmap().isNull() for e in _entries),
           str([e.thumb.pixmap().isNull() for e in _entries]))
        ok("左列版面：缩略图在上、文字在下（勾选框贴左上角）",
           all(e.checkbox.y() < e.thumb.y() < e.title_label.y() for e in _entries)
           and all(e.checkbox.x() < e.width() // 2 for e in _entries))
        # 缓存归属边界（用户 2026-10-04 强调）：写任务目录，不借道独立区
        _cache_dir = page.store.imposition_thumbnails_dir(page.task_id)
        _cached = list(_cache_dir.glob("*.jpg"))
        ok("左列缩略图缓存写在任务目录 thumbnails/imposition/",
           _cache_dir.exists() and len(_cached) >= 2,
           f"{_cache_dir} jpg={len(_cached)}")

        # ---- 批量删除（回归钉子）----
        # 曾出错：确认后的日志行引用未定义的 `listing` ⇒ 页虽然删了，但方法
        # 在日志处抛 NameError，用户什么提示都看不到（旧用例只验了信号发射，
        # 没跑过真正的处理器——这里用替身确认弹窗把处理器跑通）。
        _pages_backup = [dict(p) for p in page._imposition_pages()]
        for _e in page.imposition_view.page_list.entries():
            _e.set_checked(True)
        import desktop.components.imposition.confirm_delete as _icdel

        class _FakeConfirmDialog:
            def __init__(self, items, parent=None):
                self.items = list(items)

            def exec(self):
                return 1

        _real_confirm = _icdel.BatchDeleteConfirmDialog
        _icdel.BatchDeleteConfirmDialog = _FakeConfirmDialog
        _log_at = len(page.log_view.toPlainText())
        try:
            page._on_imposition_batch_delete()
            page._imposition_timer.stop()
            pump(ctx.app, times=6)
        finally:
            _icdel.BatchDeleteConfirmDialog = _real_confirm
        ok("批量删除：确认后真删了页、清单一空",
           len(page._imposition_pages()) == 0
           and len(page.imposition_view.page_list.entries()) == 0)
        _tail = page.log_view.toPlainText()[_log_at:]
        ok("批量删除：日志列出被删页码（回归：曾引用未定义变量直接崩）",
           "已批量删除 2 页拼版（第 1、2 页）" in _tail, _tail[-160:])
        # 恢复两页：后面的取图来源/旧数据断言都建立在"拼版已生效"之上
        page._save_imposition_pages(_pages_backup)
        page._imposition_timer.stop()
        pump(ctx.app, times=6)
        ok("批量删除回归用例收尾：页清单已恢复（2 页）",
           len(page._imposition_pages()) == 2
           and len(page.imposition_view.page_list.entries()) == 2)

        ok("拼版生效", page.imposition_active())
        ok("第四步取图目录切到 stages/imposition",
           page.print_source_dir() == repo.imposition_output_dir(tid),
           str(page.print_source_dir()))

        # 同步合成一次（点「生成 PDF」前走的就是这条），产物可查
        page._compose_imposition_now()
        produced = sorted(repo.imposition_output_dir(tid).glob("*.png"))
        ok("拼版产物落盘为 0001/0002",
           _names(produced) == ["0001.png", "0002.png"], str(_names(produced)))
        entries, _doc = page._print_entries()
        ok("待打印列表改从拼版产物取",
           {str(Path(e["file"]).parent) for e in entries}
           == {str(repo.imposition_output_dir(tid))},
           str(_names([e["file"] for e in entries])))
        effects = page._build_print_effects(entries)
        ok("拼版生效时整页透传（拼版页本身就是成品）",
           len(effects) == 2 and all(e["effect"] is None for e in effects),
           str(effects))

        # 取消启用 → 回到去底色（用户口径：「否则从第三步去底色获取」）
        page._set_imposition_checked(False)
        page._imposition_timer.stop()
        pump(ctx.app, times=6)
        ok("取消启用后取图回到第三步去底色",
           page.print_source_dir() == rembg_dir and not page.imposition_active())
        entries, _doc = page._print_entries()
        ok("取消启用后待打印列表回到去底色产物",
           {str(Path(e["file"]).parent) for e in entries} == {str(rembg_dir)},
           str(_names([e["file"] for e in entries])))

        # ------ 6b. 列表胶囊 + 「旧数据不显示」（用户 2026-10-03）------
        # 口径一："任务列表子任务到底有几个需要根据详情决定，特别是拼板这个
        #        节点可能存在，需要看详情里面是否启用，如果启用就添加这个节点"
        # 口径二："如果之前流程里面没有启用拼板，但是生成了pdf，此时再次启用
        #        拼板，则生成PDF的数据要来源于拼板，旧的数据不显示"
        from desktop.services.stale_chain import print_source_switched
        from desktop.store import IMPOSITION_STAGE, STAGE_SHORT
        from desktop.workers.task_rows_worker import TaskRowsWorker

        def _chips_of(task_id: str) -> list[dict]:
            """列表行 worker 真实产出（不碰表格控件，纯数据层）。"""
            worker = TaskRowsWorker(repo)
            got: list = []
            worker.completed.connect(got.append)
            worker.failed.connect(lambda m: got.append(m))
            worker.run()
            rows = got[0]
            return rows[0]["stages"] if isinstance(rows, list) else []

        page._set_imposition_checked(False)
        page._imposition_timer.stop()
        pump(ctx.app, times=6)
        ok("未启用拼版：列表只有四个子任务",
           len(_chips_of(tid)) == 4, str([c["short"] for c in _chips_of(tid)]))
        page._set_imposition_checked(True)
        page._imposition_timer.stop()
        pump(ctx.app, times=6)
        chips = _chips_of(tid)
        shorts = [c["short"] for c in chips]
        ok("启用拼版：列表多一个子任务（共五个）",
           len(chips) == 5, str(shorts))
        ok("拼版胶囊排在 PDF 之前（与流程条节点同位）",
           STAGE_SHORT[IMPOSITION_STAGE] in shorts
           and shorts.index(STAGE_SHORT[IMPOSITION_STAGE])
           == shorts.index(STAGE_SHORT["print"]) - 1,
           str(shorts))
        ok("拼版胶囊文案取自 spec 的 short_name（不另写一份中文）",
           STAGE_SHORT[IMPOSITION_STAGE] == "拼版",
           STAGE_SHORT[IMPOSITION_STAGE])
        # 状态：勾了但没拼页 = 未生效（灰）；勾了且拼了页 = 生效（绿）
        # ⚠️ 这里临时清空 pages，测完**原样恢复**第 6 节拼好的两页——后面
        # 取图来源/旧数据的断言都建立在"拼版已生效"之上。
        doc_backup = repo.load_imposition_doc(tid)
        repo.save_imposition_doc(tid, {"enabled": True, "pages": []})
        pending_chip = next(
            c for c in _chips_of(tid) if c["short"] == STAGE_SHORT[IMPOSITION_STAGE]
        )
        ok("启用但还没拼页 → 拼版胶囊为未执行（灰）",
           pending_chip["status"] == "pending", str(pending_chip))
        repo.save_imposition_doc(tid, doc_backup)
        live_chip = next(
            c for c in _chips_of(tid) if c["short"] == STAGE_SHORT[IMPOSITION_STAGE]
        )
        ok("启用且拼了页 → 拼版胶囊为成功（绿）",
           live_chip["status"] == "success", str(live_chip))

        # 「旧数据」：伪造一份**去底色来源**下生成过的 PDF + 对应运行记录
        print_dir = repo.stage_dir(tid, "print")
        print_dir.mkdir(parents=True, exist_ok=True)
        (print_dir / "print.pdf").write_bytes(b"%PDF-1.4 old")
        old_run = repo.create_stage_run(tid, "print", {
            "pdf_name": "print.pdf", "source_stage": "rembg_submit",
        })
        repo.finish_stage(tid, old_run, "success", str(print_dir))
        page._set_imposition_checked(False)
        page._imposition_timer.stop()
        pump(ctx.app, times=6)
        page._refresh_stale_notices()
        ok("来源没变时那份 PDF 仍然可用（不误伤）",
           not page._print_source_switched()
           and page._current_print_pdf_path() is not None)
        ok("从未成功生成过 → 不判过期",
           not print_source_switched({}, "imposition"))
        ok("老记录没有 source_stage → 不误判过期",
           not print_source_switched(
               {"print": [{"status": "success", "finished_at": 1.0,
                           "parameters": {"pdf_name": "print.pdf"}}]},
               "imposition",
           ))

        # 现在启用拼版：那份 PDF 成了旧数据
        page._set_imposition_checked(True)
        page._imposition_timer.stop()
        pump(ctx.app, times=6)
        page._select_stage(3)
        pump(ctx.app, times=6)
        ok("启用拼版后取图来源切到 imposition",
           page.print_source_stage() == "imposition",
           page.print_source_stage())
        ok("换来源后旧 PDF 判为过期（缓存跟着开关走）",
           page._print_source_stale)
        ok("旧数据不显示：当前可用 PDF 为空",
           page._current_print_pdf_path() is None,
           str(page._current_print_pdf_path()))
        ok("「下载 PDF」按钮随之禁用",
           not page.print_preview.download_button.isEnabled())
        ok("预览控件的 PDF 绑定被清空",
           page.print_preview._pdf_path is None,
           str(page.print_preview._pdf_path))
        notice = page._regenerate_notice("print")
        ok("状态行提示取图来源已改（要点名拼版）",
           bool(notice) and "取图来源已改为" in notice
           and "拼版" in notice, str(notice))
        # 磁盘上那份文件**不删**（用户自己的产物），只是不再提供/不再算结果
        ok("旧 PDF 文件仍在磁盘上（只是不显示，不删用户产物）",
           (print_dir / "print.pdf").exists())
        toasts: list = []
        real_toast = page._toast
        page._toast = lambda *a, **k: toasts.append(a)
        try:
            page._download_print_pdf()
        finally:
            page._toast = real_toast
        ok("旧数据下载被拦下并说明原因",
           any("重新生成" in str(t) for t in toasts), str(toasts))
        # 反向也对称：取消启用 → 又变回去底色，但历史是去底色 → 不判旧
        page._select_stage(IMPOSITION_INDEX)
        pump(ctx.app, times=4)
        page._set_imposition_checked(False)
        page._imposition_timer.stop()
        pump(ctx.app, times=6)
        ok("反向切换对称：回到原来源后不再判旧、PDF 恢复可用",
           not page._print_source_switched()
           and page._current_print_pdf_path() is not None)

        # ---- 6c. 「勾了就算启用」：不要求已经有拼版页（用户 2026-10-03 报障）----
        # 早先 ``imposition_active()`` 额外要求"至少拼了一页"，于是用户勾了
        # 「在流程中启用图片拼版」却还没拼页时——第四步仍取去底色图、流程条仍是
        # 灰虚线 + 绕行线，报"启用不生效 / 流程线没更新"。现在把**启用**
        # （用户意图）与**有没有页**（当前进度）彻底分层。
        page._save_imposition_pages([])
        # ⚠️ **别停合成定时器**：清空拼版页必须真的跑一轮合成（``compose_doc``
        # 见 pages=[] 会 ``_sweep_stale(dest, 0)`` 把 stages/imposition 收干净）。
        # 残留的 0001.png 会让第四步把上一轮的图当成本轮结果——这正是
        # "启用后不按拼板来"的另一种形态，必须由真实路径清掉。
        page._compose_imposition_async()
        for _ in range(60):
            pump(ctx.app, times=2)
            if not page._imposition_composing and not page._imposition_dirty:
                break
        pump(ctx.app, times=6)
        stale_pngs = sorted(repo.imposition_output_dir(tid).glob("*.png"))
        ok("清空拼版页后：产物目录被一并收干净（不拿上一轮的图当结果）",
           stale_pngs == [], str([p.name for p in stale_pngs]))
        page._set_imposition_checked(False)
        page._imposition_timer.stop()
        pump(ctx.app, times=6)
        ok("（前置）未启用：取图 = 去底色",
           page.print_source_dir() == rembg_dir and not page.imposition_active())
        page._set_imposition_checked(True)
        page._imposition_timer.stop()
        pump(ctx.app, times=6)
        ok("勾了启用（还没拼页）→ 判定为已启用", page.imposition_active())
        ok("勾了启用（还没拼页）→ 流程条点亮为生效态（徽标转对勾）",
           page.step_bar.imposition_node.badge._status == "success",
           f"badge={page.step_bar.imposition_node.badge._status}")
        ok("勾了启用（还没拼页）→ 第四步取图已切到 stages/imposition",
           page.print_source_dir() == repo.imposition_output_dir(tid),
           str(page.print_source_dir()))
        ok("启用与有无产物分两层：已启用但还没有页",
           page.imposition_active() and not page.imposition_has_pages())
        ok("启用但没拼页时列表为空（而不是悄悄回退去底色）",
           page._print_entries()[0] == [],
           str([e["file"] for e in page._print_entries()[0]]))
        ok("启用但没拼页时状态行说清「没有拼版页」而不是「未生效」",
           "拼版已启用" in page.imposition_panel_status.text()
           and "没有拼版页" in page.imposition_panel_status.text(),
           page.imposition_panel_status.text())
        # 点「生成 PDF」必须给**拼版专属**提示，不能把人引去第三步
        toasts2: list = []
        real_toast2 = page._toast
        page._toast = lambda *a, **k: toasts2.append(a)
        try:
            page._select_stage(3)
            pump(ctx.app, times=4)
            page._run_stage_unchecked(False)
        finally:
            page._toast = real_toast2
        ok("启用但没拼页时生成 PDF → 提示去拼版（不是回第三步）",
           any("拼版" in str(t) and "选择拼版" in str(t) for t in toasts2),
           str(toasts2))
        # 拼一页 → "有产物"成立（同一判据下只是进度变了）
        page._select_stage(IMPOSITION_INDEX)
        pump(ctx.app, times=4)
        page._save_imposition_pages([{
            "items": [
                {"file": str(a), "rect": [0, 0, 200, 600], "rotation": 0.0},
                {"file": str(b), "rect": [200, 0, 200, 600], "rotation": 0.0},
            ],
        }])
        page._imposition_timer.stop()
        page._compose_imposition_now()
        pump(ctx.app, times=4)
        ok("拼上一页后：有产物成立、来源仍是拼版",
           page.imposition_has_pages()
           and page.print_source_dir() == repo.imposition_output_dir(tid))
        # ⚠️ 恢复**两页**基线：6c 只拼了一页，而第 7 节的「上一页/下一页」用例
        # 需要能翻到第二页。别让这段的临时状态漏给后面。
        page._save_imposition_pages([
            {"items": [
                {"file": str(a), "rect": [0, 0, 200, 600], "rotation": 0.0},
                {"file": str(b), "rect": [200, 0, 200, 600], "rotation": 0.0},
            ]},
            {"items": [
                {"file": str(c), "rect": [0, 0, 200, 600], "rotation": 0.0},
                {"file": str(d), "rect": [200, 0, 200, 600], "rotation": 0.0},
            ]},
        ])
        page._imposition_timer.stop()
        page._compose_imposition_now()
        page.imposition_view.set_current(0)
        pump(ctx.app, times=4)
        ok("（恢复）两页拼版就位，供第 7 节继续",
           len(page._imposition_pages()) == 2 and page.imposition_active(),
           f"pages={len(page._imposition_pages())} "
           f"active={page.imposition_active()}")

        # ---------------- 7. 面板动作：复位 / 删除 ----------------
        # （页序在左列拖动排序，翻页在画布下方「上一页/下一页」——面板上
        #   不再有「左转/右转 90°」与「上移/下移」，用户 2026-09-30 口径）
        page._set_imposition_checked(True)
        page._imposition_timer.stop()
        page.imposition_view.set_current(0)
        page.imposition_view.canvas.select(0)
        page.imposition_view.canvas.rotate_selected(90.0)
        page._imposition_timer.stop()
        ok("画布旋转选中图作用到版面",
           abs(page.imposition_view.current_items()[0]["rotation"] - 90.0) < 0.01,
           str(page.imposition_view.current_items()[0]["rotation"]))

        page._on_imposition_reset_layout()
        page._imposition_timer.stop()
        reset_items = page._imposition_pages()[0]["items"]
        ok("「复位本页版面」把两张图恢复成默认并排（尺寸回原始、旋转归零）",
           [item["rotation"] for item in reset_items] == [0.0, 0.0]
           and reset_items[1]["rect"][:2] == [0.0, 0.0]
           and reset_items[0]["rect"][0] == reset_items[1]["rect"][2],
           str(reset_items))
        ok("复位后画布也同步了", page.imposition_view.current_items()
           == reset_items)

        # ---- 「上一页/下一页」：翻页在中间编辑区底部右侧（用户 2026-09-30）----
        nav_seen: list[int] = []
        page.imposition_view.page_selected.connect(nav_seen.append)
        ok("第一页：「上一页」禁用、「下一页」可用",
           not page.imposition_view.prev_button.isEnabled()
           and page.imposition_view.next_button.isEnabled())
        page.imposition_view.next_button.click()
        page._imposition_timer.stop()
        ok("「下一页」切到第二页（与左列点选同一条路径）",
           page.imposition_view.current_index() == 1 and nav_seen == [1],
           f"current={page.imposition_view.current_index()} nav={nav_seen}")
        ok("末页：「下一页」禁用、「上一页」可用",
           not page.imposition_view.next_button.isEnabled()
           and page.imposition_view.prev_button.isEnabled())
        page.imposition_view.prev_button.click()
        page._imposition_timer.stop()
        ok("「上一页」切回第一页",
           page.imposition_view.current_index() == 0 and nav_seen == [1, 0],
           f"current={page.imposition_view.current_index()} nav={nav_seen}")
        page.imposition_view.page_selected.disconnect(nav_seen.append)

        # ---------------- 7b. 拖动排序与「✕」释放图片 ----------------
        page._on_imposition_page_reorder(1, 0)
        page._imposition_timer.stop()
        pump(ctx.app, times=4)
        reordered = page._imposition_pages()
        ok("拖动排序：原第二页变第一页（顺序即 PDF 页序）",
           len(reordered) == 2
           and Path(reordered[0]["items"][0]["file"]).name == "2-r.png"
           and Path(reordered[1]["items"][0]["file"]).name == "1-r.png",
           str([Path(i["items"][0]["file"]).name for i in reordered]))
        ok("左列页码标签随新顺序重建（第几页同步）",
           [e.title_label.text()
            for e in page.imposition_view.page_list.entries()]
           == ["第一页", "第二页"])
        ok("画布落到拖动后的那一页",
           page.imposition_view.current_index() == 0,
           str(page.imposition_view.current_index()))
        page._on_imposition_page_reorder(1, 0)  # 拖回去，恢复原顺序
        page._imposition_timer.stop()

        before_release = page._imposition_pages()
        page._on_imposition_release_page(0)
        page._imposition_timer.stop()
        pump(ctx.app, times=4)
        remaining = _names(S.remaining_files(
            page.imposition_source_files(), page._imposition_doc()))
        ok("「✕」删掉该页，另一页保留",
           len(page._imposition_pages()) == 1
           and Path(page._imposition_pages()[0]["items"][0]["file"]).name
           == "2-r.png")
        ok("被释放的两张回到未选择列表",
           "1-r.png" in remaining and "1-l.png" in remaining, str(remaining))
        page._save_imposition_pages(before_release)
        page._imposition_timer.stop()
        page.imposition_view.set_current(0)
        pump(ctx.app, times=4)

        # ---------------- 7b-2. 「删除选中图片」+ 单图页「新增图片」 --------
        # （2026-09-30 用户定：右侧不再有「删除本页拼版」——删页入口只剩左列
        # 「✕」/批量删除/清空；选中哪张图就能删哪张；单图页给「新增图片」）
        page._save_imposition_pages(before_release)
        page._imposition_timer.stop()
        page.imposition_view.set_current(0)
        pump(ctx.app, times=4)
        page.imposition_view.canvas.select(1)  # 选中左槽「1-l」
        page._on_imposition_delete_item()
        page._imposition_timer.stop()
        pump(ctx.app, times=4)
        kept = page._imposition_pages()
        ok("「删除选中图片」：页保留、只删被选中的那一张",
           len(kept) == 2 and len(kept[0]["items"]) == 1
           and Path(kept[0]["items"][0]["file"]).name == "1-r.png",
           str([[Path(i["file"]).name for i in p["items"]] for p in kept]))
        ok("删完后面板出现「新增图片」（单图页），画布选中清空",
           not page.imposition_panel.add_image_button.isHidden()
           and page.imposition_view.selected_slot() < 0
           and page.imposition_view.current_index() == 0)
        # 删掉单图页的最后一张图：页整个消失（空页没有意义）——另一页保留，
        # 仍是生效态；把剩余页也删光才回退去底色。
        # （2026-09-30 用户定：删最后一张=整页移除，要弹确认框——真实弹窗是
        # 模态的，测试里不能 exec，用替身同 picker 套路，可编排确认/取消）
        import qfluentwidgets as _qw

        _real_dialog = _qw.Dialog

        class _FakeConfirm:
            result = 1  # 1=确认，0=取消
            asked = []

            def __init__(self, title, content, parent=None):
                _FakeConfirm.asked.append((title, content))

                class _Btn:
                    def setText(self, text):
                        pass

                self.yesButton = _Btn()
                self.cancelButton = _Btn()

            def exec(self):
                return _FakeConfirm.result

        _qw.Dialog = _FakeConfirm

        page.imposition_view.canvas.select(0)
        _FakeConfirm.result = 0  # 先试「取消」
        page._on_imposition_delete_item()
        page._imposition_timer.stop()
        pump(ctx.app, times=4)
        ok("删最后一张弹确认框、点「取消」：页保留不动",
           len(page._imposition_pages()) == 2
           and [Path(i["file"]).name
                for i in page._imposition_pages()[0]["items"]] == ["1-r.png"]
           and _FakeConfirm.asked[-1][0] == "删除图片"
           and "整页拼版" in _FakeConfirm.asked[-1][1],
           f"pages={[[Path(i['file']).name for i in p['items']] for p in page._imposition_pages()]} "
           f"asked={_FakeConfirm.asked}")

        page.imposition_view.canvas.select(0)
        _FakeConfirm.result = 1  # 「删除」
        page._on_imposition_delete_item()
        page._imposition_timer.stop()
        pump(ctx.app, times=4)
        ok("删掉单图页最后一张：页一并删除，另一页保留（仍是生效态）",
           len(page._imposition_pages()) == 1
           and [Path(i["file"]).name
                for i in page._imposition_pages()[0]["items"]]
           == ["2-r.png", "2-l.png"]
           and page.imposition_view.current_index() == 0
           and page.imposition_active()
           and page.print_source_dir() != rembg_dir,
           f"pages={[[Path(i['file']).name for i in p['items']] for p in page._imposition_pages()]} "
           f"cur={page.imposition_view.current_index()} "
           f"active={page.imposition_active()}")
        # 把最后一页的两张也删光：全部页清空。
        # ⚠️ 口径（用户 2026-10-03）：**删光只是"没有可拼的图"，不等于"未启用"**
        # ——拼版仍启用，所以取图来源仍指向 stages/imposition（此时是空目录），
        # 第四步会提示先去拼版。早先这里断言"回退去底色"，那是"启用还要额外
        # 满足有拼页"的旧口径，正是用户报的"启用不生效"的根源。
        page.imposition_view.canvas.select(0)
        page._on_imposition_delete_item()
        page._imposition_timer.stop()
        pump(ctx.app, times=4)
        page.imposition_view.canvas.select(0)
        page._on_imposition_delete_item()
        page._imposition_timer.stop()
        pump(ctx.app, times=4)
        ok("删光全部图片：页清空，但仍保持启用（取图来源不退回去底色）",
           page._imposition_pages() == []
           and page.imposition_view.current_index() == -1
           and not page.imposition_has_pages()
           and page.imposition_active()
           and page.print_source_dir() == repo.imposition_output_dir(tid),
           f"pages={page._imposition_pages()} "
           f"cur={page.imposition_view.current_index()} "
           f"active={page.imposition_active()} "
           f"has_pages={page.imposition_has_pages()} "
           f"src={page.print_source_dir()} vs {rembg_dir}")
        _qw.Dialog = _real_dialog  # 恢复真实弹窗

        # 单图页「新增图片」：append 弹窗替身返回 1 张右半幅「2-r」
        # ——原图是左半幅「1-l」→ 新图进右槽、贴在原图右边（原图版面不动）
        single_left = S.single_items(str(b))  # 1-l（左半幅，GREEN）
        page._save_imposition_pages([{"items": single_left}])
        page._imposition_timer.stop()
        page.imposition_view.set_current(0)
        pump(ctx.app, times=4)
        ok("单图页进入后面板露出「新增图片」",
           not page.imposition_panel.add_image_button.isHidden())
        import desktop.components.imposition.picker as _picker_mod

        _real_picker = _picker_mod.ImpositionPickerDialog

        class _FakeAppend:
            """替身弹窗：固定返回一张图（append 模式只放行 1 张）。"""

            def __init__(self, picked):
                self._picked = picked
                import sys
                print("PROBE fake picker constructed", file=sys.stderr)

            def exec(self):
                return 1

            def picked_files(self):
                return self._picked

            def removed_files(self):
                return []

            def removed_changed(self):
                return False

        # ⚠️ 赋给弹窗槽位的必须是**可调用对象**（工厂），不能是替身实例——
        # 控制器拿到的是 `ImpositionPickerDialog(...)` 调用形式。
        _picker_mod.ImpositionPickerDialog = (
            lambda *a, **k: _FakeAppend([str(c)]))  # 2-r
        try:
            page.imposition_panel.add_image_button.click()
            page._imposition_timer.stop()
            pump(ctx.app, times=4)
            merged = page._imposition_pages()
            ok("左半幅原图 + 新增右半幅：新图进右槽、贴原图右边",
               len(merged) == 1 and len(merged[0]["items"]) == 2
               and Path(merged[0]["items"][0]["file"]).name == "2-r.png"
               and Path(merged[0]["items"][1]["file"]).name == "1-l.png"
               and merged[0]["items"][0]["rect"][0]
               == merged[0]["items"][1]["rect"][0] + 400.0
               and merged[0]["items"][1]["rect"] == single_left[0]["rect"],
               str([[Path(i["file"]).name for i in p["items"]]
                    for p in merged]))
        finally:
            _picker_mod.ImpositionPickerDialog = _real_picker

        # 原图是右半幅「1-r」：新增「2-l」进左槽、贴原图左边
        page._save_imposition_pages([{"items": S.single_items(str(a))}])
        page._imposition_timer.stop()
        page.imposition_view.set_current(0)
        pump(ctx.app, times=4)
        _picker_mod.ImpositionPickerDialog = (
            lambda *a, **k: _FakeAppend([str(d)]))  # 2-l
        try:
            page.imposition_panel.add_image_button.click()
            page._imposition_timer.stop()
            pump(ctx.app, times=4)
            merged = page._imposition_pages()
            ok("右半幅原图 + 新增左半幅：新图进左槽、贴原图左边",
               len(merged) == 1 and len(merged[0]["items"]) == 2
               and Path(merged[0]["items"][0]["file"]).name == "1-r.png"
               and Path(merged[0]["items"][1]["file"]).name == "2-l.png"
               and merged[0]["items"][1]["rect"][0] == -400.0,
               str([i["rect"] for i in merged[0]["items"]]))
        finally:
            _picker_mod.ImpositionPickerDialog = _real_picker
        page._save_imposition_pages(before_release)
        page._imposition_timer.stop()
        page.imposition_view.set_current(0)
        pump(ctx.app, times=4)

        # ---------------- 7c. 整版/单图旋转组件 + 红色对齐线（用户 2026-09-30）----
        # 「拼版整体可以旋转，不是 90 度，而是有旋转组件」「单独一个文本框图片
        # 也可以旋转」「无论何时，两张图片组成的中心点都有一个垂直的红色虚线」
        import math

        from desktop.components.imposition.panel import ImpositionPanel
        from desktop.ui.widgets import HelpButton

        def _centers(items):
            return [(it["rect"][0] + it["rect"][2] / 2.0,
                     it["rect"][1] + it["rect"][3] / 2.0) for it in items]

        # ---- 整版旋转的几何：绕公共中心公转 + 自转，公共中心不动 ----
        canvas2 = ImpositionCanvas()
        canvas2.resize(600, 600)
        canvas2.set_page(S.default_items([str(a), str(b)]))
        canvas2.select(0)
        centers_before = _centers(canvas2._items)
        mid_before = canvas2._spread_center_units()
        canvas2.rotate_whole(30.0)
        centers_after = _centers(canvas2._items)
        mid_after = canvas2._spread_center_units()
        ok("整版旋转：两图中心间距不变（相对位置不动）",
           abs(math.dist(centers_after[0], centers_after[1])
               - math.dist(centers_before[0], centers_before[1])) < 1e-6)
        ok("整版旋转：公共中心（红色对齐线落点）不动",
           all(abs(a - b) < 1e-9 for a, b in zip(mid_before, mid_after)))
        ok("整版旋转：两图 rotation 都叠加增量（自转）",
           all(abs(it["rotation"] - 30.0) < 0.01 for it in canvas2.items()),
           str([it["rotation"] for it in canvas2.items()]))
        ok("spread_rotation = 两图平均角",
           abs(canvas2.spread_rotation() - 30.0) < 0.01,
           str(canvas2.spread_rotation()))

        # ---- 单图绝对角度：只改选中的那张 ----
        canvas2.set_item_rotation(45.0)
        ok("set_item_rotation 只改选中图的绝对角度",
           abs(canvas2.items()[0]["rotation"] - 45.0) < 0.01
           and abs(canvas2.items()[1]["rotation"] - 30.0) < 0.01,
           str([it["rotation"] for it in canvas2.items()]))
        ok("selected_rotation 读到选中角",
           abs(canvas2.selected_rotation() - 45.0) < 0.01)
        canvas2.deleteLater()

        # ---- 红色对齐线恒显（对比：框线未按住时不画，对齐线必须一直在）----
        spine_cv = ImpositionCanvas()
        spine_cv.resize(600, 600)
        # ⚠️ 判据用 BLUE/YELLOW 图：测试用的 RED (220,40,40) 与对齐线
        # (224,32,32) 太接近，会污染像素计数
        spine_cv.set_page([
            {"file": str(c), "rect": [400.0, 0.0, 400.0, 600.0], "rotation": 0.0},
            {"file": str(d), "rect": [0.0, 0.0, 400.0, 600.0], "rotation": 0.0},
        ])

        def _red_hits(image, x_px, band=8):
            """数 ``x_px ± band`` 这一竖条里的对齐线红像素（窄带扫描，快）。"""
            total = 0
            for x in range(max(0, x_px - band),
                           min(image.width(), x_px + band + 1)):
                for y in range(0, image.height()):
                    color = image.pixelColor(x, y)
                    if (abs(color.red() - SPINE_RGB[0]) <= 40
                            and abs(color.green() - SPINE_RGB[1]) <= 40
                            and abs(color.blue() - SPINE_RGB[2]) <= 40):
                        total += 1
            return total

        spine_img = spine_cv.grab().toImage()
        x_units, _ = spine_cv._spread_center_units()
        x_px = int(round(spine_cv._off_x + x_units * spine_cv._px_per_unit))
        ok("红色对齐线**恒显**（未按住鼠标也在画）",
           _red_hits(spine_img, x_px) > 20,
           f"命中 {_red_hits(spine_img, x_px)} 像素")
        ok("对齐线只画在两图中心中点那条竖线上（别处没有）",
           _red_hits(spine_img, x_px + 150, band=4) == 0,
           f"远处命中 {_red_hits(spine_img, x_px + 150, band=4)}")

        # ---- 单图页红线判据（用户 2026-09-30 晚：单独一张半页图片在某页，
        # 不显示中间红线）----实际任务里**无 -l/-r 后缀的竖图也可能是半页**
        # （整幅误检 / 封面插页，任务 0020 的 3.png 实测 1070×1536），文件名
        # 认不出来——判据是源图宽高比：竖图（高≥宽）不画、横图（宽>高）才画。
        single_portrait = _mk(tmp / "single-half.png", BLUE)  # 400×600 竖图
        spine_cv.set_page([
            {"file": str(single_portrait),
             "rect": [0.0, 0.0, 400.0, 600.0], "rotation": 0.0},
        ])
        portrait_img = spine_cv.grab().toImage()
        ok("单图页是**竖图**（半页/单页，含无后缀的）：整幅画面没有红线",
           _count_near(portrait_img, SPINE_RGB) == 0,
           f"命中 {_count_near(portrait_img, SPINE_RGB)} 像素")
        single_land = _mk(tmp / "single-spread.png", BLUE, size=(600, 400))
        spine_cv.set_page([
            {"file": str(single_land),
             "rect": [0.0, 0.0, 600.0, 400.0], "rotation": 0.0},
        ])
        land_img = spine_cv.grab().toImage()
        ok("单图页是**横图**（整幅对开）：红色对齐线仍要画（旋转基准）",
           _count_near(land_img, SPINE_RGB) > 20,
           f"命中 {_count_near(land_img, SPINE_RGB)} 像素")

        # ---- 成品截图范围框：两图外接框并集的灰虚线（用户 2026-09-30）----
        def _crop_hits_x(image, x_px, band=6, y_from=None, y_to=None):
            """数 ``x_px ± band`` 竖条里的截图框灰像素；y 范围可裁（避开横边）。"""
            total = 0
            for x in range(max(0, x_px - band),
                           min(image.width(), x_px + band + 1)):
                for y in range(y_from if y_from is not None else 0,
                               y_to if y_to is not None else image.height()):
                    color = image.pixelColor(x, y)
                    if (abs(color.red() - CROP_RGB[0]) <= 40
                            and abs(color.green() - CROP_RGB[1]) <= 40
                            and abs(color.blue() - CROP_RGB[2]) <= 40):
                        total += 1
            return total

        def _bbox_px(cv):
            """外接框并集（=产出紧裁范围）→ 控件像素 (l,t,r,b) + 图坐标元组。"""
            boxes = [cv._item_box_units(it) for it in cv._items]
            ul = min(b[0] for b in boxes)
            ut = min(b[1] for b in boxes)
            ur = max(b[2] for b in boxes)
            ub = max(b[3] for b in boxes)
            px = tuple(
                int(round(off + u * cv._px_per_unit))
                for off, u in ((cv._off_x, ul), (cv._off_y, ut),
                               (cv._off_x, ur), (cv._off_y, ub))
            )
            return px, (ul, ut, ur, ub)

        (l_px, t_px, r_px, b_px), _ubox = _bbox_px(spine_cv)
        ok("成品截图范围框**恒显**：边线画在两图最外侧点的并集上",
           _crop_hits_x(spine_img, l_px) > 20
           and _crop_hits_x(spine_img, r_px) > 20,
           f"左 {_crop_hits_x(spine_img, l_px)} / "
           f"右 {_crop_hits_x(spine_img, r_px)} 像素")
        # 内部查灰要避开上下横边所在的行（矩形边框本来就贯穿全宽）
        _inner_l = _crop_hits_x(spine_img, l_px + 150, band=4,
                                y_from=t_px + 10, y_to=b_px - 10)
        _inner_r = _crop_hits_x(spine_img, r_px - 150, band=4,
                                y_from=t_px + 10, y_to=b_px - 10)
        ok("并集内部没有截图框线（虚线只在最外侧）",
           _inner_l == 0 and _inner_r == 0,
           f"内测命中 {_inner_l} / {_inner_r}")
        _w_before = _ubox[2] - _ubox[0]
        spine_cv.rotate_whole(30.0)
        spine_img2 = spine_cv.grab().toImage()
        ok("整版旋转时对齐线仍在原位（旋转对比基准）",
           _red_hits(spine_img2, x_px) > 5, f"命中 {_red_hits(spine_img2, x_px)}")
        spine_cv.refit()
        crop_img2 = spine_cv.grab().toImage()
        (_l2, _t2, _r2, _b2), _ubox2 = _bbox_px(spine_cv)
        ok("整版旋转后外接框并集外扩（截图范围跟着最外侧点走）",
           _ubox2[2] - _ubox2[0] > _w_before
           and _crop_hits_x(crop_img2, _l2) > 20
           and _crop_hits_x(crop_img2, _r2) > 20,
           f"宽 {_w_before:.0f}→{_ubox2[2] - _ubox2[0]:.0f}，"
           f"边线命中 {_crop_hits_x(crop_img2, _l2)} / "
           f"{_crop_hits_x(crop_img2, _r2)}")
        spine_cv.deleteLater()

        # ---------------- 7d. 滚轮缩放 + 渲染按帧合并（用户 2026-09-30）----
        # 「滑动滚轮，图片渲染区域减少渲染次数」：滚轮缩放以光标为锚、只改
        # 几何；重绘不跟事件走——连发期间并进帧窗口（每帧最多一帧、走快速
        # 档），停稳后补一帧高质量重绘。
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QWheelEvent as _QWheelEvent

        from desktop.components.imposition import canvas as _canvas_mod

        zoom_cv = ImpositionCanvas()
        zoom_cv.resize(600, 600)
        zoom_cv.set_page(S.default_items([str(a), str(b)]))
        zoom_cv.show()
        ctx.app.processEvents()
        zoom_cv.grab()  # 强制画一帧：把两张图解进缓存

        def _notch(dy: int, pos=None) -> None:
            """给画布发一格滚轮（+120 上滚/放大，-120 下滚/缩小），处理事件。"""
            p = pos or QPointF(zoom_cv.width() / 2, zoom_cv.height() / 2)
            ctx.app.sendEvent(
                zoom_cv,
                _QWheelEvent(
                    p, zoom_cv.mapToGlobal(p.toPoint()),
                    QPoint(0, 0), QPoint(0, dy),
                    Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                    Qt.ScrollPhase.ScrollUpdate, False,
                ),
            )
            for _ in range(2):
                ctx.app.processEvents()

        ok("载页默认倍率 = 适配可视区（不缩放）",
           abs(zoom_cv._zoom - 1.0) < 1e-9
           and abs(zoom_cv._px_per_unit - zoom_cv._fit_ppu) < 1e-9)

        anchor = QPointF(zoom_cv.width() * 0.6, zoom_cv.height() * 0.4)
        unit_before = zoom_cv._to_units(anchor)
        items_before = zoom_cv.items()
        _notch(120, anchor)
        unit_after = zoom_cv._to_units(anchor)
        ok("滚轮放大：锚点下的图坐标不动（以光标为锚）",
           abs(unit_before[0] - unit_after[0]) < 1e-6
           and abs(unit_before[1] - unit_after[1]) < 1e-6,
           f"{unit_before} → {unit_after}")
        ok("缩放只改几何：items 原样、图缓存不重解码",
           zoom_cv.items() == items_before
           and len(zoom_cv._images) == 2
           and zoom_cv._px_per_unit > zoom_cv._fit_ppu,
           f"ppu={zoom_cv._px_per_unit:.2f} fit={zoom_cv._fit_ppu:.2f}")
        ok("一格滚轮 = 1.15 倍",
           abs(zoom_cv._zoom - _canvas_mod.WHEEL_ZOOM_STEP) < 1e-6,
           f"zoom={zoom_cv._zoom:.4f}")

        # ---- 渲染合并：连发期间只有一个帧窗口，多余的滚动并到下一帧 ----
        wheel_src = (
            Path(__file__).resolve().parents[2]
            / "desktop" / "components" / "imposition" / "canvas.py"
        ).read_text(encoding="utf-8")
        wheel_src = wheel_src[
            wheel_src.index("def wheelEvent"):
            wheel_src.index("def _zoom_at")
        ]
        ok("滚轮事件不直接要重绘（重绘归帧窗口，减渲染的口子）",
           "self.update()" not in wheel_src)
        ok("连发第一滚：启动帧窗口（不立刻重绘）",
           zoom_cv._wheel_timer.isActive())
        _notch(120, anchor)
        _notch(120, anchor)
        ok("窗口内的后续滚动只挂起、不重复开窗（按帧合并）",
           zoom_cv._wheel_timer.isActive()
           and zoom_cv._wheel_paint_pending)
        zoom_cv._wheel_timer.stop()
        zoom_cv._on_wheel_frame()
        ok("窗口到期：画一帧，还有挂起就滚到下一帧（快速档保持）",
           zoom_cv._wheel_paint_pending is False
           and zoom_cv._wheel_timer.isActive()
           and zoom_cv._wheel_burst)
        zoom_cv._wheel_timer.stop()
        zoom_cv._on_wheel_frame()
        ok("滚动停稳：关快速档、补一帧高质量重绘",
           zoom_cv._wheel_burst is False)

        # ---- 倍率钳制 ----
        for _ in range(40):
            zoom_cv._zoom_at(QPointF(300, 300), 10.0)
        ok("放大利住在上限（相对适配基准）",
           abs(zoom_cv._zoom - _canvas_mod.ZOOM_MAX) < 1e-9,
           f"zoom={zoom_cv._zoom}")
        for _ in range(40):
            zoom_cv._zoom_at(QPointF(300, 300), 0.01)
        ok("缩不利住在下限",
           abs(zoom_cv._zoom - _canvas_mod.ZOOM_MIN) < 1e-9,
           f"zoom={zoom_cv._zoom}")

        # ---- 尺寸变化保留倍率；载页 / refit 才归一 ----
        zoom_cv.refit()  # 钳制测试把倍率利在了下限：先归一再放大
        zoom_cv._zoom_at(QPointF(300, 300), 1.5)
        ppu_before = zoom_cv._px_per_unit
        zoom_cv.resize(500, 500)
        ctx.app.processEvents()
        ok("窗口尺寸变化保留滚轮倍率（不打回原形）",
           abs(zoom_cv._zoom - 1.5) < 1e-9
           and abs(zoom_cv._px_per_unit - zoom_cv._fit_ppu * 1.5) < 1e-9
           and not math.isclose(zoom_cv._px_per_unit, ppu_before))
        zoom_cv.refit()
        ok("refit 归一倍率（回到打开时的样子）",
           abs(zoom_cv._zoom - 1.0) < 1e-9
           and abs(zoom_cv._px_per_unit - zoom_cv._fit_ppu) < 1e-9)
        zoom_cv.set_page(S.default_items([str(a), str(b)]))
        ok("载页归一倍率（换页回'打开就能看全'）",
           abs(zoom_cv._zoom - 1.0) < 1e-9)
        zoom_cv.clear_page()
        _notch(120)
        ok("空画布滚轮不炸、不动倍率",
           abs(zoom_cv._zoom - 1.0) < 1e-9)
        zoom_cv.deleteLater()

        # ---- 面板旋转组件：增量语义 / ±180° 跨界 / 程序化回填不回抛 ----
        def _column_index(box, widget) -> int:
            """控件在面板竖排布局里的下标（判「页级块在前、图片级块在后」）。"""
            for i in range(box.count()):
                if box.itemAt(i).widget() is widget:
                    return i
            return -1

        panel = ImpositionPanel()
        deltas: list[float] = []
        item_angles: list[float] = []
        panel.whole_rotate_delta.connect(deltas.append)
        panel.item_rotation_edited.connect(item_angles.append)
        ok("面板上没有「上移/下移」与「左转/右转 90°」按钮（2026-09-30 删除）",
           not any(hasattr(panel, name) for name in
                   ("up_button", "down_button",
                    "rotate_left_button", "rotate_right_button")))
        ok("旋转组件微调口径：滑块 0.01°/格、输入框 2 位小数步进 0.1°",
           (panel.whole_slider.minimum(), panel.whole_slider.maximum())
           == (-18000, 18000)
           and panel.whole_slider.singleStep() == 1
           and panel.whole_slider.pageStep() == 100
           and panel.whole_spin.decimals() == 2
           and panel.whole_spin.singleStep() == 0.1,
           f"slider={panel.whole_slider.minimum()}.."
           f"{panel.whole_slider.maximum()} "
           f"step={panel.whole_slider.singleStep()} "
           f"spin={panel.whole_spin.decimals()}位/"
           f"{panel.whole_spin.singleStep()}")
        panel.show()
        ctx.app.processEvents()
        ok("输入框在说明行、滑块通栏独占下一行（不挤一行）",
           panel.whole_spin.geometry().bottom()
           <= panel.whole_slider.geometry().top()
           and panel.whole_slider.width() > panel.whole_spin.width(),
           f"spin_bottom={panel.whole_spin.geometry().bottom()} "
           f"slider_top={panel.whole_slider.geometry().top()} "
           f"slider_w={panel.whole_slider.width()}")
        panel.whole_spin.setValue(10.0)
        ok("整体旋转组件：输入 10° 吐 +10° 增量", deltas == [10.0], str(deltas))
        panel.set_whole_angle(170.0)
        ok("程序化回填整版角度不吐增量", deltas == [10.0], str(deltas))
        panel.whole_spin.setValue(-170.0)
        ok("跨 ±180° 边界换算成 +20° 增量", deltas == [10.0, 20.0], str(deltas))
        ok("没有选中图时单图旋转组件禁用",
           not panel.item_spin.isEnabled() and not panel.item_slider.isEnabled())
        panel.set_item_rotation(45.0)
        ok("回填选中角后组件启用且值正确",
           panel.item_spin.isEnabled()
           and abs(panel.item_spin.value() - 45.0) < 0.01,
           str(panel.item_spin.value()))
        ok("单图回填不吐信号", item_angles == [], str(item_angles))
        panel.item_spin.setValue(60.0)
        ok("单图组件改值发**绝对角度**", item_angles == [60.0], str(item_angles))
        panel.set_item_rotation(None)
        ok("清空选中后单图组件重新禁用", not panel.item_spin.isEnabled())
        ok("面板分区：「操作当前图片页」页级块在前、「当前图片样式」图片级块在后",
           panel.item_section.title_label.text() == "当前图片样式"
           and 0 <= _column_index(panel.box, panel.clear_button)
           < _column_index(panel.box, panel.item_section))
        ok("面板上没有「选择拼版」按钮（2026-09-30 删除：入口只在左列虚线格）",
           not hasattr(panel, "add_button"))
        ok("「复位本页版面」独占一行 block（删除按钮挪走后不再拼行）",
           _column_index(panel.box, panel.reset_button) >= 0)
        _actions_row = next(
            (panel.box.itemAt(i).layout() for i in range(panel.box.count())
             if panel.box.itemAt(i).layout() is not None
             and panel.box.itemAt(i).layout().indexOf(panel.add_image_button) >= 0),
            None)
        ok("「删除选中图片」挪进页级区，与「新增图片」同一行（不在图片样式区块里）",
           _actions_row is not None
           and _actions_row.indexOf(panel.delete_item_button) >= 0
           and panel.item_section.layout().indexOf(panel.delete_item_button) < 0)
        ok("未选中图时删除按钮隐藏、新增按钮隐藏（两图页初始态）",
           panel.delete_item_button.isHidden()
           and panel.add_image_button.isHidden())
        panel.set_item_rotation(30.0)
        ok("选中图后「删除选中图片」露出（页级区里）",
           not panel.delete_item_button.isHidden())
        ok("「删除选中图片」用共享危险按钮样式 theme.danger_button_qss"
           "（2026-09-30 用户定：样式对齐任务列表删除按钮）",
           "#C93A3A" in panel.delete_item_button.styleSheet()
           and ":hover" in panel.delete_item_button.styleSheet()
           and "padding: 6px 12px 7px 12px" in panel.delete_item_button.styleSheet()
           and "#C0392B" not in panel.delete_item_button.styleSheet())
        ok("「删除选中图片」不带图标（红底上 fluent 深色图标对比度差）",
           panel.delete_item_button.icon().isNull())
        panel.set_single_page(True)
        ok("「删除选中图片」与「新增图片」等高（内边距补齐 fluent 上下边框）",
           panel.delete_item_button.sizeHint().height()
           == panel.add_image_button.sizeHint().height(),
           str((panel.delete_item_button.sizeHint().height(),
                panel.add_image_button.sizeHint().height())))
        panel.set_single_page(False)
        panel.set_item_rotation(None)
        ok("清空选中后删除按钮重新隐藏",
           panel.delete_item_button.isHidden())
        ok("「在流程中启用图片拼版」开关在面板最底部",
           0 <= _column_index(panel.box, panel.enabled_checkbox)
           and _column_index(panel.box, panel.enabled_checkbox)
           > _column_index(panel.box, panel.item_section))
        ok("说明挂在问号按钮上（不再平铺）",
           isinstance(getattr(panel, "help_button", None), HelpButton)
           and "可选节点" in panel.help_button.toolTip())
        ok("清空选中后「当前图片样式」区块灰掉",
           not panel.item_section._active)
        panel.set_item_rotation(30.0)
        ok("有选中图时「当前图片样式」区块高亮",
           panel.item_section._active, str(panel.item_section._active))
        panel.deleteLater()

        # ---- 页级接线：面板增量 → 画布即时转 → 停顿提交落盘 + 面板回填 ----
        page._save_imposition_pages(before_release)
        page._imposition_timer.stop()
        page.imposition_view.set_current(0)
        page.imposition_view.canvas.select(0)
        page.imposition_view.canvas.set_page(S.default_items([str(a), str(b)]))
        pump(ctx.app, times=4)
        page._on_imposition_whole_rotate(15.0)
        live = [it["rotation"] for it in page.imposition_view.canvas.items()]
        ok("整版增量**即时**作用于画布（不等落盘）",
           all(abs(r - 15.0) < 0.01 for r in live), str(live))
        page._commit_imposition_edit()
        page._imposition_timer.stop()
        saved = page._imposition_pages()[0]["items"]
        ok("停顿提交把整版旋转落盘（两张都 +15°）",
           all(abs(it["rotation"] - 15.0) < 0.01 for it in saved),
           str([it["rotation"] for it in saved]))
        ok("提交后面板回填整版角度",
           abs(page.imposition_panel.whole_spin.value() - 15.0) < 0.01,
           str(page.imposition_panel.whole_spin.value()))
        page.imposition_view.canvas.select(1)
        page._on_imposition_item_rotate(25.0)
        page._commit_imposition_edit()
        page._imposition_timer.stop()
        saved = page._imposition_pages()[0]["items"]
        ok("单图绝对角度落盘（只改选中的左槽）",
           abs(saved[1]["rotation"] - 25.0) < 0.01
           and abs(saved[0]["rotation"] - 15.0) < 0.01,
           str([it["rotation"] for it in saved]))
        ok("提交后单图组件回填选中角",
           page.imposition_panel.item_spin.isEnabled()
           and abs(page.imposition_panel.item_spin.value() - 25.0) < 0.01,
           str(page.imposition_panel.item_spin.value()))

        # ---------------- 8. 双击预览：双击图 → 原图；双击空白 → 虚线框范围组合
        # 用户 2026-09-30：双击某张图预览这张原图；在图片外面双击画布，
        # 预览灰色虚线框（成品截图范围 = page_bounds 紧裁）那块区域的组合图。
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QMouseEvent

        def _dbl(cv, x, y):
            return QMouseEvent(
                QEvent.Type.MouseButtonDblClick, QPointF(float(x), float(y)),
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )

        # ---- 画布层：命中分流（图上 → item，图外空白 → spread）----
        canvas3 = ImpositionCanvas()
        canvas3.resize(600, 600)
        canvas3.set_page(S.default_items([str(a), str(b)]))
        canvas3.show()
        ctx.app.processEvents()

        def _blank_pt(cv):
            """画布上的空白点：场景顶边（=所有图外接框上沿）再往上 6px。"""
            r = cv._rect_px(0)
            return (r.center().x(), max(2.0, cv._off_y - 6.0))

        def _item_pt(cv, index=0):
            """某张图 rect 里的点（取中心；默认版面两图不重叠）。"""
            c = cv._rect_px(index).center()
            return (c.x(), c.y())

        spread_hits: list[int] = []
        item_hits: list[int] = []
        canvas3.spread_double_clicked.connect(lambda: spread_hits.append(1))
        canvas3.item_double_clicked.connect(item_hits.append)
        bx, by = _blank_pt(canvas3)
        canvas3.mouseDoubleClickEvent(_dbl(canvas3, bx, by))
        ok("双击图片之外的空白 → 发 spread_double_clicked（预览组合）",
           spread_hits == [1] and item_hits == [],
           f"spread={spread_hits} item={item_hits}")
        ok("双击空白不把手势带起来（处理了就 accept，无编辑模式残留）",
           canvas3._mode is None and not canvas3._pressed,
           f"mode={canvas3._mode} pressed={canvas3._pressed}")
        # 右槽图中心（x∈[400,800] 图坐标 → 约 [300,582] 控件像素）
        ix, iy = _item_pt(canvas3, 0)
        canvas3.mouseDoubleClickEvent(_dbl(canvas3, ix, iy))
        ok("双击某张图 → 发 item_double_clicked 且是命中的槽位",
           item_hits == [0] and spread_hits == [1],
           f"item={item_hits} spread={spread_hits}")
        spread_hits.clear()
        item_hits.clear()
        canvas3.clear_page()
        canvas3.mouseDoubleClickEvent(_dbl(canvas3, 300, 40))
        ok("空画布双击不发预览信号",
           spread_hits == [] and item_hits == [],
           f"spread={spread_hits} item={item_hits}")
        canvas3.deleteLater()

        # ---- 视图层：信号 → 信号直连转发 + 提示语带双击说明 ----
        view2 = ImpositionViewWidget()
        view2.resize(900, 600)
        view2.show()
        ctx.app.processEvents()
        view2.set_pages([{"items": S.default_items([str(a), str(b)])}],
                        current=0)
        view_forward: list[str] = []
        view2.spread_preview_requested.connect(
            lambda: view_forward.append("spread"))
        view2.item_preview_requested.connect(
            lambda i: view_forward.append(f"item:{i}"))
        vb = _blank_pt(view2.canvas)
        vi = _item_pt(view2.canvas, 0)
        view2.canvas.mouseDoubleClickEvent(_dbl(view2.canvas, *vb))
        view2.canvas.mouseDoubleClickEvent(_dbl(view2.canvas, *vi))
        ok("视图把两种双击都转发给控制器（spread / item:槽位）",
           view_forward == ["spread", "item:0"], str(view_forward))
        ok("底部提示语写明双击预览的操作方式",
           "双击" in view2.hint.text() and "成品组合" in view2.hint.text(),
           view2.hint.text())
        view2.deleteLater()

        # ---- worker 层：合成结果 = page_bounds 紧裁（即灰色虚线框那块）----
        page_items = page._imposition_pages()[0]["items"]
        target = page._imposition_spread_target(0)
        ok("弹窗来源目标：整页左右组合（count=1，非单张原图）",
           target is not None and target.count == 1
           and "左右组合" in target.note, str(target and target.note))
        bounds = S.page_bounds({"items": [dict(i) for i in page_items]})
        _worker = target.render(1600)
        _got: dict = {}
        _worker.finished.connect(
            lambda _i, img, _s: _got.update(img=img))
        _worker.run()
        img = _got.get("img")
        ok("组合预览 worker 产出非空 QImage",
           img is not None and not img.isNull(),
           str(type(img)))
        if img is not None and not img.isNull():
            ratio_got = img.width() / img.height()
            ratio_bounds = (bounds[2] - bounds[0]) / (bounds[3] - bounds[1])
            ok("预览图宽高比 = 灰色虚线框（page_bounds）的宽高比",
               abs(ratio_got - ratio_bounds) < 0.01,
               f"图 {img.width()}x{img.height()} vs 界 {bounds}")

        # ---- 控制器层：_open_imposition_spread_preview 开弹窗（替身）----
        from desktop.components.viewers import image_zoom_dialog as _izd

        _seen_zoom: dict = {}

        class _FakeZoom:
            def __init__(self, *a, **k):
                _seen_zoom["factory"] = k.get("factory")
                _seen_zoom["shown"] = 0
                _seen_zoom["show_for"] = []

            def show(self):
                _seen_zoom["shown"] += 1

            def raise_(self):
                pass

            def activateWindow(self):
                pass

            def show_for(self, factory=None, index=0):
                _seen_zoom["show_for"].append((factory is not None, index))

            def close(self):
                pass

        _real_zoom_cls = _izd.ImageZoomDialog
        _izd.ImageZoomDialog = _FakeZoom
        try:
            page._open_imposition_spread_preview()
            ok("双击空白 → 控制器 show + show_for 打开预览弹窗",
               _seen_zoom.get("shown") == 1
               and _seen_zoom.get("show_for") == [(True, 0)],
               str(_seen_zoom))
            zoom_target = (_seen_zoom.get("factory") or (lambda _i: None))(0)
            ok("弹窗内容来源 = 左右组合目标（不是单张原图）",
               zoom_target is not None and zoom_target.count == 1
               and "左右组合" in zoom_target.note,
               str(zoom_target and zoom_target.note))
        finally:
            _izd.ImageZoomDialog = _real_zoom_cls
            page._imposition_zoom_dialog = None

        # ---------------- 9. 右键菜单：预览图片 / 编辑图片（不经预览弹窗）
        # 用户 2026-10-01：右键菜单两个入口，目标规则与双击一致（图上 →
        # 这张原图；空白 → 整页组合）；「编辑图片」原本是预览弹窗里的按钮，
        # 现在右键直达——单张图覆盖回写源图原图，整页组合写回拼版成品。
        from PySide6.QtCore import QEvent, QPoint
        from PySide6.QtGui import QContextMenuEvent
        from PySide6.QtWidgets import QDialog
        from qfluentwidgets.components.widgets.menu import RoundMenu

        from tests.selftests._context import wait_until

        _menu: dict = {}

        def _fake_menu_exec(self, pos, ani=True, aniType=None):
            _menu["actions"] = self.actions()
            return None

        _real_menu_exec = RoundMenu.exec
        RoundMenu.exec = _fake_menu_exec

        def _ctx(cv, x, y):
            return QContextMenuEvent(
                QContextMenuEvent.Reason.Mouse, QPoint(int(x), int(y)),
                QPoint(int(x), int(y)),
            )

        def _pick(choice: int):
            """点菜单里的第 choice 项（0=预览图片 1=编辑图片）。"""
            _menu["actions"][choice].trigger()

        try:
            # ---- 画布层：菜单两项 + 目标分流 ----
            canvas4 = ImpositionCanvas()
            canvas4.resize(600, 600)
            canvas4.set_page(S.default_items([str(a), str(b)]))
            canvas4.show()
            ctx.app.processEvents()

            hits: dict = {"preview_item": [], "preview_spread": 0,
                          "edit_item": [], "edit_spread": 0}
            canvas4.item_double_clicked.connect(
                lambda i: hits.__setitem__("preview_item", hits["preview_item"] + [i]))
            canvas4.spread_double_clicked.connect(
                lambda: hits.__setitem__("preview_spread", hits["preview_spread"] + 1))
            canvas4.item_edit_requested.connect(
                lambda i: hits.__setitem__("edit_item", hits["edit_item"] + [i]))
            canvas4.spread_edit_requested.connect(
                lambda: hits.__setitem__("edit_spread", hits["edit_spread"] + 1))
            selections: list[int] = []
            canvas4.selection_changed.connect(selections.append)

            ix, iy = _item_pt(canvas4, 0)
            canvas4.contextMenuEvent(_ctx(canvas4, ix, iy))
            ok("右键图上弹出菜单：两项是「预览图片 / 编辑图片」",
               [act.text() for act in _menu.get("actions", [])]
               == ["预览图片", "编辑图片"],
               str([act.text() for act in _menu.get("actions", [])]))
            ok("右键即选中那张图（与左键点击同款语义）",
               canvas4.selected() == 0 and selections == [0],
               f"selected={canvas4.selected()} selections={selections}")
            _pick(0)
            ok("右键图上点「预览图片」→ 与双击同一信号（预览这张原图）",
               hits["preview_item"] == [0] and hits["preview_spread"] == 0,
               str(hits))
            _pick(1)
            ok("右键图上点「编辑图片」→ 发 item_edit_requested（同槽位）",
               hits["edit_item"] == [0] and hits["edit_spread"] == 0,
               str(hits))

            bx, by = _blank_pt(canvas4)
            canvas4.contextMenuEvent(_ctx(canvas4, bx, by))
            _pick(0)
            _pick(1)
            ok("右键空白处：预览走 spread 信号、编辑走 spread_edit 信号",
               hits["preview_spread"] == 1 and hits["edit_spread"] == 1
               and hits["edit_item"] == [0],
               str(hits))
            canvas4.deleteLater()

            _menu.clear()
            empty_hits: list[int] = []
            empty_canvas = ImpositionCanvas()
            empty_canvas.item_edit_requested.connect(empty_hits.append)
            empty_canvas.contextMenuEvent(_ctx(empty_canvas, 30, 30))
            ok("空画布右键没有菜单", not _menu.get("actions"), str(_menu))
            empty_canvas.deleteLater()

            # ---- 视图层：编辑信号也直连转发 + 提示语提到右键 ----
            view3 = ImpositionViewWidget()
            view3.set_pages([{"items": S.default_items([str(a), str(b)])}],
                            current=0)
            edit_forward: list[str] = []
            view3.item_edit_requested.connect(
                lambda i: edit_forward.append(f"item:{i}"))
            view3.spread_edit_requested.connect(
                lambda: edit_forward.append("spread"))
            view3.canvas.item_edit_requested.emit(1)
            view3.canvas.spread_edit_requested.emit()
            ok("视图把两种右键编辑都转发给控制器（item:槽位 / spread）",
               edit_forward == ["item:1", "spread"], str(edit_forward))
            ok("底部提示语写明右键可编辑",
               "右键" in view3.hint.text() and "编辑" in view3.hint.text(),
               view3.hint.text())
            view3.deleteLater()

            # ---- 控制器层：右键图上「编辑图片」→ 编辑器（覆盖回写源图）----
            import desktop.components.viewers.image_editor as _ied

            _edit_seen: dict = {}
            _edited = _solid_qimage(EDIT_ITEM_COLOR, 64, 48)

            class _FakeEditorDialog:
                def __init__(self, parent, image, save_back=False):
                    _edit_seen["save_back"] = save_back

                def exec(self):
                    _edit_seen["exec"] = _edit_seen.get("mode", "ok")
                    return QDialog.DialogCode.Accepted

                def result_image(self):
                    return _edited

            _real_editor_cls = _ied.ImageEditorDialog
            _ied.ImageEditorDialog = _FakeEditorDialog

            from desktop.components.viewers.image_zoom_dialog import (
                overwrite_image_file,
            )

            def _pixel_of(path: Path):
                return _qimage_pixel(path, 2, 2)

            try:
                item_path = Path(
                    page._imposition_pages()[0]["items"][0]["file"]
                )
                ok("准备：拼版源图存在", item_path.exists())
                # 预热画布解码缓存，等会儿断言「缓存被丢掉」才有意义
                page.imposition_view.canvas._image(str(item_path))
                ok("准备：画布缓存里已有这张图",
                   str(item_path) in page.imposition_view.canvas._images)

                _edit_seen.clear()
                page._open_imposition_item_edit(0)
                ok("编辑器以 save_back 模式打开（完成 = 覆盖原图片）",
                   _edit_seen.get("save_back") is True
                   and _edit_seen.get("exec") == "ok", str(_edit_seen))
                ok("「完成」把编辑结果覆盖回源图原图",
                   _pixel_of(item_path) == EDIT_ITEM_COLOR,
                   f"item={item_path.name} 像素={_pixel_of(item_path)}")
                ok("画布解码缓存已丢（重绘读新图，不显示旧图）",
                   str(item_path) not in page.imposition_view.canvas._images)
                ok("源图变了 → 重新防抖合成已挂上",
                   page._imposition_dirty, f"dirty={page._imposition_dirty}")
                page._imposition_timer.stop()
                page._imposition_dirty = False

                # 取消编辑：不覆盖
                _edit_seen.clear()
                _edit_seen["mode"] = "reject"

                class _RejectEditor(_FakeEditorDialog):
                    def exec(self):
                        return QDialog.DialogCode.Rejected

                _ied.ImageEditorDialog = _RejectEditor
                before = _pixel_of(item_path)
                page._open_imposition_item_edit(0)
                ok("取消编辑不覆盖源图", _pixel_of(item_path) == before,
                   f"before={before} after={_pixel_of(item_path)}")
                _ied.ImageEditorDialog = _FakeEditorDialog
            finally:
                _ied.ImageEditorDialog = _real_editor_cls

            # ---- 控制器层：右键空白「编辑图片」→ 合成全分辨率 → 写回成品 ----
            from desktop.services.imposition import FILE_FMT

            out_path = page.store.imposition_output_dir(
                page.task_id
            ) / FILE_FMT.format(1)
            _spread_seen: dict = {}
            _spread_edited = _solid_qimage(EDIT_SPREAD_COLOR, 30, 20)

            class _FakeSpreadEditor:
                def __init__(self, parent, image, save_back=False):
                    _spread_seen["save_back"] = save_back
                    _spread_seen["size"] = (image.width(), image.height())

                def exec(self):
                    return QDialog.DialogCode.Accepted

                def result_image(self):
                    return _spread_edited

            _ied.ImageEditorDialog = _FakeSpreadEditor
            try:
                if out_path.exists():
                    out_path.unlink()
                page._open_imposition_spread_edit()
                done = wait_until(
                    ctx.app,
                    lambda: out_path.exists()
                    and _pixel_of(out_path) == EDIT_SPREAD_COLOR,
                )
                ok("整页组合编辑：按产出口径合成 → 编辑器 → 覆盖成品文件",
                   done and _pixel_of(out_path) == EDIT_SPREAD_COLOR,
                   f"out={out_path.name} exists={out_path.exists()} "
                   f"pixel={_pixel_of(out_path) if out_path.exists() else None}")
                ok("编辑器以 save_back 模式打开（成品有真实文件可回写）",
                   _spread_seen.get("save_back") is True, str(_spread_seen))
                ok("给编辑器的是全分辨率组合图（不缩）",
                   _spread_seen.get("size") == (
                       _spread_edited.width(), _spread_edited.height())
                   or (_spread_seen.get("size") or (0, 0))[0]
                   >= _spread_edited.width(),
                   str(_spread_seen))
                ok("挂着的防抖合成被取消（不会用未编辑结果冲掉手工修饰）",
                   not page._imposition_dirty,
                   f"dirty={page._imposition_dirty}")
            finally:
                _ied.ImageEditorDialog = _real_editor_cls
        finally:
            RoundMenu.exec = _real_menu_exec
    finally:
        if page is not None:
            try:
                page._imposition_timer.stop()
            except RuntimeError:
                pass
            # ⚠️ 用 shutdown_all_workers 而不是 shutdown_workers：本页是**独立**
            # 构造的（不挂在 ctx.w 上），它自己的 PDF 预览等子控件各有线程宿主；
            # 只收页面自己的会让那些线程活到解释器退出（同进程后续模块还在跑）。
            page.shutdown_all_workers()
            page.hide()
            page.deleteLater()
            pump(ctx.app, times=4)
        shutil.rmtree(tmp, ignore_errors=True)
