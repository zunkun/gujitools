# -*- coding: utf-8 -*-
"""文件与目录相关的通用工具：哈希、自然排序、阶段输出清单、预览缓存键。"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
from pathlib import Path

from utils.file_utils import replace_with_retry
from utils.sort_utils import natural_sort_key

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def reveal_in_explorer(path) -> bool:
    """在 Windows 资源管理器里打开 ``path`` 的位置（2026-10-11 用户需求）。

    - ``path`` 是**文件**：打开它所在目录并**选中**该文件（``explorer /select,``）；
    - ``path`` 是**目录**：直接打开这个目录。

    返回是否真的发起了打开——路径不存在时为 ``False``，调用方不必再判存在性。
    """
    target = Path(path)
    if not target.exists():
        return False
    if target.is_dir():
        os.startfile(str(target))  # type: ignore[attr-defined]
    else:
        # ⚠️ "/select," 与路径必须是**两个参数**：合成一个参数会被当成
        #    名为 "/select,<file>" 的文件名，资源管理器只弹"找不到"。
        #    路径先 normpath 成反斜杠形态——explorer 对正斜杠的 /select
        #    支持不稳（实测会打开库视图而不是定位文件）。
        subprocess.Popen(
            ["explorer", "/select,", os.path.normpath(str(target))]
        )
    return True


def reveal_dir(path) -> bool:
    """导出收尾用：把 ``path`` **当目录**打开（不存在/不是目录都不弹）。

    ⚠️ 与 :func:`reveal_in_explorer` 的差别只有一个"不存在就不弹"：
    那个是"用户在界面上主动点某个已知文件/目录"，找不到就该当场报错；这个跑在
    **导出完成回调**里，路径由本次导出刚刚算出（可能是 worker 线程回传的
    统计值），不给用户弹一个"找不到"的失败框——导出明明成功了。

    用户 2026-10-16：「导出成功后，打开相应的目录」。
    """
    target = Path(path)
    if not target.is_dir():
        return False
    os.startfile(str(target))  # type: ignore[attr-defined]
    return True


# 页缩略图（thumbnails/source 等）的最长边；256px 保证 area=1 半幅裁剪后仍清晰
THUMBNAIL_EDGE = 256

#: 「这个缩略图目录**正有人在填**」的在场标记文件名。
#:
#: 生产方：导入后台任务（``source_thumbnails_worker``）渲染期间写、结束即删；
#: 消费方：PDF 查看器（``pdf_viewer._cache_is_being_filled``）见到它就不自己
#: 补渲，只读 + 每秒回扫。**没有它两边会各渲一遍整本**——一本 28 页的 JPX
#: 扫描件就是 56 次 ~850ms 的解码（用户 2026-10-21 报"缩略图老半天不齐"）。
PRODUCING_MARKER = ".producing"


def set_producing_marker(directory, on: bool) -> None:
    """写/删「这个目录正有人在填」的在场标记（**永不抛**）。

    调用方：导入任务在**提交后台活之前**先立标记（主线程里几微秒，抢在
    查看器 ``set_pdf`` 之前），后台 worker 收尾时撤掉；worker 自己渲染期间
    也会重复立一次（幂等，防"提交了但 worker 还没跑到"的窗口）。
    """
    target = Path(directory)
    marker = target / PRODUCING_MARKER
    try:
        if on:
            target.mkdir(parents=True, exist_ok=True)
            marker.write_bytes(b"1")
        elif marker.exists():
            marker.unlink()
    except OSError:
        pass  # 标记只是协作信号，读写失败不影响正事


#: 「提取图片」产物在任务目录里的相对位置（与 ``ports.STAGE_LOCATIONS`` 的
#: ``stages/extract`` 一致；这里不 import ports 是为了保持本模块零依赖）。
EXTRACT_PAGES_REL = ("stages", "extract")


def task_extract_pages_dir(pdf_path) -> Path | None:
    """任务目录里**已提取的整页图**目录；不是任务目录里的 PDF 就返回 None。

    ⚠️ 为什么需要（2026-10-21）：生成 256px 缩略图最贵的不是"输出小"，而是
    **解一页内嵌的 JPX**（4285×5736 实测 ~850ms）；而"提取图片"的产物是一张
    2067×2767 的 **JPEG**，从它缩 256px 只要 **21ms**（JPEG 能在 DCT 域降采样）。
    所以**已提取的页**再也不用回 PDF 渲——省掉 40 倍。

    判据只认"PDF 就在任务目录里"（导入后任务目录存的是源文件副本）：
    拿用户原始下载文件时同级没有 ``stages/``，自然返回 None，行为不变。
    """
    path = Path(str(pdf_path or ""))
    if path.suffix.lower() != ".pdf":
        return None
    candidate = path.parent.joinpath(*EXTRACT_PAGES_REL)
    return candidate if candidate.is_dir() else None


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


#: 独立任务页「导出YOLO标注」的记忆文件名（记上次填的名称与导出目录）。
SINGLETASK_YOLO_EXPORT_NAME = "yolo_export.json"


def singletask_yolo_export_path(subtask: str) -> Path:
    """独立任务页「导出YOLO标注」的记忆文件。

    用户 2026-10-16：「导出目录，和前缀都要保存下来，跟任务绑定」——任务流程
    那一侧记在 ``tasks/<id>/ui.json``（见 ``desktop.store.ui_state``），独立
    任务这一侧按**子任务**记一份（名称 + 目录两个键），即
    ``~/Documents/guji/singletask/<子任务>/yolo_export.json``。

    ⚠️ 按子任务记（而不是"每次导出"）：同一批图常要分几次导成不同前缀
    （b1 / b2…）汇进同一个数据集根，每次都重填纯属折腾。
    """
    return singletask_dir(subtask) / SINGLETASK_YOLO_EXPORT_NAME


#: **程序更新**产物目录名（相对 :func:`guji_data_dir`）：应用内下载的安装包落点。
#:
#: 为什么落在**用户数据目录**而不是安装目录（用户 2026-10-16 要求"软件内下载、
#: 别让用户自己下"）：安装目录（``{localappdata}\Programs\guji``）随时会被安装
#: 器覆盖，安装包放那儿会在升级时被一起删掉；数据目录是用户自己的、可写、跨升级
#: 保留，于是"点了稍后"下次还能直接用（见 ``pending_install_file``）。
UPDATES_DIRNAME = "updates"


def updates_dir() -> Path:
    """程序更新目录：``~/Documents/guji/updates``（安装包与"待安装"记录）。"""
    return guji_data_dir() / UPDATES_DIRNAME


def pending_install_file() -> Path:
    """「下好但还没装」的安装包记录：``updates/pending.json``。

    内容形如 ``{"tag": "v2.0.5", "path": …, "name": …, "sha256": …, "size": …}``。
    下次点「检查更新」时若 tag 一致且文件还在，就直接给「立即重启安装」，不必重下。
    """
    return updates_dir() / "pending.json"


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


def page_thumbs_dir(subtask: str) -> Path:
    """独立拼图页的**页面效果缩略图实体**目录：``singletask/<子任务>/page_thumbs/``。

    与 :func:`image_thumbs_dir`（页内**单张源图**的缩略图）各归各：这里放
    按版面合成的**整页**实体——``page1.jpg`` 从第一页起数，映射数据（页号
    ↔ 文件 ↔ 内容签名）在同目录 ``index.json``（用户 2026-10-09：「缩略图
    实体其实没有生成落地……组合成拼版图片应该另外放在一个目录中，直接
    按照 page1 page2 命名，注意做好映射数据」）。任务流程那边写
    ``tasks/<id>/thumbnails/imposition_pages/``，两边不共用（2026-10-04
    「singletask 和 taskdetail 不是一回事」）。
    """
    return singletask_dir(subtask) / "page_thumbs"


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
        # ``_MEIPASS`` 是 PyInstaller 运行时注入的临时解包目录，类型存根里没有，
        # 故走 getattr（缺省空串：只在 frozen 分支取用，那里它一定存在）。
        return Path(getattr(sys, "_MEIPASS", "")) / "desktop"
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


def list_stage_images(directory: Path) -> list[Path]:
    """某阶段输出目录中的图片（按页序自然排序，唯一排序键
    ``utils.sort_utils.natural_sort_key``；原这里的 ``natural_key`` 是
    重复实现，2026-10-11 收口）。"""
    if not directory.exists():
        return []
    return sorted(
        (f for f in directory.iterdir() if f.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda f: natural_sort_key(f.name),
    )


def image_files_fingerprint(directory: Path) -> dict[str, tuple[int, int]] | None:
    """目录里**每张图片**的 ``{绝对路径: (字节数, mtime_ns)}``；读不到目录返回 ``None``。

    回答的是"**哪几张**图片被更新了"。目录级聚合（:func:`dir_content_signature`）
    只能说"这个目录里有没有东西变了"，说不清是哪几张——而要**按页**失效旧版面
    （``print.json`` 的逐图 rect）与旧缩略图缓存，就必须精确到文件（用户
    2026-10-18：「上一步更新了哪些图片要有记录」）。

    ⚠️ 只 ``scandir`` + ``stat``，**不解码**任何图片（第四步取图目录可能几百页）。
    ⚠️ 只看**图片后缀**：拼版合成落盘时会先写 ``.part`` 临时文件再原子改名，
    把它算进来会让指纹在合成过程中抖动。
    """
    try:
        with os.scandir(directory) as scan:
            names = [
                entry.name for entry in scan
                if Path(entry.name).suffix.lower() in IMAGE_SUFFIXES
            ]
    except OSError:
        return None
    out: dict[str, tuple[int, int]] = {}
    for name in names:
        path = directory / name
        try:
            info = os.stat(path)
        except OSError:
            continue  # 竞态（正在被覆盖/删除）：跳过这一条，别让整次判定失败
        out[str(path)] = (info.st_size, info.st_mtime_ns)
    return out


def changed_images(
    before: dict[str, tuple[int, int]] | None,
    after: dict[str, tuple[int, int]] | None,
) -> list[str]:
    """两次逐文件指纹之间**内容变了 / 新增**的图片路径（升序）。

    - ``after`` 读不到（目录被删/权限）→ 空表：无从判断，宁可不动；
    - ``before`` 为 ``None``（**第一次见到这个目录**，没有基线）→ 空表：没有
      可比的对象，第一次见面不能算"上一步更新了它"（否则一进任务就会把整目录
      报成"刚更新"，日志与缓存失效都会误伤）。

    ⚠️ **不看 mtime 单值、看 (大小, mtime) 整对**：重合成会把整批成品重写一遍
    （mtime 全变），只有内容真的换了的那些页才是用户要清缓存的对象——大小变了
    必然在列；大小没变而 mtime 变了（同尺寸重编码）也算更新（保守，清缓存无害）。
    """
    if after is None or before is None:
        return []
    return sorted(
        path for path, fingerprint in after.items()
        if before.get(path) != fingerprint
    )


def dir_content_signature(directory: Path) -> tuple[int, int, int] | None:
    """目录里**图片文件**的目录级**内容指纹**：``(文件数, mtime 纳秒之和, 总字节)``。

    回答的是"这批产物的**内容**变了没有"，**不是**"目录换没换"（那是路径字符串
    的活儿）。下游步骤要刷新的判据里，两者都要：上游产物经常被**同名覆盖**——
    拼版成品重合成（``stages/imposition/NNNN.png`` 重新写一遍）、单页重提取、
    编辑器回写源图——路径一个字都没变，只有内容换了。只比路径，第四步的待打印
    列表就会一直停在旧图上（用户 2026-10-18：「图片拼版图片发生变化，PDF排版不能
    实时更新」）。

    取 mtime **之和**而不是最大值：任何一个文件被重写都会改变和（最大值会被
    "本来就是最新的那个"吃掉）。冲突概率极低（要两个文件同时改写且大小也在
    和里抵消）。

    ⚠️ **"哪几张变了"要问 :func:`image_files_fingerprint`**，这个聚合指纹只够
    判断"要不要重刷"。目录不存在 / 读不了返回 ``None``（调用方按"没有内容"处理，
    与空目录互相区分：后者是 ``(0, 0, 0)``）。
    """
    files = image_files_fingerprint(directory)
    if files is None:
        return None
    return (
        len(files),
        sum(fingerprint[1] for fingerprint in files.values()),
        sum(fingerprint[0] for fingerprint in files.values()),
    )
