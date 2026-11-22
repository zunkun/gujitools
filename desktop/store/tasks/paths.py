# -*- coding: utf-8 -*-
"""任务目录布局与各类落点：产物目录、预览草稿、缩略图缓存、源文件副本。

从 ``desktop/store/tasks.py`` 拆出（2026-11-22）。落点的唯一事实来源仍是
``desktop.steps.ports``——这里只做路径推导，不读写业务数据。
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from desktop.steps import ports
from desktop.store.json_io import (
    owner_path, read_json, resolve_scoped_path, write_json, write_owner,
)
from desktop.store.tasks.base import TaskMixinBase
from desktop.utils.files import copy_file_atomic
from utils.file_utils import SOURCE_DOCUMENT_EXTS
from utils.rembg_algorithms import ALGORITHM_KEYS, REMBG_DEFAULT_ALGORITHM


class TaskLayoutMixin(TaskMixinBase):
    """任务目录布局、产物落点与缓存目录（路径推导）。"""

    if TYPE_CHECKING:
        # 宿主 TaskStore（或同级 Mixin）提供：只做类型声明，运行时零副作用。
        task_diagram: Callable[[str], Any]
        get_task: Callable[[str], dict | None]
        scoped_file_scope: Callable[[str, str | None], dict[str, str | None]]

    # ---------- 任务目录布局 ----------
    #: 合法任务号的形状：四位以上纯数字（由 `_next_task_no` 生成，如 0007）。
    _TASK_ID_RE = re.compile(r"^[0-9]{4,}$")

    def task_dir(self, task_id: str) -> Path:
        """任务根目录：tasks/<任务号>。

        ⚠️ **必须校验形状**（2026-09-26 审计）：`task_id` 会被直接拼进路径，而
        `delete_task` 对它做 `rmtree`。`tasks.json` 就在用户的文档目录下、可被
        外部编辑或别的工具写坏，一旦出现 `"id": "..\\..\\somewhere"` 就会
        **越界删除任务目录之外的东西**。这里只认 `create_task` 生成的形状。
        """
        if not isinstance(task_id, str) or not self._TASK_ID_RE.match(task_id):
            raise ValueError(
                f"任务号形状非法：{task_id!r}（应为四位以上数字，如 0007）"
            )
        return self.root / "tasks" / task_id

    def stage_dir(self, task_id: str, stage: str) -> Path:
        """某阶段的输出目录：tasks/<任务号>/stages/<阶段>。"""
        return self.task_dir(task_id) / "stages" / stage

    # ---------- 产物落点（由 desktop.steps.ports 派生）----------
    def artifact(self, task_id: str, stage: str, port: str = "pages") -> Path:
        """某阶段某端口的产物绝对路径（**落点的唯一入口**）。

        ⚠️ 这四个 ``*_output_dir`` 方法以前各自写死了路径，是"加一步要改四处"
        的根源；现在它们都转调到这里，而落点表
        （:data:`desktop.steps.ports.STAGE_LOCATIONS`）是唯一事实来源。
        加一步 = 加一行表，不用动 store。
        """
        path = ports.artifact_path(self.task_dir(task_id), stage, port)
        if path is None:
            raise KeyError(f"阶段 {stage!r} 没有登记端口 {port!r} 的落点")
        return path

    def extract_output_dir(self, task_id: str) -> Path:
        """提取图片直接位于 stages/extract（无 PDF 名/嵌套子目录）。"""
        return self.artifact(task_id, "extract", "pages")

    def rembg_output_dir(self, task_id: str) -> Path:
        """步骤三成品图片目录（「执行去底色」产出，print 阶段从此取图）。"""
        return self.artifact(task_id, "rembg", "pages")

    def rembg_preview_dir(self, task_id: str, node_id: str | None = None,
                          primary_id: str | None = None) -> Path:
        """去底色「实时调整」的**草稿目录**（``tasks/<任务号>/preview/rembg[~节点]``）。

        ⚠️ **必须与正式成品目录分开**（用户 2026-11-04）：改参数/切缩略图时的
        实时结果只是"这一步里看到的预览"，用户还没点「执行去底色」——
        - 不能落进 ``stages/rembg``（否则拼版 / 第四步直接把它当正式输入，
          而且会覆盖掉上一轮全量执行的成品）；
        - 不能落进 ``stages/`` 下任何地方（那边的目录一概被当成阶段产物）；
        - 也不能顺手写 ``rembg_methods`` 侧车（``ports.rembg_methods_path``
          只认 ``stages/`` 下的目录，草稿目录天然不命中，正好）。

        草稿在「执行去底色」开始时整体清空（见 ``RembgLiveMixin._drop_live_results``）。
        """
        if node_id:
            items = self.task_diagram(task_id).node_ids_of("rembg")
            primary_id = primary_id or (items[0] if items else None)
        name = ports.scoped_name("rembg", node_id, primary_id)
        return self.task_dir(task_id) / "preview" / name

    def clear_rembg_preview(self, task_id: str, node_id: str | None = None) -> None:
        """清空去底色的实时预览草稿（正式执行开始前调用；失败不抛）。"""
        shutil.rmtree(self.rembg_preview_dir(task_id, node_id), ignore_errors=True)

    def rembg_offsets_path(self, task_id: str, node_id: str | None = None,
                           primary_id: str | None = None) -> Path:
        """**逐张图片**阈值偏移的存储文件（黑名单法，只记非 0 的图片）。

        主节点沿用 ``rembg_offsets.json``；同一步骤的副本节点落
        ``rembg_offsets~<节点>.json``（与 ``boxes`` / ``pages`` 同一套命名）。
        """
        from desktop.steps import ports

        if node_id:
            items = self.task_diagram(task_id).node_ids_of("rembg")
            primary_id = primary_id or (items[0] if items else None)
        name = ports.scoped_name("rembg_offsets.json", node_id, primary_id)
        return resolve_scoped_path(self.task_dir(task_id) / name, node_id)

    def load_rembg_offsets(self, task_id: str, node_id: str | None = None,
                           primary_id: str | None = None) -> dict[str, int]:
        """读逐张偏移表 ``{页名: offset}``（只含非 0 项；坏文件当空表）。"""
        path = self.rembg_offsets_path(task_id, node_id, primary_id)
        data = read_json(path, {})
        if not isinstance(data, dict):
            return {}
        out: dict[str, int] = {}
        for key, value in data.items():
            try:
                offset = int(value)
            except (TypeError, ValueError):
                continue
            if offset:
                out[str(key)] = offset
        return out

    def rembg_offset(self, task_id: str, image_key: str,
                     node_id: str | None = None,
                     primary_id: str | None = None) -> int:
        """某张图片的阈值偏移（没记录过 = 0）。"""
        return int(self.load_rembg_offsets(
            task_id, node_id, primary_id
        ).get(str(image_key), 0))

    def save_rembg_offset(self, task_id: str, image_key: str, offset: int,
                          node_id: str | None = None,
                          primary_id: str | None = None) -> None:
        """记录某张图片的阈值偏移；**offset=0 就删掉这一项**（黑名单法）。

        ⚠️ 只在用户**确实改过**这张图时调用；整表很小，读改写即可，不要为它
        再造缓存。
        """
        path = self.rembg_offsets_path(task_id, node_id, primary_id)
        data = self.load_rembg_offsets(task_id, node_id, primary_id)
        image_key = str(image_key)
        value = int(offset)
        if value:
            data[image_key] = value
        else:
            data.pop(image_key, None)
        if not data:
            try:
                path.unlink(missing_ok=True)
                owner_path(path).unlink(missing_ok=True)
            except OSError:
                pass
            return
        if self.task_dir(task_id).exists():
            write_json(path, data)
            write_owner(path, node_id or primary_id)

    def rembg_algorithms_path(self, task_id: str, node_id: str | None = None,
                              primary_id: str | None = None) -> Path:
        """**逐张图片**去底色算法的存储文件（只记用户单独改过的图片）。

        主节点沿用 ``rembg_algorithms.json``；同一步骤的副本节点落
        ``rembg_algorithms~<节点>.json``（与 ``rembg_offsets`` 同一套命名）。
        """
        from desktop.steps import ports

        if node_id:
            items = self.task_diagram(task_id).node_ids_of("rembg")
            primary_id = primary_id or (items[0] if items else None)
        name = ports.scoped_name("rembg_algorithms.json", node_id, primary_id)
        return resolve_scoped_path(self.task_dir(task_id) / name, node_id)

    def load_rembg_algorithms(self, task_id: str, node_id: str | None = None,
                              primary_id: str | None = None) -> dict[str, str]:
        """读逐张算法表 ``{页名: 算法 key}``；坏文件/未知算法当没记录。"""
        path = self.rembg_algorithms_path(task_id, node_id, primary_id)
        data = read_json(path, {})
        if not isinstance(data, dict):
            return {}
        out: dict[str, str] = {}
        for key, value in data.items():
            algorithm = str(value or "")
            if algorithm in ALGORITHM_KEYS:
                out[str(key)] = algorithm
        return out

    def rembg_algorithm(self, task_id: str, image_key: str,
                        node_id: str | None = None,
                        primary_id: str | None = None) -> str:
        """某张图片单独指定的算法；没记录过 = 默认 Otsu。"""
        return str(self.load_rembg_algorithms(
            task_id, node_id, primary_id
        ).get(str(image_key), REMBG_DEFAULT_ALGORITHM))

    def save_rembg_algorithm(self, task_id: str, image_key: str, algorithm: str,
                             node_id: str | None = None,
                             primary_id: str | None = None) -> None:
        """记录某张图片的算法（用户确实在这张图上改过时才调用）。

        ⚠️ 与 offset 的「黑名单法」不同：这里**连默认值 otsu 也照存**。
        原因是算法没有"0 等价未设置"的哨兵——用户明确把某页设回 otsu 时，
        它必须继续留在表里，不能被后续的全局值覆盖。
        """
        if str(algorithm) not in ALGORITHM_KEYS:
            return
        path = self.rembg_algorithms_path(task_id, node_id, primary_id)
        data = self.load_rembg_algorithms(task_id, node_id, primary_id)
        data[str(image_key)] = str(algorithm)
        if self.task_dir(task_id).exists():
            write_json(path, data)
            write_owner(path, node_id or primary_id)

    def imposition_output_dir(self, task_id: str) -> Path:
        """「图片拼版」产出的成品拼版页图目录（列表顺序即页序）。

        拼版节点**生效**时（选择态为真且有拼版页），第四步「PDF排版」与它的
        待打印列表一律从这里取图；否则仍从 ``rembg_output_dir`` 取。
        """
        return self.artifact(task_id, "imposition", "pages")

    def print_output_pdf(self, task_id: str) -> Path:
        """print 阶段产物 print.pdf 的完整路径。"""
        return self.artifact(task_id, "print", "pdf")

    def stage_output_dir(self, task_id: str, stage: str,
                         node_id: str | None = None) -> Path:
        """返回某阶段（GUI）应写入的输出目录。

        rembg 返回成品图目录、print 返回 print.pdf 所在目录。
        """
        # detect 只检测不落盘，它的产物是坐标文件；若有参考缩略图放
        # thumbnails/detect（那是界面缓存，不是端口产物，故不在 ports 表里）。
        # ⚠️ 按**节点**取（B 方案）：同一步骤的多个「检测文本框」节点各自一份
        #    标注图目录，互不覆盖（用户 2026-10-17：缩略图目录也按节点隔离）。
        if stage == "detect":
            return self.thumbnails_dir(task_id, "detect", node_id)
        return self.stage_dir(task_id, stage)

    def workset_dir(self, task_id: str) -> Path:
        """已废弃：检测/去底直接读 extract 输出目录，不再物化输入副本。

        仅为清理历史遗留目录保留（老版本任务目录下可能仍有 workset/）。
        """
        return self.task_dir(task_id) / "workset"

    def runs_config_dir(self, task_id: str) -> Path:
        """子进程执行配置（run-*.json / detect-config.json）。"""
        return self.task_dir(task_id) / "runs"

    def thumbnails_dir(self, task_id: str, name: str,
                       node_id: str | None = None) -> Path:
        """按**节点作用域**取一个缩略图缓存目录：``thumbnails/<名>[~<节点>]``。

        主节点/无节点 ⇒ ``thumbnails/<名>``（旧路径，**零迁移**）；副本节点 ⇒
        ``thumbnails/<名>~<节点>``。规则由 :func:`desktop.steps.ports.scoped_name`
        唯一给出，与产物落点（``stages/<阶段>~<节点>``）同一套——同一步骤有多个
        节点时各自的缩略图缓存互不覆盖（用户 2026-10-17：「缩略图目录也要
        按节点这样处理」）。
        """
        scope = self.scoped_file_scope(task_id, node_id)
        return (
            self.task_dir(task_id)
            / "thumbnails"
            / ports.scoped_name(name, scope["node_id"], scope["primary_id"])
        )

    def input_thumbnails_dir(self, task_id: str) -> Path:
        """**入口图片**的缩略图缓存：``thumbnails/input/``。

        用户 2026-10-17：流程第一个节点是「检测文本框 / 图片去底色 / 图片拼版 /
        PDF排版」时，它的输入是用户直接放进 ``stages/input/`` 的那批图——此前
        左栏只能现解码原图（几千像素的扫描图）。现在**导入即按图键生成**到这份
        缓存里，左栏直接读小图。

        ⚠️ **不按节点分**：入口图片目录（``stages/input/``）是**整个任务共用**
        的（所有无上游的节点都回落到它），所以缓存也与它同作用域（任务级）。
        """
        return self.task_dir(task_id) / "thumbnails" / "input"

    def entry_thumb_path(self, task_id: str, image: Path | str) -> Path | None:
        """一张入口图片在 :meth:`input_thumbnails_dir` 里的缓存缩略图路径。

        没有缓存、或缓存比源图旧/体积像截断，一律返回 ``None``（调用方回落到
        真图解码）。按**图键**命名（``book_key``：文件名+大小+路径指纹）——入口
        图片名字五花八门，按序号会张冠李戴（与 ``thumb_cache_worker`` 同一规则）。
        """
        from desktop.utils.files import book_key
        from desktop.workers.thumb_cache_worker import cache_usable, stat_mtime

        target = self.input_thumbnails_dir(task_id) / f"{book_key(image)}.jpg"
        if not cache_usable(target, stat_mtime(image)):
            return None
        return target

    def print_manage_thumbnails_dir(self, task_id: str) -> Path:
        """PDF排版「管理图片」弹窗的缩略图缓存：``thumbnails/print_manage/``。

        这一份覆盖**待打印条目 + 已删除条目**（拼版成品、手动插入图、入口图、
        去底色成品都可能进来），按 ``book_key``（图文件路径指纹）命名。弹窗
        打开时只读这些小图，不再同步解码原图（用户 2026-11-02「弹窗打开慢」）。

        ⚠️ 删除图片的小图**不删**：「插入图片 → 删除恢复」还要显示它；哪些
        缩略图"在用"由 ``print.json`` 的 ``pages`` / ``deleted_pages`` 声明
        （就是用户说的"用配置文件表示"）。不按节点分：``print.json`` 本身按节点。
        """
        return self.task_dir(task_id) / "thumbnails" / "print_manage"

    def source_thumbnails_dir(self, task_id: str) -> Path:
        """源 PDF 页缩略图：导入即生成，PDF 预览直接复用，永不清理。

        ⚠️ **不按节点分**：它来自**源 PDF**（一本书一份），同一步骤的多个提取
        节点产出的页图同名同页号，共用这份按页号命名的缓存是正确且省事的。
        """
        return self.task_dir(task_id) / "thumbnails" / "source"

    def rembg_thumbnails_dir(self, task_id: str,
                             node_id: str | None = None) -> Path:
        """第四步缩略图缓存：去底色阶段随成品图一并生成，
        缩略条直接复用，不必每次现解码 6000px 的原图。

        ⚠️ 按**节点**取（B 方案）：两个「图片去底色」节点各有各的成品产物
        （``stages/rembg[~<节点>]``），缩略图缓存也跟着分（裸名 ``print`` /
        ``print~<节点>``），否则副本节点会命中主节点的缩略图（张冠李戴）。
        """
        return self.thumbnails_dir(task_id, "print", node_id)

    def imposition_thumbnails_dir(self, task_id: str,
                                  node_id: str | None = None) -> Path:
        """拼版页左列缩略图缓存（每页取第一张源图，``book_key`` 命名）。

        ⚠️ 与独立拼图页的 ``singletask/imposition/`` **各归各**（用户
        2026-10-04 明确「singletask 和 taskdetail 不是一回事」）：任务缓存
        随任务目录走，``delete_task`` 整体清理时一并清掉；两边只共用组件与
        ``ImageThumbCacheWorker``，**不共用缓存根**。
        """
        return self.thumbnails_dir(task_id, "imposition", node_id)

    def imposition_page_thumbs_dir(self, task_id: str,
                                   node_id: str | None = None) -> Path:
        """拼版**页面效果缩略图实体**目录：``tasks/<id>/thumbnails/imposition_pages/``。

        与 :meth:`imposition_thumbnails_dir`（页内**单张源图**的缩略图）
        不是一层：这里放按版面合成的**整页**实体，``page1.jpg`` 从第一页
        起数，映射数据（页号 ↔ 文件 ↔ 内容签名）在同目录 ``index.json``
        （用户 2026-10-09：「缩略图实体其实没有生成落地……组合成拼版图片
        应该另外放在一个目录中，直接按照 page1 page2 命名，注意做好映射
        数据」）。随任务目录走，``delete_task`` 一并清掉。

        ⚠️ 按**节点**取（B 方案）：两个「图片拼版」节点各有各的版面文档与
        合成产物，缩略图实体也跟着分（``imposition_pages[~<节点>]``）。
        """
        return self.thumbnails_dir(task_id, "imposition_pages", node_id)

    def copy_source_to_task(self, task_id: str, source_path: Path) -> Path:
        """导入时在任务目录下保留一份源文件副本（原子落地）。

        ⚠️ 复制本身可能是在**后台线程**里做的（见
        ``desktop/workers/serial_jobs.py``），而详情页/预览随时会来读这份
        副本，所以走 ``copy_file_atomic``：写 ``.part`` 再 ``os.replace``，
        别人不会读到半截 PDF。
        """
        target = self.task_dir(task_id) / source_path.name
        return copy_file_atomic(source_path, target)

    def source_copy_path(self, task_id: str) -> Path | None:
        """任务目录里的 PDF 备份路径；没有备份返回 None。

        ⚠️ 后续所有操作（详情页预览、extract 入参…）**都必须用它**，不能用
        ``task['source_path']``：源文件在用户磁盘上，会被移动/改名/删除，
        一走就「渲染失败」。备份随任务走，任务才是自包含的。
        """
        task_dir = self.task_dir(task_id)
        task = self.get_task(task_id)
        if task:
            candidate = task_dir / Path(str(task.get("source_path") or "")).name
            if candidate.is_file():
                return candidate
        # 兜底：源被改名过（文件名对不上）时，任务目录下唯一的源文件就是备份
        candidates = (
            sorted(
                (
                    path
                    for ext in SOURCE_DOCUMENT_EXTS
                    for path in task_dir.glob(f"*{ext}")
                ),
                key=lambda path: path.name,
            )
            if task_dir.exists()
            else []
        )
        return candidates[0] if candidates else None

    def ensure_source_copy(self, task_id: str) -> Path | None:
        """保证任务目录里有 PDF 备份；缺了就按索引里的 source_path 补一份。

        老任务（导入时复制失败）或备份被误删时靠它自愈；源也一起没了就
        返回 None，调用方负责提示。
        """
        existing = self.source_copy_path(task_id)
        if existing:
            return existing
        task = self.get_task(task_id)
        if not task:
            return None
        source = Path(str(task.get("source_path") or ""))
        if not source.is_file():
            return None
        try:
            return self.copy_source_to_task(task_id, source)
        except OSError:
            return None
