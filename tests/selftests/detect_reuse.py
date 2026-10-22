# -*- coding: utf-8 -*-
"""检测结果复用判据（``desktop/services/detect_reuse.py``）自测。

背景（用户 2026-10-20 第二个问题）
    1000+ 页的书第二次点「检测文本框」时，绝大多数页的框与上次一模一样。
    复用判据写在条目里（``src`` 文件戳 + ``det`` 检测指纹），双匹配才跳过重跑。

本模块是纯逻辑，不起 GUI、不加载模型，钉住：
1. ``file_stamp`` 随文件内容变化；
2. ``split`` 只挑 ``src``+``det`` 全匹配的页；
3. ``det`` 不匹配（换了版本/口径）⇒ 全部重新检测；
4. ``det`` 不匹配（换了版本/口径）⇒ 不复用；
5. 无框页同样可复用（否则"检测过但没框"的页每次都重跑）；
6. 负载形状符合槽位约定（1 槽=整幅、2 槽=左右）。
"""

NAME = "detect_reuse"
DEPENDS: list[str] = []
TITLE = "检测结果复用（src+det 双指纹）"


def run(ctx) -> None:
    import os
    import tempfile
    from pathlib import Path

    from desktop.services import detect_reuse as dr
    from tests.selftests._context import ok

    tmp = Path(tempfile.mkdtemp(prefix="guji_reuse_"))
    try:
        a = tmp / "0001.png"
        b = tmp / "0002.png"
        a.write_bytes(b"aaaa")
        b.write_bytes(b"bbbb")

        # ---- 1. 文件戳随内容/时间变化 ----
        stamp1 = dr.file_stamp(a)
        ok("file_stamp 返回 [字节数, mtime_ns]",
           isinstance(stamp1, list) and len(stamp1) == 2 and stamp1[0] == 4,
           str(stamp1))
        a.write_bytes(b"aaaa-bigger")
        os.utime(a, ns=(stamp1[1] + 10**9, stamp1[1] + 10**9))
        stamp2 = dr.file_stamp(a)
        ok("文件改过 → 文件戳变化", stamp2 != stamp1, f"{stamp1} → {stamp2}")
        ok("文件不存在 → None", dr.file_stamp(tmp / "nope.png") is None)

        det = dr.det_fingerprint()
        doc = {
            "0001": {"boxes": [[1, 2, 3, 4], [5, 6, 7, 8]], "origin": "auto",
                     dr.FIELD_SRC: stamp2, dr.FIELD_DET: det},
            "0002": {"boxes": [], "origin": "auto",
                     dr.FIELD_SRC: dr.file_stamp(b), dr.FIELD_DET: det},
        }

        # ---- 2. 双匹配才复用 ----
        reuse, todo = dr.split([a, b], doc, det)
        ok("src+det 全匹配 → 复用（含无框页）",
           sorted(reuse) == ["0001", "0002"], f"reuse={sorted(reuse)}")
        ok("复用负载标明 reused=True",
           all(item.get("reused") is True for item in reuse.values()), str(reuse))
        ok("无需检测的页为空", todo == [], str(todo))

        # ---- 3. 负载形状按槽位还原 ----
        ok("2 槽 → left/right",
           reuse["0001"]["left"] == [1, 2, 3, 4]
           and reuse["0001"]["right"] == [5, 6, 7, 8]
           and reuse["0001"]["full"] is None, str(reuse["0001"]))
        ok("0 槽 → 三个都 None（无框页）",
           reuse["0002"]["left"] is None and reuse["0002"]["right"] is None
           and reuse["0002"]["full"] is None, str(reuse["0002"]))
        ok("1 槽 → full（整幅）",
           dr.payload_of({"boxes": [[0, 0, 9, 9]]})["full"] == [0, 0, 9, 9],
           str(dr.payload_of({"boxes": [[0, 0, 9, 9]]})))

        # ---- 4. det 不匹配 → 不复用 ----
        other = "deadbeefcafe"
        ok("det 指纹不同（版本/口径变了）", other != det, f"{det} vs {other}")
        reuse2, todo2 = dr.split([a, b], doc, other)
        ok("det 变了 ⇒ 全部重新检测", reuse2 == {} and len(todo2) == 2,
           f"reuse={reuse2} todo={todo2}")

        # ---- 5. src 不匹配 → 不复用（只挑该页）----
        doc["0002"] = dict(doc["0002"])
        doc["0002"][dr.FIELD_SRC] = [999, 111]
        reuse3, todo3 = dr.split([a, b], doc, det)
        ok("只有文件戳对不上的那一页重跑",
           sorted(reuse3) == ["0001"] and [p.name for p in todo3] == ["0002.png"],
           f"reuse={sorted(reuse3)} todo={[p.name for p in todo3]}")

        # ---- 6. 条目缺失/畸形 → 不复用 ----
        ok("没有条目的页不复用",
           dr.entry_usable(None, a, det) is False)
        ok("畸形条目不复用",
           dr.entry_usable({"boxes": []}, a, det) is False)

        # ---- 7. source_key：同一路径必得同一键 ----
        ok("同一路径的 source_key 稳定",
           dr.source_key(tmp) == dr.source_key(tmp), dr.source_key(tmp))
        ok("source_key 不含路径分隔符",
           "/" not in dr.source_key(tmp) and "\\" not in dr.source_key(tmp),
           dr.source_key(tmp))
        raw = dr.source_key(Path('weird:name*?.png'))
        ok("source_key 洗掉文件名非法字符",
           not any(ch in raw for ch in '\\/:*?"<>|'), raw)
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
