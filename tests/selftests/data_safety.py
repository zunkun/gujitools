# -*- coding: utf-8 -*-
"""数据安全：不许越界删、不许半截文件顶替完整文件（2026-09-26 审计）。

覆盖：

1. `task_dir` 会把 `task_id` 直接拼进路径，而 `delete_task` 对它 `rmtree` ——
   `tasks.json` 可被外部编辑，`"id": "..\\..\\x"` 就会**越界删除任务目录之外的东西**。
2. `create_task` 原来"先查后建"取号：开发版与安装版共用数据目录（单例守卫按构建
   目录判定），两个进程会算出同一个号 → 同号互相覆盖。改成靠目录创建的原子性取号。
3. 缩略图缓存与 extract 快路径原来是**非原子写**，而缓存可用性判据是 `mtime`
   → 截断文件的 mtime 更新，会被**永久**当成有效缓存、不自愈。
4. 第四步的版面 `rect_changed` 只在松手时发 → 「拖住不放直接关窗口」丢掉这次改动。
5. `functions/init.py` 原本在库层 `sys.exit(1)`、模板损坏时不捕获、写配置非原子。
"""

NAME = "data_safety"
DEPENDS: list[str] = []
TITLE = "数据安全（越界/半截文件）"


def run(ctx) -> None:
    import os
    from pathlib import Path

    from tests.selftests._context import ok

    repo = Path(__file__).resolve().parents[2]

    def code_of(rel: str) -> str:
        raw = (repo / rel).read_text(encoding="utf-8")
        return "\n".join(line.split("#", 1)[0] for line in raw.splitlines())

    # ---- 1. 任务号形状校验（防越界删除）----
    from desktop.store import TaskStore

    store = TaskStore(ctx.tmp / "data_safety")
    for bad in ("../evil", "..\\evil", "", "abc", "0001/../..", "٠٠٠١", 1, None):
        try:
            store.task_dir(bad)
        except ValueError:
            ok(f"task_dir 拒绝非法任务号 {bad!r}", True)
        except Exception as exc:  # noqa: BLE001
            ok(f"task_dir 拒绝非法任务号 {bad!r}", False, f"{type(exc).__name__}: {exc}")
        else:
            ok(f"task_dir 拒绝非法任务号 {bad!r}", False, "放行了")
    ok("task_dir 正常任务号照旧可用", store.task_dir("0007").name == "0007")

    # 越界删除的最终防线：delete_task 遇到被篡改的 id 必须拒绝、且不碰外面
    outside = ctx.tmp / "data_safety_outside"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "keep.txt").write_text("别删我", encoding="utf-8")
    try:
        store.delete_task("../../data_safety_outside")
    except ValueError:
        refused = True
    except Exception:  # noqa: BLE001
        refused = True
    else:
        refused = False
    ok("delete_task 拒绝被篡改的任务号（不越界删）", refused)
    ok("越界目标里的文件毫发无损", (outside / "keep.txt").is_file())

    # ---- 2. 取号靠目录创建的原子性（已占用的号要顺延）----
    first = store.create_task(Path("a.pdf"), "hash-a", "书A")
    ok("首次建任务拿到 0001", first == "0001", first)
    # 手工占掉下一个号的目录（模拟"另一个进程刚抢到"）
    store.task_dir("0002").mkdir(parents=True, exist_ok=True)
    second = store.create_task(Path("b.pdf"), "hash-b", "书B")
    ok("已占用的号会被跳过（不会同号互相覆盖）", second == "0003", second)
    ok("跳号后两个任务的目录都在",
       store.task_dir("0001").is_dir() and store.task_dir("0003").is_dir())

    # ---- 3. write_bytes_atomic：不留半截、不留 .part ----
    from utils.file_utils import write_bytes_atomic

    target = ctx.tmp / "data_safety" / "atomic.bin"
    payload = os.urandom(4096)
    write_bytes_atomic(target, payload)
    ok("原子写内容正确", target.read_bytes() == payload)
    ok("原子写不留 .part 残留",
       not list(target.parent.glob("*.part")), str(list(target.parent.glob("*.part"))))
    # 目标目录不可写（用"父目录是个文件"来稳定触发失败）→ 必须抛且不留垃圾
    broken_parent = ctx.tmp / "data_safety" / "not_a_dir"
    broken_parent.write_text("x", encoding="utf-8")
    try:
        write_bytes_atomic(broken_parent / "x.bin", b"data")
    except OSError:
        ok("原子写失败时抛错（不静默）", True)
    except Exception as exc:  # noqa: BLE001
        ok("原子写失败时抛错（不静默）", False, f"{type(exc).__name__}: {exc}")
    else:
        ok("原子写失败时抛错（不静默）", False, "居然成功了")

    # ---- 4. 截断的历史缓存要能自愈（min-size 判据）----
    import fitz

    from desktop.workers.source_thumbnails_worker import (
        MIN_THUMB_BYTES, SourceThumbnailsWorker,
    )

    pdf = ctx.tmp / "data_safety" / "book.pdf"
    doc = fitz.open()
    for _ in range(2):
        doc.new_page()
    doc.save(str(pdf))
    doc.close()

    out_dir = ctx.tmp / "data_safety" / "thumbs"
    out_dir.mkdir(parents=True, exist_ok=True)
    worker = SourceThumbnailsWorker(pdf, out_dir)
    worker._pdf_mtime = pdf.stat().st_mtime - 10  # 让"缓存比源新"成立
    truncated = out_dir / "0001.jpg"
    truncated.write_bytes(b"truncated")  # 远小于 MIN_THUMB_BYTES，mtime 是现在
    ok("截断缓存体积确实小于下界", truncated.stat().st_size < MIN_THUMB_BYTES)
    document = fitz.open(str(pdf))
    try:
        spent = worker._render_page(document, 0)
    finally:
        document.close()
    ok("截断的历史缓存被判定为无效并重渲（自愈）", spent > 0, f"耗时={spent}")
    ok("重渲后缓存体积正常", truncated.stat().st_size >= MIN_THUMB_BYTES,
       str(truncated.stat().st_size))
    ok("重渲不留 .part", not list(out_dir.glob("*.part")))

    # ---- 5. 回归形态 ----
    canvas = code_of("desktop/components/viewers/print_layout_canvas.py")
    ok("版面画布提供 flush_pending（补发未松手的拖动）", "def flush_pending(self)" in canvas)
    page = code_of("desktop/pages/taskdetail/page.py")
    ok("关窗口前补发未提交的版面改动", "flush_layout_pending()" in page)
    ok("切步骤前也补发", "self.flush_layout_pending()" in page)
    init_code = code_of("functions/init.py")
    ok("init 不在库层 sys.exit", "sys.exit" not in init_code)
    ok("init 的模板缺失/损坏会抛异常（不是打印后退出）",
       "模板文件未找到" in init_code and "模板文件无法解析" in init_code)
    ok("init 写配置是原子的（不留半截覆盖用户配置）",
       "replace_with_retry(tmp, target)" in init_code)
    extract = code_of("utils/pdf_extract.py")
    ok("extract 快路径的图片落盘改成原子写",
       "write_bytes_atomic(img_path" in extract)
    thumbs = code_of("desktop/workers/source_thumbnails_worker.py")
    ok("缩略图落盘改成原子写", "write_bytes_atomic(target, data)" in thumbs)
    preview = code_of("desktop/workers/preview_worker.py")
    ok("预览缓存落盘改成原子写", "write_bytes_atomic(cache_file, data)" in preview)
    tasks = code_of("desktop/store/tasks.py")
    ok("取号改为 mkdir(exist_ok=False) 原子占号 + 抢不到就顺延",
       "mkdir(parents=True, exist_ok=False)" in tasks and "except FileExistsError" in tasks,
       "找不到原子占号")
