# -*- coding: utf-8 -*-
"""文件与目录相关的通用工具：哈希、自然排序、阶段输出清单、预览缓存键。"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import threading
from pathlib import Path

from utils.file_utils import replace_with_retry

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

# 页缩略图（thumbnails/source 等）的最长边；256px 保证 area=1 半幅裁剪后仍清晰
THUMBNAIL_EDGE = 256


def guji_data_dir() -> Path:
    """GUI 数据根目录：用户文档目录下的 guji。"""
    return Path.home() / "Documents" / "guji"


#: **独立任务**数据区的目录名（相对 :func:`guji_data_dir`）。
#:
#: 用户 2026-10-03：
#:
#: > 这个缩略图也可以放在 ~/Documents/guji/singletask 下面，
#: > singletask 是独立任务，下面有各种子任务
#:
#: 与任务流程那套 ``tasks/<id>/`` 是**两个世界**：那边一个 id = 一本完整的书、
#: 带四步流程与 runs/boxes/草稿；这边是左侧导航里那**几个独立功能页**（图片提取 /
#: 去底色 / 生成 PDF / 拼图），每个子任务自己一个目录、只放自己的缓存与中间物。
SINGLETASK_DIRNAME = "singletask"

#: 子任务目录名里不能出现的字符（Windows 文件名限制），换成一横线。
_SAFE_CHARS = '<>:"/\\|?*'


def safe_dirname(name: str) -> str:
    """把任意标题洗成能当目录名的一串（去掉非法字符、收敛空白）。"""
    text = "".join("-" if ch in _SAFE_CHARS else ch for ch in str(name)).strip()
    text = "".join(ch for ch in text if ord(ch) >= 32).strip(" .")
    return text or "untitled"


def singletask_dir(subtask: str) -> Path:
    """独立任务区下某个**子任务**的目录：``~/Documents/guji/singletask/<子任务>``。"""
    return guji_data_dir() / SINGLETASK_DIRNAME / safe_dirname(subtask)


#: 子任务目录名改名时的**旧名 → 新名**映射（2026-10-03 换``disk_key``）。
#:
#: 目录名以前取的是 spec 的中文标题，于是它跟着文案变；而里面躺着用户攒下的
#: 缩略图缓存与**手改过的版面图**（``拼图/edited/``）。文案一改，这些目录就成了
#: 没人再去找的孤儿——现象是"我明明改过版面，重新打开又变回原样"。
#:
#: 现在目录名取 :meth:`StepSpec.disk_key`（步骤路由键，不随文案动）。这条表负责
#: 把已经存在的老目录**搬**过去。⚠️ 它是一次性迁移，不是长期兼容层：新老并存时
#: **以新目录为准**（旧目录留着不删，用户确认没用了自己清）。
_LEGACY_SUBTASK_DIRS: dict[str, str] = {
    "图片提取": "extract",
    "检测文本框": "detect",
    "去底色": "rembg",
    "拼图": "imposition",
    "生成 PDF": "print",
}


def migrate_legacy_singletask_dirs() -> list[str]:
    """把按旧标题建的 ``singletask/<中文名>/`` 搬到新名（见 ``_LEGACY_SUBTASK_DIRS``）。

    **幂等**：目标已存在就跳过（只当新目录存在的老数据，不会来回搬）；旧目录
    **不删**——里面可能有用户还在意的东西，误删不可恢复。

    返回实际搬动过的目录名（给自测与日志用）。
    """
    base = guji_data_dir() / SINGLETASK_DIRNAME
    moved: list[str] = []
    for old_name, new_name in _LEGACY_SUBTASK_DIRS.items():
        old_dir = base / safe_dirname(old_name)
        if not old_dir.is_dir():
            continue
        new_dir = base / safe_dirname(new_name)
        if new_dir.exists():
            continue  # 已有新目录（先前搬过/ 或新目录自己有了内容）⇒ 不碰
        try:
            old_dir.rename(new_dir)
        except OSError:
            continue  # 占用/权限/跨卷——留在原地，下次启动再试，绝不半途删
        moved.append(f"{old_name} → {new_name}")
    return moved


def migrate_extract_thumbs_to_numbered(subtask: str = "extract") -> list[str]:
    """一次性迁移：extract 的缩略图改成「序号口径、只留一份」（2026-10-04）。

    用户原话：「我不需要太多缩略图，只保留一份就可以……既然最后是按照序号
    提取的，那么就按照序号处理」。

    改之前一个子任务目录下有**两套**缩略图（同一个页面被渲了两遍、存了两份）：

    1. ``thumbnails/<书>/0001.jpg``——PDF 页渲染（未提取时左栏显示）；
    2. ``thumbs/256/<图键>.jpg``——按提取产物重渲（提取后左栏显示）。

    实测同页两者像素差 < 12/255（内容基本一致），所以第 2 套是纯冗余。

    迁移做两件事：

    - 把 ``thumbnails/<书>/NNNN.jpg`` **挪进** ``thumbnails/<书>/<边长>/``，
      文件名不变（序号口径本来就是这个名）——挪的是**目录位置**不是内容，
      命中判据（``cache_usable`` 比 mtime）原样成立，不用重渲；
    - 删掉 ``thumbs/`` 整棵（它只服务第 2 套；⚠️ 只删 ``<子任务>/thumbs``，
      不碰别的子任务目录）。

    **幂等**：目标已存在就跳过、不覆盖；删 ``thumbs/`` 前先确认里面没有别的
    子目录。⚠️ 全程 ``try/except OSError``：占用/权限/跨卷一律**留着不动**，
    下次启动再试——缓存丢了能重渲，删错了没法恢复。
    """
    base = singletask_dir(subtask)
    notes: list[str] = []
    thumbs_root = base / "thumbs"
    book_root = base / "thumbnails"

    # ---- 1. 平铺的 NNNN.jpg 挪进 <边长>/ ----
    if book_root.is_dir():
        for book_dir in sorted(p for p in book_root.iterdir() if p.is_dir()):
            # 已经是分层目录（迁移过了）或就是边长目录 ⇒ 不动
            flat = sorted(book_dir.glob("[0-9][0-9][0-9][0-9].jpg"))
            if not flat:
                continue
            target_dir = book_dir / str(int(THUMBNAIL_EDGE))
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                continue
            for src in flat:
                dst = target_dir / src.name
                if dst.exists():
                    continue  # 迁移过的：目标在位，绝不覆盖
                try:
                    src.rename(dst)
                except OSError:
                    continue  # 占用/跨卷：留在原地，下次再试
            notes.append(f"{book_dir.name}: 平铺页缩略图 → {target_dir.name}/")

    # ---- 2. 删掉 thumbs/（第 2 套，纯冗余）----
    if thumbs_root.is_dir():
        try:
            # 只在它确实是「缩略图缓存目录」时才删：里面有非数字子目录就放弃
            entries = list(thumbs_root.iterdir())
            suspicious = [
                p.name for p in entries
                if p.is_dir() and not p.name.isdigit()
            ]
            if suspicious:
                notes.append(f"thumbs/ 非纯缓存，跳过删除：{suspicious}")
            else:
                shutil.rmtree(thumbs_root)
                notes.append("thumbs/ 已删除（与页缩略图重复）")
        except OSError:
            notes.append("thumbs/ 删除失败（占用/权限），保留")
    return notes


def singletask_thumbnails_dir(subtask: str, book: str | Path | None = None) -> Path:
    """子任务的**页缩略图缓存**：``singletask/<子任务>/thumbnails[/<书>]``。

    导入 PDF 时**立刻**渲染到这里（用户 2026-10-03："从上一层导入PDF，没有立即
    提取缩略图"）。命中即复用，缺页才渲染——所以第二次打开同一本书几乎不花时间。

    ⚠️⚠️ **必须带 ``book`` 分一层目录**（2026-10-03 自测当场逮到）：缩略图文件名是
    **页号**（``0001.jpg``…），而这个缓存目录是**所有书共用**的。不按书分开，A 书
    第 1 页的缩略图会被当成 B 书第 1 页的命中缓存 ⇒ 翻页翻出**别本书的内容**。
    （任务流程那边没事，是因为 ``tasks/<id>/thumbnails/source`` 一本书一个目录。）

    目录名用 ``书名-大小-路径指纹前 8 位``：同名不同书靠指纹区分，同一本书改名后
    仍能命中旧缓存。

    ⚠️ **只放缓存，不放产物**：模块页的输出目录仍然默认在源文件旁边
    （:meth:`desktop.steps.spec.StepSpec.default_output`），别把用户已经习惯的
    产物位置改掉。
    """
    base = singletask_dir(subtask) / "thumbnails"
    if book is None:
        return base
    return base / safe_dirname(book_key(book))


def book_key(book: str | Path) -> str:
    """一本书在缓存目录里的唯一名字：``<文件名去后缀>-<大小>-<路径指纹前8位>``。

    路径参与指纹：``D:/书/甲.pdf`` 与 ``E:/书/甲.pdf`` 同名同大小，但不是同一本书。
    """
    path = Path(book)
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8", "replace")).hexdigest()
    return f"{path.stem}-{size}-{digest[:8]}"


def image_thumb_cache_path(
    subtask: str, image: str | Path, edge: int = THUMBNAIL_EDGE,
) -> Path:
    """一张**源图片**在 singletask 缓存里的缩略图路径。

    ``singletask/<子任务>/thumbs/<边缘边长>/<book_key>.jpg``

    用户 2026-10-03 定的口径：**所有独立任务的左侧都显示缩略图**，且缩略图
    统一缓存在 ``~/Documents/guji/singletask`` 下（PDF 用
    :func:`singletask_thumbnails_dir` 的按页编号那套，这里是按图文件本身）。

    - **按图分文件**（不是按页号）：图片源的条目名五花八门（``1.jpg`` /
      ``右-01.png``…），按页号命名必然撞名，撞名就是**别人的图被当成本图的
      缓存**——与 PDF 那条护栏（``book_key`` 分目录）是同一个坑。
    - **按边长分层**：``ThumbStrip.decode_edge`` 会随 dpr 变，1.5 倍屏要
      234px、小图要 156px。混在一个目录里，改一次 dpr 就会拿旧尺寸的缓存
      当命中（条目里发糊），所以边长进目录名。
    - 键里带**大小与路径指纹**（复用 :func:`book_key`）：同名不同图靠它区分，
      同图改名后仍能命中旧缓存。
    """
    return image_thumbs_dir(subtask, edge) / f"{safe_dirname(book_key(image))}.jpg"


def image_thumbs_dir(subtask: str, edge: int = THUMBNAIL_EDGE) -> Path:
    """一批**图片源**的缩略图缓存**目录**：``singletask/<子任务>/thumbs/<边长>``。

    与 :func:`image_thumb_cache_path` 是同一套规则的两种用法：那个给**单张图**
    的缓存文件路径，这个给**目录**（一批图共用、或宿主需要"重渲一张"时交给
    ``ImageThumbCacheWorker``）。

    ⚠️ 目录**只按「子任务 + 边长」分层**，不按单图键：单图键里带着大小与路径
    指纹，拿它当目录名既很长，也会让"同一张图被编辑后尺寸变了"直接换目录
    （旧缓存全成孤儿）。⚠️ 边长必须进目录名（``decode_edge`` 随 dpr 变）。
    """
    return singletask_dir(subtask) / "thumbs" / str(int(edge))


# ---------------------------------------------------------------- 序号口径的缩略图
#
# 用户 2026-10-04：「我不需要太多缩略图，只保留一份就可以，一切以最终标准处理，
# 既然最后是按照序号提取的，那么就按照序号处理；如果没有提取之前，可以写一个
# 映射图，原始名称跟序号的映射不就行了」。
#
# 事实基础（``utils/pdf_extract.py`` 的两处落盘，``:254`` 与 ``:317``）：
# **提取产物的文件名就是 ``f"{page_idx + 1}.{ext}"``**——序号 N 恒等于 PDF 的
# 第 N 页，唯一例外是**失败页留空号**（失败页不产出文件，见 ``_report_batch``）。
# 于是「原始名称 ↔ 序号」是恒等映射，不必真去生成一张对照表；真正需要记下来的
# 只有「哪些序号**没**产出」，那才是映射表里唯一有信息量的部分。
#
# ⚠️ **这为什么能砍掉第二份缓存**：此前 extract 一个子任务目录下有两套缩略图：
# ``thumbnails/<书>/NNNN.jpg``（PDF 整页渲染）与 ``thumbs/256/<图键>.jpg``
# （按提取产物重渲）。实测同页两者像素差 < 12/255（内容基本一致），因为这批书
# 每页恰好一张内嵌整页图。统一到序号口径后，同一页**只落一个文件**：
# 未提取时它是「PDF 第 N 页的渲染」，提取后按产物重渲**覆盖同一个文件**。


def extract_thumbs_dir(
    subtask: str, book: str | Path, edge: int = THUMBNAIL_EDGE,
) -> Path:
    """某个子任务下**一本书**的序号口径缩略图目录。

    ``singletask/<子任务>/thumbnails/<书>/<边长>/``

    ⚠️ 仍然**必须带 ``book`` 分一层**（与 :func:`singletask_thumbnails_dir`
    同一条护栏）：文件名是**序号**，A 书第 1 页与 B 书第 1 页会撞名 ⇒ 翻出
    别本书的内容。
    """
    return (
        singletask_thumbnails_dir(subtask, book) / str(int(edge))
    )


def extract_thumb_path(
    subtask: str, book: str | Path, seq: int, edge: int = THUMBNAIL_EDGE,
) -> Path:
    """第 ``seq`` 页（1 起始）的缩略图路径：``<序号4位补零>.jpg``。

    ⚠️ 四位补零不是装饰，是**排序键**：``1.jpg`` 排在 ``10.jpg`` 前面，
    缩略图条的顺序必须与产物序号一致（``collect_result_images`` 用自然排序）。
    """
    return extract_thumbs_dir(subtask, book, edge) / f"{int(seq):04d}.jpg"


def thumb_map_path(subtask: str, book: str | Path) -> Path:
    """序号 ↔ 产物的映射表：``singletask/<子任务>/thumbnails/<书>/map.json``。

    记录 ``{"book":…, "pages": N, "seqs": [1,2,…]}``——``seqs`` 是**真实产出
    的序号**（失败页不在其中）。它是缩略图与产物之间的唯一权威对照：左栏条目
    按它与缓存文件对齐，缺号的地方不会出现"有缩略图却没产物"的幽灵条目。
    """
    return singletask_thumbnails_dir(subtask, book) / "map.json"


def default_open_dir() -> Path:
    """文件对话框的默认打开目录：用户文档目录。

    QFileDialog 传空串会回退到进程工作目录（打包后就是程序所在目录），
    入口落在安装/项目目录很不合适；统一改从文档目录起步。目录不存在时
    回退到用户主目录，再不行返回空 Path 由调用方保持空串行为。
    """
    documents = Path.home() / "Documents"
    if documents.is_dir():
        return documents
    return Path.home() if Path.home().is_dir() else Path()


def project_root() -> Path:
    """项目根目录（`desktop` 包的上一级）。

    源码模式下 worker 子进程用 `-m desktop.worker` 启动，工作目录必须是
    能解析出 `desktop` 包的那一级；用本函数取，避免依赖某个文件的层数
    （文件挪一层就会算错）。
    """
    return Path(__file__).resolve().parents[2]


def package_dir() -> Path:
    """`desktop` 包目录（源码与 PyInstaller 打包两种模式下都可用）。

    打包后 `desktop` 作为 PYZ 内的字节码存档存在，磁盘上没有真正的
    ``desktop/static/icon.png``；数据文件由 spec 的 ``datas`` 额外落到
    ``_internal/desktop/``，因此 frozen 下直接指向 ``sys._MEIPASS``。
    """
    import sys

    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "desktop"
    return Path(__file__).resolve().parents[1]


def file_hash(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """流式计算文件 SHA-256（分块读取，避免大 PDF 撑爆内存）。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def copy_file_atomic(source: Path, target: Path) -> Path:
    """把 source 复制到 target，**要么没有、要么完整**。

    ⚠️ 不能用裸 ``shutil.copy2(source, target)``：导入后的复制是在**后台
    线程**里跑的，而详情页/PDF 预览随时会来看任务目录里的副本。直接往
    target 写，复制途中它就 ``is_file() == True`` 了，读到的却是半截
    PDF——渲染失败、甚至静默出一张残缺页。

    所以先写同目录的临时文件，落盘后再 ``os.replace`` 原子改名。临时名带
    .part 后缀，``glob("*.pdf")`` 之类的兜底查找也扫不到它。

    ⚠️ 临时名里要带 **pid + 线程号**：同一个副本可能被两个地方同时复制
    （后台队列复制中，用户已经点进详情页 → ``ensure_source_copy`` 又复制
    一遍）。共用一个临时名的话两边会交叉写同一个文件；各自写自己的临时
    文件则内容相同，谁最后 replace 都对。
    """
    # ⚠️ 临时名 = 原名截断 + pid/tid + .part：NTFS 单个文件名上限 255 字符，
    # 长书名（如《长短经.九卷.唐.赵蕤.撰.南宋时期杭州净戒院刊本…》这类古籍
    # 文件名本身就 100+ 字符）再加 pid/tid 后缀就会超限，copy2 直接报
    # 「系统找不到指定的路径」。把名字部分截到安全长度（pid/tid/part 约
    # 占 40 字符），截断后的前缀 + pid/tid 仍能保证两个并发复制不重名——
    # 同名前缀 + 不同 pid/tid 组合出的临时名彼此不同。
    _stem = target.stem[: 255 - 45 - len(target.suffix)]
    temp = target.with_name(
        f"{_stem}.{os.getpid():x}{threading.get_ident():x}{target.suffix}.part"
    )
    try:
        shutil.copy2(source, temp)
    except OSError:
        # 失败别留下半截临时文件，否则会被当成"下次可复用"
        try:
            temp.unlink()
        except OSError:
            pass
        raise
    replace_with_retry(temp, target)  # Windows 上读者会让 os.replace 抛 PermissionError
    return target


def natural_key(name: str):
    """生成自然排序键：数字段按整数、其余转小写，使 2 排在 10 前。"""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]


def list_stage_images(directory: Path) -> list[Path]:
    """某阶段输出目录中的图片（自然排序）。"""
    if not directory.exists():
        return []
    return sorted(
        (f for f in directory.iterdir() if f.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda f: natural_key(f.name),
    )
