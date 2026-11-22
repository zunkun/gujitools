# -*- coding: utf-8 -*-
"""2b. 并发合成（用户 2026-10-03 报「程序容易跑崩溃」） / 3. 剩余未选清单 / 3b. 自动拼版规则（用户 2026-09-30） / 3b-2. 无侧半幅（提交计划 role，用户 2026-10-23） / 3b-3. 计划与下游文件名写法不一致（0004）"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import GREEN, RED, _mk, _names
    from pathlib import Path
    from desktop.services import imposition as S
    from PIL import Image as _PILImage
    from tests.selftests._context import make_pdf, ok, pump
    import threading
    import threading

    big = _mk(st.tmp / "big.png", GREEN, (1400, 1800))
    big_page = S.normalize_page(
        {
            "items": [
                {
                    "file": str(big),
                    "rect": [0.0, 0.0, 1400.0, 1800.0],
                    "rotation": 0,
                }
            ]
        }
    )
    race_dir = st.tmp / "compose_race"
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
    ok(
        "多线程并发合成不抛异常（老实现这里会 PermissionError）",
        not errors,
        str(errors[:3]),
    )

    from PIL import Image as _PILImage

    def _decodable(path) -> bool:
        """真解码一遍：半张 PNG 会在这里抛或给出异常尺寸。"""
        try:
            with _PILImage.open(path) as im:
                im.load()
            return True
        except Exception:  # noqa: BLE001 - 打不开就是坏图
            return False

    ok(
        "并发合成后每页都是完整可解码的 PNG（不是半张图）",
        all(_decodable(race_dir / n) for n in ("0001.png", "0003.png", "0006.png")),
        str(sorted(p.name for p in race_dir.glob("*.png"))),
    )
    ok(
        "并发合成不留 .part 临时文件",
        list(race_dir.glob("*.part")) == [],
        str(list(race_dir.glob("*.part"))),
    )
    ok(
        "并发合成页数正确（没被 _sweep_stale 误删）",
        len(list(race_dir.glob("*.png"))) == 6,
        str(len(list(race_dir.glob("*.png")))),
    )
    remaining = S.remaining_files([st.a, st.b, st.c, st.d], {"pages": [st.made]})
    ok(
        "剩余未拼版的图片 = 未被任何页引用的那些",
        _names(remaining) == ["2-r.png", "2-l.png"],
        str(_names(remaining)),
    )
    # 「删除图片」黑名单（removed 字段）：软删除，恢复即回到候选
    norm = S.normalize_doc(
        {"enabled": True, "pages": [st.made], "removed": [str(st.c), str(st.c), "", "  "]}
    )
    ok(
        "normalize_doc 保留黑名单（去重、丢空项、保序）",
        norm["removed"] == [str(st.c)],
        str(norm.get("removed")),
    )
    ok(
        "老文档没有 removed 键也能读",
        S.normalize_doc({"enabled": False, "pages": []})["removed"] == [],
    )
    ok(
        "remaining_files 同时排除已用与已删除的图",
        _names(
            S.remaining_files([st.a, st.b, st.c, st.d], {"pages": [st.made], "removed": [str(st.c)]})
        )
        == ["2-l.png"],
        str(
            _names(
                S.remaining_files(
                    [st.a, st.b, st.c, st.d], {"pages": [st.made], "removed": [str(st.c)]}
                )
            )
        ),
    )
    ok(
        "excluded_files 按源清单顺序列出被删除的图",
        _names(S.excluded_files([st.a, st.b, st.c, st.d], {"removed": [str(st.d), str(st.c)]}))
        == ["2-r.png", "2-l.png"],
        str(_names(S.excluded_files([st.a, st.b, st.c, st.d], {"removed": [str(st.d), str(st.c)]}))),
    )
    st.full = _mk(st.src / "3.png", (128, 128, 128))

    def _page_shapes(pages):
        return [tuple(Path(i["file"]).name for i in p["items"]) for p in pages]
    st._page_shapes = _page_shapes

    ok(
        "classify_source 按文件名后缀分形态（-r/-l/无后缀）",
        S.classify_source(st.a) == S.SOURCE_RIGHT
        and S.classify_source(st.b) == S.SOURCE_LEFT
        and S.classify_source(st.full) == S.SOURCE_FULL,
        f"{S.classify_source(st.a)}/{S.classify_source(st.b)}/"
        f"{S.classify_source(st.full)}",
    )
    single = S.make_single_page(st.full)
    ok(
        "整幅图自成一页（版面只有一项、原始尺寸）",
        single is not None
        and len(single["items"]) == 1
        and Path(single["items"][0]["file"]).name == "3.png"
        and single["items"][0]["rect"][2:] == [400.0, 600.0],
        str(single),
    )
    assert single is not None  # ⚠️ 上一行已判过
    ok(
        "单图页产出 = 原图尺寸紧裁",
        S.compose_page(single).size == (400, 600),
        str(S.compose_page(single).size),
    )

    auto = S.auto_impose_pages([st.a, st.b, st.c, st.d])
    ok(
        "自动拼版（r,l,r,l）：首位 -r 单独一页，左半幅与下一个右半幅配对",
        st._page_shapes(auto) == [("1-r.png",), ("1-l.png", "2-r.png"), ("2-l.png",)],
        str(st._page_shapes(auto)),
    )
    ok(
        "自动配对同样序号在前的进右槽",
        Path(auto[1]["items"][0]["file"]).name == "1-l.png",
    )
    ok(
        "自动拼版：末尾落单的左半幅单独一页",
        len(auto[-1]["items"]) == 1
        and Path(auto[-1]["items"][0]["file"]).name == "2-l.png",
    )

    auto_full = S.auto_impose_pages([st.full, st.a, st.b, st.c, st.d])
    ok(
        "整幅后拼版重开：整幅单独一页、随后首位 -r 单独一页、再左+右配对",
        st._page_shapes(auto_full)
        == [("3.png",), ("1-r.png",), ("1-l.png", "2-r.png"), ("2-l.png",)],
        str(st._page_shapes(auto_full)),
    )
    ok(
        "上一张等配对时遇到整幅 → 上一张单独一页（整幅不与它拼）",
        st._page_shapes(S.auto_impose_pages([st.b, st.full])) == [("1-l.png",), ("3.png",)],
        str(st._page_shapes(S.auto_impose_pages([st.b, st.full]))),
    )
    ok(
        "整幅夹在中间同样断开配对",
        st._page_shapes(S.auto_impose_pages([st.a, st.b, st.full, st.c, st.d]))
        == [("1-r.png",), ("1-l.png",), ("3.png",), ("2-r.png",), ("2-l.png",)],
        str(st._page_shapes(S.auto_impose_pages([st.a, st.b, st.full, st.c, st.d]))),
    )

    # 页号必须连续（用户 2026-09-30：不连续的图片不可以合并在一页）
    e = _mk(st.src / "5-r.png", RED)
    f2 = _mk(st.src / "4-l.png", GREEN)
    ok(
        "source_page_number 按文件名前缀解析（1-r→1、004-l→4、cover→None）",
        S.source_page_number(st.a) == 1
        and S.source_page_number(st.src / "004-l.png") == 4
        and S.source_page_number(st.src / "cover.png") is None,
        f"{S.source_page_number(st.a)}/"
        f"{S.source_page_number(st.src / '004-l.png')}/"
        f"{S.source_page_number(st.src / 'cover.png')}",
    )
    ok(
        "页号不连续（1-l 之后直接 5-r）→ 不配对、各自单独一页",
        st._page_shapes(S.auto_impose_pages([st.b, e])) == [("1-l.png",), ("5-r.png",)],
        str(st._page_shapes(S.auto_impose_pages([st.b, e]))),
    )
    ok(
        "断口后重新开始：5-r 等不到 4-l（序号也不连续）、4-l 落单",
        st._page_shapes(S.auto_impose_pages([st.a, st.b, e, f2]))
        == [("1-r.png",), ("1-l.png",), ("5-r.png",), ("4-l.png",)],
        str(st._page_shapes(S.auto_impose_pages([st.a, st.b, e, f2]))),
    )
    ok(
        "同一页号的 l→r 不配对（必须跨页号：前一左＋后一右）",
        st._page_shapes(S.auto_impose_pages([st.d, st.c])) == [("2-l.png",), ("2-r.png",)],
        str(st._page_shapes(S.auto_impose_pages([st.d, st.c]))),
    )
    ok(
        "读不到尺寸的图跳过（不产出残页）",
        S.auto_impose_pages([st.tmp / "missing.png"]) == [],
    )
    ok("空清单自动拼版 = 空页清单", S.auto_impose_pages([]) == [])
    p21 = _mk(st.src / "21.png", RED)
    p22 = _mk(st.src / "22.png", GREEN)
    p23 = _mk(st.src / "23.png", RED)
    p24 = _mk(st.src / "24.png", GREEN)
    full30 = _mk(st.src / "30.png", (128, 128, 128))
    unsided_roles = {f"{n}": "half-unsided" for n in (21, 22, 23, 24, 30)}

    def _role_for(text):
        return unsided_roles.get(Path(str(text)).stem)

    ok(
        "source_kind：没有计划时无后缀图仍是整幅（旧行为）",
        S.source_kind(p21) == S.SOURCE_FULL,
    )
    ok(
        "source_kind：计划说 half-unsided 时按半幅认",
        S.source_kind(p21, _role_for) == S.SOURCE_HALF_UNSIDED,
        S.source_kind(p21, _role_for),
    )
    ok(
        "无侧半幅：两张连续 → 拼成一页（序号在前进右槽）",
        st._page_shapes(S.auto_impose_pages([p21, p22], _role_for))
        == [("21.png", "22.png")],
        str(st._page_shapes(S.auto_impose_pages([p21, p22], _role_for))),
    )
    ok(
        "无侧半幅：页号不连续 → 各自单独一页",
        st._page_shapes(S.auto_impose_pages([p21, p23], _role_for))
        == [("21.png",), ("23.png",)],
        str(st._page_shapes(S.auto_impose_pages([p21, p23], _role_for))),
    )
    ok(
        "整幅（role=full）打断无侧半幅的配对",
        st._page_shapes(S.auto_impose_pages([p21, full30, p22], _role_for))
        == [("21.png",), ("30.png",), ("22.png",)],
        str(st._page_shapes(
            S.auto_impose_pages([p21, full30, p22], _role_for))),
    )
    ok(
        "无侧半幅不与带侧别的半幅混拼",
        st._page_shapes(S.auto_impose_pages(
            [st.b, p21], lambda text: "half-unsided"
            if Path(str(text)).stem == "21" else None,
        )) == [("1-l.png",), ("21.png",)],
        str(st._page_shapes(S.auto_impose_pages(
            [st.b, p21], lambda text: "half-unsided"
            if Path(str(text)).stem == "21" else None,
        ))),
    )
    ok(
        "没有 role_for 时无后缀图维持旧行为（不配对）",
        st._page_shapes(S.auto_impose_pages([p21, p22]))
        == [("21.png",), ("22.png",)],
        str(st._page_shapes(S.auto_impose_pages([p21, p22]))),
    )
    stale_l = _mk(st.src / "21-l.png", RED)
    stale_r = _mk(st.src / "22-r.png", GREEN)
    legacy = S.expand_role_aliases(
        {"21": "half-unsided", "22": "half-unsided"}
    )
    ok(
        "别名：计划无后缀 → 也认旧名 21-l / 22-r",
        legacy.get("21-l") == "half-unsided"
        and legacy.get("22-r") == "half-unsided",
        str(legacy),
    )
    reverse = S.expand_role_aliases({"21-l": "half-left"})
    ok(
        "别名：计划带 -l → 也认旧名 21（用户改过侧别）",
        reverse.get("21") == "half-left", str(reverse),
    )
    ok(
        "别名不覆盖显式 label",
        S.expand_role_aliases({"21": "half-unsided", "21-l": "half-left"})
        .get("21-l") == "half-left",
        str(S.expand_role_aliases(
            {"21": "half-unsided", "21-l": "half-left"})),
    )
    sided = S.expand_role_aliases(
        {"21-l": "half-left", "21-r": "half-right"}
    )
    ok(
        "真双栏页（同页两个 role）不造别名，避免左右被认成同一边",
        "21" not in sided
        and sided.get("21-l") == "half-left"
        and sided.get("21-r") == "half-right",
        str(sided),
    )
    legacy_role_for = lambda text: legacy.get(Path(str(text)).stem)
    ok(
        "旧名 -l + 新名无后缀 的两张连续页能拼成一页（0004 现场）",
        st._page_shapes(S.auto_impose_pages(
            [stale_l, _mk(st.src / "22.png", GREEN)], legacy_role_for,
        )) == [("21-l.png", "22.png")],
        str(st._page_shapes(S.auto_impose_pages(
            [stale_l, _mk(st.src / "22.png", GREEN)], legacy_role_for,
        ))),
    )
    ok(
        "旧名 -l + -r（同一批旧产物）同样按无侧半幅配对",
        st._page_shapes(S.auto_impose_pages(
            [stale_l, stale_r], legacy_role_for,
        )) == [("21-l.png", "22-r.png")],
        str(st._page_shapes(S.auto_impose_pages(
            [stale_l, stale_r], legacy_role_for,
        ))),
    )

