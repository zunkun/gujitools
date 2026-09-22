# -*- coding: utf-8 -*-
"""第四步的字体候选目录：已知候选 + 后台扫一次的系统字体。

为什么要这个模块
----------------
`utils.fonts.selectable_entries()` 是一张**静态候选表**，查它只花几毫秒，
足以覆盖日常字体。但用户自己装的补字字体（花园明朝、BabelStone Han…）只有
真扫描才能发现，而它们恰恰是古籍异体字最需要的。

扫描的代价是**慢**（本机 200+ 字体约 7 秒），所以规矩有两条：

1. **只在后台线程扫**（`_ScanThread`），且**全局只启动一次**——扫完的结果
   写磁盘缓存，之后每次都是毫秒级；
2. **绝不挡住出 PDF 的路**：生成 PDF 只用 `utils.fonts` 的静态候选表，
   本模块纯粹服务于"给用户看的字体列表"。

用户在前三步干活的那点空闲，足够后台把列表补全；直接进第四步也能用，
只是列表是静态候选（扫描完成后会自动补进来）。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from utils.fonts import selectable_entries

#: 「自动」项：值用空串，与参数默认 None 对齐（空 → 自动按仿宋优先）
AUTO_LABEL = "自动（仿宋优先）"
AUTO_VALUE = ""


class _ScanThread(QThread):
    """后台扫描系统字体（耗时数秒，**绝不放在主线程**）。"""

    finished_entries = Signal(object)

    def run(self) -> None:  # pragma: no cover - 线程体，自测直接调函数
        try:
            from utils.font_scan import scan_system_fonts

            entries = list(scan_system_fonts())
        except Exception:
            entries = []
        self.finished_entries.emit(entries)


class FontCatalog(QObject):
    """字体候选目录（进程内单例，见 `catalog()`）。

    - ``choices()``：立刻给出可用列表（静态候选 + 已扫到的），**不阻塞**；
    - ``start_scan()``：后台扫一次系统字体，完成后发 ``scan_finished``，
      界面据此把新字体补进下拉。重复调用直接返回。
    """

    scan_finished = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._extra: list = []
        self._started = False
        # ⚠️ 线程对象必须持有引用：QThread 被回收时若还在跑会直接崩
        self._thread: QThread | None = None

    def choices(self) -> list[tuple[str, str]]:
        """下拉候选 ``(中文显示, 参数值)``：自动 + 已知 + 扫描到的。

        ⚠️ 按**显示名**去重：扫描结果里常出现与已知候选同名的字体（都叫
        "楷体"），留两个同名项对用户没有意义，还容易选错。
        """
        items: list[tuple[str, str]] = [(AUTO_LABEL, AUTO_VALUE)]
        seen: set[str] = set()
        for entry in list(selectable_entries()) + list(self._extra):
            if entry.display in seen:
                continue
            seen.add(entry.display)
            items.append((entry.display, entry.display))
        return items

    def is_scanning(self) -> bool:
        """后台扫描是否在跑（界面可据此显示"扫描中"）。"""
        return self._thread is not None

    def start_scan(self) -> None:
        """启动后台扫描；**只启动一次**。

        调用时机无所谓（进第四步、回到第一步都行）——扫描在后台线程里跑，
        主线程不被拖住。
        """
        if self._started:
            return
        self._started = True
        thread = _ScanThread(self)
        thread.finished_entries.connect(self._on_scanned)
        self._thread = thread
        thread.start()

    def _on_scanned(self, entries) -> None:
        """后台扫描完成：记下结果并通知界面刷新下拉。"""
        self._extra = list(entries or [])
        self._thread = None
        self.scan_finished.emit(self.choices())


_CATALOG: FontCatalog | None = None


def catalog() -> FontCatalog:
    """进程内唯一的字体目录（首次调用时创建，需要已有 QApplication）。"""
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = FontCatalog()
    return _CATALOG


def start_background_scan() -> None:
    """在空闲时把系统字体列表补齐（只跑一次，后台线程）。"""
    try:
        catalog().start_scan()
    except Exception:
        # 没有 Qt 环境（CLI / 自测）时直接放弃：列表退化为静态候选，
        # 不影响生成 PDF
        pass
