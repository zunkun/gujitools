# -*- coding: utf-8 -*-
"""4. 操作画布（拖动 / 缩放 / 旋转 / 复位） / 4b. 选中态常显 + 操作框只在按住期间（用户 2026-09-30） / 左键拖动**框外**圆钮 → 旋转选中的那张图（用户 2026-10-23） / 4b-2. 选中的图永远画在最上面（用户 2026-10-10）"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import BLUE, FRAME_RGB, YELLOW, _count_near, _px_near, ROOT
    from desktop.components.imposition.canvas import ImpositionCanvas
    from pathlib import Path
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QPointF, QSize, Qt
    from desktop.services import imposition as S
    from tests.selftests._context import make_pdf, ok, pump
    from PySide6.QtGui import QImage

    st.canvas = ImpositionCanvas()
    st.canvas.resize(600, 600)
    st.canvas.set_page(st.made["items"])
    ok(
        "画布载入两张图、默认不选中（切页后图片操作区不激活）",
        len(st.canvas.items()) == 2 and st.canvas.selected() == -1,
        str(st.canvas.selected()),
    )
    ok(
        "画布能从文件解出图（不是空图）",
        not QImage(st.made["items"][0]["file"]).isNull(),
    )
    # 图缓存必须随换页清掉：一页两张几千像素见方的原图，一路翻页会吃到 GB 级
    st.canvas._image(st.made["items"][0]["file"])
    ok("画布按需缓存当前页的图", len(st.canvas._images) == 1)
    st.canvas.set_page(st.made["items"])
    ok("换页丢掉上一页的图缓存（内存有界）", st.canvas._images == {})

    # 贴图底图：源图先按档位降采样（一次缩到几百像素会跳采样、看着发虚）
    big_path = st.tmp / "big.png"
    big = QImage(4000, 3000, QImage.Format.Format_RGB32)
    big.fill(0xFFFFFFFF)
    big.save(str(big_path))
    shown = st.canvas._display_image(str(big_path), 500)
    ok("贴图底图按档位预缩（4000px 源图 → 600 档）",
       shown is not None and max(shown.width(), shown.height()) == 600,
       "" if shown is None else f"{shown.width()}x{shown.height()}")
    ok("同一档位重复取底图命中缓存（拖动/旋转不重复重采样）",
       st.canvas._display_image(str(big_path), 500) is shown, "")
    st.canvas.set_page(st.made["items"])
    ok("换页连贴图底图缓存一起丢掉", st.canvas._display_cache == {})

    st.canvas.select(1)
    knob = st.canvas._rotate_knob(1)
    ok(
        "选中项上方有旋转钮（在框外、水平居中）",
        abs(knob.x() - st.canvas._rect_px(1).center().x()) < 0.01
        and knob.y() < st.canvas._rect_px(1).y(),
        f"{knob.x():.1f},{knob.y():.1f}",
    )
    hit = st.canvas._hit_handle(1, knob)
    local = st.canvas._to_local_px(1, knob)
    klocal = st.canvas._rotate_knob_local(1)
    ok(
        "旋转钮能被命中",
        hit == 8,
        f"hit={hit} local=({local.x():.2f},{local.y():.2f}) "
        f"knob_local=({klocal.x():.2f},{klocal.y():.2f})",
    )
    corners = [QPointF(x, y) for x, y in st.canvas._handle_positions(1)]
    ok(
        "四角手柄能按位置命中（左上=0 / 右上=1 / 右下=2 / 左下=3）",
        [st.canvas._hit_handle(1, pos) for pos in corners[:4]] == [0, 1, 2, 3],
        str([st.canvas._hit_handle(1, pos) for pos in corners[:4]]),
    )
    ok(
        "四边命中带落在边上（上边=4 / 右边=5）",
        st.canvas._hit_handle(1, corners[4]) == 4
        and st.canvas._hit_handle(1, corners[5]) == 5,
    )
    st.canvas.rotate_selected(90.0)
    ok(
        "旋转 90° 写进 items",
        abs(st.canvas.items()[1]["rotation"] - 90.0) < 0.01,
        str(st.canvas.items()[1]["rotation"]),
    )
    # 默认版面（复位用）：按两张图的**原始像素**并排，旋转归零
    reset = S.default_items([str(st.a), str(st.b)])
    ok(
        "默认版面 = 原始尺寸并排 + 无旋转（复位用）",
        reset is not None
        and reset[0]["rect"] == [400.0, 0.0, 400.0, 600.0]
        and reset[1]["rect"] == [0.0, 0.0, 400.0, 600.0]
        and all(item["rotation"] == 0.0 for item in reset),
        str(reset),
    )

    events: list[list] = []
    st.canvas.items_changed.connect(events.append)
    st.canvas.select(0)
    rect0 = st.canvas.items()[0]["rect"][0]
    st.canvas._items[0]["rect"][0] += 25.0
    st.canvas._dirty = True
    ok("未松手时还不发信号（拖动过程只重绘）", not events)
    st.canvas.flush_pending()
    ok(
        "flush_pending 补齐未松手的改动",
        len(events) == 1 and abs(events[0][0]["rect"][0] - (rect0 + 25.0)) < 0.01,
        str(events[0][0]["rect"] if events else None),
    )
    ok("松手后不再重复发（dirty 已清）", not st.canvas.flush_pending())
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent

    def _mouse(kind, pos):
        return QMouseEvent(
            kind,
            QPointF(pos[0], pos[1]),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    st._mouse = _mouse

    st.canvas.select(1)
    selected_px = _count_near(st.canvas.grab().toImage(), FRAME_RGB)
    ok(
        "只选中（没按住）也画**细选中框**（选中状态常显）",
        selected_px > 20 and not st.canvas.frame_visible(),
        f"选中框像素={selected_px}",
    )
    # 旋转钮必须**选中后常显、且在图片外面**（用户 2026-10-23：
    # 「可以在图片外面……哪个图片是选中的，就旋转哪个图片，鼠标左键」）：
    # 只在按住时画等于没有抓手，点不到也看不到。
    knob_shot = st.canvas.grab().toImage()
    knob_pos = st.canvas._rotate_knob(1)
    knob_px = sum(
        1
        for dy in range(-8, 9)
        for dx in range(-8, 9)
        if _px_near(knob_shot, int(knob_pos.x()) + dx,
                    int(knob_pos.y()) + dy, FRAME_RGB)
    )
    ok(
        "选中后旋转钮**常显在图片外面**（框外上方，不按住也能看到）",
        knob_px >= 3
        and not st.canvas._item_contains_px(1, knob_pos)
        and not st.canvas.frame_visible(),
        f"钮像素={knob_px} 钮=({knob_pos.x():.0f},{knob_pos.y():.0f})",
    )
    center = st.canvas._rect_px(1).center()
    st.canvas.mousePressEvent(
        st._mouse(QEvent.Type.MouseButtonPress, (center.x(), center.y()))
    )
    ok("按下鼠标 → 升级为带手柄的完整操作框", st.canvas.frame_visible())
    pressed_px = _count_near(st.canvas.grab().toImage(), FRAME_RGB)
    ok(
        "按住时确实画出了虚线框 + 手柄 + 旋转钮",
        pressed_px > selected_px + 100,
        f"选中框 {selected_px} → 按住 {pressed_px} 像素",
    )
    st.canvas.mouseReleaseEvent(
        st._mouse(QEvent.Type.MouseButtonRelease, (center.x(), center.y()))
    )
    released_px = _count_near(st.canvas.grab().toImage(), FRAME_RGB)
    ok(
        "松手 → 手柄全框消失、回到常显选中细框",
        not st.canvas.frame_visible() and 0 < released_px < pressed_px,
        f"选中={selected_px} 按住={pressed_px} 松手={released_px}",
    )
    before_angle = float(st.canvas.selected_rotation() or 0.0)
    knob_events: list[list] = []
    st.canvas.items_changed.connect(knob_events.append)
    knob_now = st.canvas._rotate_knob(1)
    knob_center = st.canvas._rect_px(1).center()
    st.canvas.mousePressEvent(
        st._mouse(QEvent.Type.MouseButtonPress,
               (knob_now.x(), knob_now.y()))
    )
    ok("左键按在框外圆钮上 → 进入旋转手势", st.canvas._mode == "rotate",
       str(st.canvas._mode))
    # 把指针绕图心转到"下一个直角"位置（钮离图心距离不变）
    arm = knob_center.y() - knob_now.y()  # 该项 rotation=90°，钮在正右方
    arm = max(abs(arm), abs(knob_now.x() - knob_center.x()), 1.0)
    st.canvas.mouseMoveEvent(
        st._mouse(QEvent.Type.MouseMove,
               (knob_center.x(), knob_center.y() + arm))
    )
    st.canvas.mouseReleaseEvent(
        st._mouse(QEvent.Type.MouseButtonRelease,
               (knob_center.x(), knob_center.y() + arm))
    )
    after_angle = float(st.canvas.selected_rotation() or 0.0)
    turned = (after_angle - before_angle) % 360.0
    ok(
        "拖动框外圆钮旋转的是**选中的那张图**（左键 +90°）",
        abs(turned - 90.0) < 2.0 and bool(knob_events),
        f"{before_angle:.1f} → {after_angle:.1f}（转 {turned:.1f}°），"
        f"上报 {len(knob_events)} 次",
    )
    # 虚线是**样式常量**层面的要求（像素级"是不是虚线"太脆，改查定义处）
    canvas_src = "".join(
        (
            ROOT
            / "desktop"
            / "components"
            / "imposition"
            / "canvas"
            / name
        ).read_text(encoding="utf-8")
        for name in ("constants.py", "paint.py")
    )
    # PySide6 6.x 的存根把枚举收进了 ``Qt.PenStyle``：未限定的 ``Qt.DashLine``
    # 在运行期仍可用（同一值），但 pyright 会报 reportAttributeAccessIssue，
    # 所以全仓统一写限定形式，这里跟着钉限定形式。
    ok(
        "选中框用的是 Qt.PenStyle.DashLine（虚线）",
        "FRAME_STYLE = Qt.PenStyle.DashLine" in canvas_src
        and "FRAME_STYLE," in canvas_src,
        "框线样式定义/使用处不匹配",
    )
    overlap = ImpositionCanvas()
    overlap.resize(600, 600)
    overlap.set_page(
        [
            {"file": str(st.c), "rect": [0.0, 0.0, 400.0, 600.0], "rotation": 0.0},
            {"file": str(st.d), "rect": [200.0, 0.0, 400.0, 600.0], "rotation": 0.0},
        ]
    )
    # 探针取在重叠区内、避开红色对齐线（x=300 units）：x 取 240 units
    st.probe = QPointF(
        overlap._rect_px(1).x() + overlap._rect_px(0).width() * 0.1,
        overlap._rect_px(0).center().y(),
    )
    shot = overlap.grab().toImage()
    ok(
        "未选中时按清单顺序画（后画的黄图盖住蓝图）",
        _px_near(shot, int(st.probe.x()), int(st.probe.y()), YELLOW)
        and not _px_near(shot, int(st.probe.x()), int(st.probe.y()), BLUE),
    )
    overlap.select(0)
    shot = overlap.grab().toImage()
    ok(
        "选中蓝图 → 蓝图浮到最上面（重叠区变蓝）",
        _px_near(shot, int(st.probe.x()), int(st.probe.y()), BLUE)
        and not _px_near(shot, int(st.probe.x()), int(st.probe.y()), YELLOW),
        f"probe=({st.probe.x():.0f},{st.probe.y():.0f})",
    )
    ok(
        "命中判定优先命中选中的图（重叠区点到的是它）",
        overlap._item_at(st.probe) == 0,
        str(overlap._item_at(st.probe)),
    )
    overlap.select(-1)
    shot = overlap.grab().toImage()
    ok(
        "取消选中 → 恢复清单顺序（重叠区回到黄）",
        _px_near(shot, int(st.probe.x()), int(st.probe.y()), YELLOW),
    )

