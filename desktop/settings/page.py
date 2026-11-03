# -*- coding: utf-8 -*-
"""设置页（左侧栏底部「设置」进的那一页）。

用户 2026-10-16：

> 1. 左侧栏开启设置菜单；2. 菜单里面有「启用开发者模式」胶囊；
>    开发者模式下有各种选项（目前只有 a. 是否启用YOLO标注）。

界面照 qfluentwidgets 的设置页范式（用户给的 SettingCard 参考）：一张
``SettingCard`` = 一行「图标 + 标题 + 说明 + 右侧控件」，多张归进一个
``SettingCardGroup``。开关用 ``SwitchSettingCard``，它**直接绑配置项**
（``configItem=…``）——勾选即落盘，本页不自己存值。

⚠️ **「启用YOLO标注」是开发者模式的下级选项**：开发者模式关着时它整张卡
藏起来（``SettingCardGroup`` 的 ``ExpandLayout`` 会跳过隐藏项，但**组自己的
高度**是算好的，所以藏完必须补一次 ``adjustSize()``，否则卡片下方留一块
空白）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    FluentIcon as FIF,
    MessageBox,
    PushSettingCard,
    SettingCardGroup,
    SmoothScrollArea,
    SwitchSettingCard,
)

from desktop.services.detect_export import (
    YOLO_IMAGES_DIRNAME,
    YOLO_LABELS_DIRNAME,
)
from desktop.settings.config import CONFIG_FILENAME, AppConfig, app_config
from desktop.settings.location import (
    MigrationCanceled,
    copy_file_if_missing,
    destination_has_content,
    guard_destination,
    migrate_data,
    plan_migration,
    resolve_data_root,
)
from desktop.ui import theme as T
from desktop.ui.toast import show_toast
from desktop.ui.widgets import PageHeader, apply_to
from desktop.utils.files import (
    guji_data_dir,
    project_root,
    set_guji_data_dir,
)
from utils.box_geometry import YOLO_CLASS_NAMES


class SettingsPage(QWidget):
    """设置页：存储位置、自动更新、开发者模式与它下面的开发选项。

    ⚠️ 页面**没有**自己的导航条目概念——它由壳层（``desktop/shell.py``）
    挂在导航栏底部并切页，与各步骤的独立模块页是两回事（模块页来自
    ``MODULES`` 注册表，那一条链不许被本页污染）。
    """

    TITLE = "设置"
    SUBTITLE = "存储位置、自动更新、开发者模式与训练/标注相关选项"

    def __init__(self, parent=None):
        """建页头 + 设置卡片组（配置项绑在卡片上，本页不另存值）。"""
        super().__init__(parent)
        self.cfg: AppConfig = app_config()

        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        root.setSpacing(T.SPACE_MD)
        self.header = PageHeader(self.TITLE, self.SUBTITLE)
        root.addWidget(self.header)

        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # 底色交给窗口/页面根（见 desktop/ui/style.py 的全局 QSS）：不关掉
        # 视口底色的话，这一页会在卡片区外露出一块与其它页不同的灰。
        scroll.enableTransparentBackground()

        container = QWidget()
        column = QVBoxLayout(container)
        # 内容区（滚动区里的卡片组）再向内缩一圈，与外框留出间隔
        # （用户 2026-11-03：「设置内部 红框区域跟外部有间隔」）。
        column.setContentsMargins(
            T.SPACE_XL, T.SPACE_MD, T.SPACE_XL, T.SPACE_LG,
        )
        column.setSpacing(T.SPACE_MD)

        # ---- 存储：数据根位置（用户 2026-11-03 要求可更改）----
        # 卡片正文显示**当前生效**的目录；点「更改」选上级目录（自动补 guji），
        # 再问是否迁移。
        self.storage_group = SettingCardGroup("存储", container)
        self.storage_card = PushSettingCard(
            "更改",
            FIF.FOLDER,
            "存储位置",
            str(guji_data_dir()),
            parent=self.storage_group,
        )
        self.storage_card.clicked.connect(self.change_storage_location)
        self.storage_group.addSettingCard(self.storage_card)
        column.addWidget(self.storage_group)

        # ---- 更新：两项自动更新（用户 2026-11-02 要求；默认关，2026-11-03）----
        self.update_group = SettingCardGroup("更新", container)
        self.auto_app_card = SwitchSettingCard(
            FIF.SYNC,
            "自动更新软件",
            "启动时检查新版本，发现后自动下载安装包（在「帮助 → 检查更新」中完成安装）",
            configItem=self.cfg.autoUpdateApp,
            parent=self.update_group,
        )
        self.auto_data_card = SwitchSettingCard(
            FIF.SYNC,
            "自动更新数据包",
            "启动时检查去底色模型，发现新版后自动下载并替换生效",
            configItem=self.cfg.autoUpdateData,
            parent=self.update_group,
        )
        self.update_group.addSettingCards([self.auto_app_card, self.auto_data_card])
        column.addWidget(self.update_group)

        self.group = SettingCardGroup("开发者", container)
        self.dev_card = SwitchSettingCard(
            FIF.DEVELOPER_TOOLS,
            "启用开发者模式",
            "打开后才显示开发/训练相关的功能选项（普通使用请保持关闭）",
            configItem=self.cfg.developerMode,
            parent=self.group,
        )
        self.yolo_card = SwitchSettingCard(
            FIF.TAG,
            "启用YOLO标注",
            "在「检测文本框」的右栏底部显示「导出YOLO标注」按钮",
            configItem=self.cfg.yoloAnnotation,
            parent=self.group,
        )
        self.group.addSettingCards([self.dev_card, self.yolo_card])
        column.addWidget(self.group)

        # 文案里的目录与类别顺序都取自**唯一来源**（不在这里重抄字符串）
        self.yolo_hint = CaptionLabel(
            "打开「启用YOLO标注」后，「检测文本框」右栏底部会多出「导出YOLO标注」："
            "点它弹窗填名称（b1 → b1-1.jpg / b1-1.txt，序号按页序）并选导出目录，"
            "导出到 <导出目录>/<名称>/"
            + YOLO_IMAGES_DIRNAME
            + "/ 与 "
            + YOLO_LABELS_DIRNAME
            + "/；类别顺序为 "
            + "、".join(YOLO_CLASS_NAMES)
            + "（左框与右框都算半幅）；没有框的页面写空标签当负样本。"
        )
        self.yolo_hint.setWordWrap(True)
        apply_to(self.yolo_hint, T.SIZE_CAPTION, color=T.INK_FAINT)
        column.addWidget(self.yolo_hint)
        column.addStretch(1)

        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        # 开发者模式变化 → YOLO 卡片跟着显隐（配置项是长期存活的 QObject，
        # 本页被销毁时 Qt 会自动断开，不必手动收）
        self.cfg.developerMode.valueChanged.connect(self.sync_dev_options)
        self.sync_dev_options()

    # ------------------------------------------------------------ 存储位置
    def change_storage_location(self) -> None:
        """选上级目录（自动补 ``guji``）→ 问是否迁移 → 切换 → 重启。

        用户 2026-11-03：「设置增加存储位置选项，默认 ~/Documents/guji，
        可以更改；选择新目录询问是否将旧数据迁移到新目录，并告知不迁移会
        丢失数据，同意迁移则迁移数据」；同日追加「迁移到某个位置后，还是
        需要 guji 目录包裹」。
        """
        current = guji_data_dir()
        chosen = QFileDialog.getExistingDirectory(
            self.window(), "选择存放 guji 数据目录的上级目录", str(current.parent)
        )
        if not chosen:
            return
        # 数据根始终由 guji 文件夹包裹（用户 2026-11-03：「迁移到某个位置后，
        # 还是需要 guji 目录包裹」）；选中的目录本身叫 guji 时直接沿用。
        target = resolve_data_root(chosen)
        reason = guard_destination(current, target)
        if reason:
            show_toast(self.window(), "warning", "无法使用该目录", reason)
            return
        if target == Path(chosen).expanduser().resolve():
            body = f"当前存储位置：\n{current}\n\n新的存储位置：\n{target}\n\n"
        else:
            body = (
                f"当前存储位置：\n{current}\n\n"
                f"新的存储位置（会在所选目录下创建 guji 文件夹）：\n{target}\n\n"
            )
        if destination_has_content(target):
            body += "⚠️ 新目录里已有内容，迁移会覆盖同名文件。\n\n"
        body += (
            "迁移前请先停止正在执行的任务。\n\n"
            "是否把当前数据（任务、设置、缩略图缓存等）复制到新的存储位置？\n\n"
            "选择「不迁移」会直接切换过去：新位置从空白开始，现有任务与设置"
            "都不会出现在程序里（等同于丢失），旧目录的数据仍保留在原处，"
            "之后可以改回来。"
        )
        if not self._confirm(
            "更改存储位置", body, "迁移数据", "不迁移"
        ):
            # 不迁移：至少把设置文件带过去，免得自动更新等开关回到默认值。
            copy_file_if_missing(
                current / CONFIG_FILENAME, target / CONFIG_FILENAME
            )
        elif not self._migrate_data(current, target):
            return
        try:
            applied = set_guji_data_dir(target)
        except OSError as exc:
            show_toast(
                self.window(), "error", "更改存储位置失败", str(exc)
            )
            return
        self.storage_card.setContent(str(applied))
        self._restart_after_change(applied)

    def _migrate_data(self, source: Path, destination: Path) -> bool:
        """把 ``source`` 下的文件逐个复制到 ``destination``；返回是否完成。

        复制放在主线程 + ``processEvents``：迁移是用户主动触发的低频操作，
        逐个文件推进度既够用、又不引入额外的线程生命周期管理。
        """
        try:
            plan = plan_migration(source, destination)
        except OSError as exc:
            show_toast(self.window(), "error", "读取旧数据失败", str(exc))
            return False
        total = max(plan.total_files, 1)
        progress = QProgressDialog(
            "正在准备迁移数据…", "取消", 0, total, self.window()
        )
        progress.setWindowTitle("迁移数据")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)

        def on_progress(index: int, count: int, name: str) -> None:
            progress.setMaximum(max(count, 1))
            progress.setValue(index)
            progress.setLabelText(f"正在迁移数据… {index}/{count}\n{name}")
            QApplication.processEvents()

        try:
            copied, _copied_bytes = migrate_data(
                plan, on_progress, progress.wasCanceled
            )
        except MigrationCanceled:
            progress.close()
            self._info(
                "已取消迁移",
                "当前存储位置没有改变。新目录里可能已留下部分复制的文件，"
                "可以自行删除。",
            )
            return False
        except OSError as exc:
            progress.close()
            self._info(
                "迁移失败",
                f"复制数据时出错：{exc}\n\n当前存储位置没有改变。",
            )
            return False
        progress.close()
        self._info("迁移完成", f"已复制 {copied} 个文件到新的存储位置。")
        return True

    def _restart_after_change(self, target: Path) -> None:
        """位置已切换 ⇒ 立即重启（不做"稍后"：旧窗口的存储仍指向旧根，
        继续用会把新任务写进旧位置，越早重启越不容易出现"两边各一半"）。"""
        self._info(
            "存储位置已更改",
            f"新的存储位置：\n{target}\n\n"
            "重启程序后生效。点「立即重启」将关闭并重新打开程序。",
            "立即重启",
        )
        self._restart_app()

    def _restart_app(self) -> None:
        """先起新进程、再关自己（见 ``single_instance.release`` 的说明）。"""
        try:
            from desktop.single_instance import release

            release()
            frozen = bool(getattr(sys, "frozen", False))
            args = [sys.executable]
            cwd = None
            if not frozen:
                root = project_root()
                args.append(str(root / "desktop.py"))
                cwd = str(root)
            common = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "close_fds": True,
            }
            if sys.platform == "win32":
                subprocess.Popen(
                    args, cwd=cwd,
                    creationflags=0x00000008 | 0x00000200, **common,
                )
            else:
                subprocess.Popen(args, cwd=cwd, start_new_session=True, **common)
        except OSError as exc:
            show_toast(self.window(), "error", "重启失败", str(exc))
            return
        from desktop.ui.menu import quit_app

        quit_app(self.window())

    def _confirm(self, title: str, body: str, yes_text: str,
                 cancel_text: str) -> bool:
        """是/否确认框（返回是否点了左边那个"是"按钮）。"""
        box = MessageBox(title, body, self.window())
        box.yesButton.setText(yes_text)
        box.cancelButton.setText(cancel_text)
        return bool(box.exec())

    def _info(self, title: str, body: str, button_text: str = "好的") -> None:
        """只有一个确认按钮的提示框。"""
        box = MessageBox(title, body, self.window())
        box.cancelButton.setVisible(False)
        box.yesButton.setText(button_text)
        box.exec()

    def sync_dev_options(self, *_args) -> None:
        """按「开发者模式」开关显隐下级选项（并重算卡片组高度）。"""
        shown = bool(self.cfg.developerMode.value)
        self.yolo_card.setVisible(shown)
        self.yolo_hint.setVisible(shown)
        # ⚠️ 必须补这一句：SettingCardGroup 的高度是 adjustSize() 时算好的，
        #    只 setVisible 的话组还留着藏起来那张卡的高度（下方一块空白）。
        self.group.adjustSize()


__all__ = ["SettingsPage"]
