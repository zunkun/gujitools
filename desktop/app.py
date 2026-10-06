# -*- coding: utf-8 -*-
"""gujitools 桌面端主窗口：左侧导航壳层（任务管理 + 独立模块）。"""

from __future__ import annotations
import os
import sys
from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtGui import QIcon
from qfluentwidgets import setTheme, Theme
from desktop.shell import NAV_COMPACT_WIDTH, ModuleShell
from desktop.store import TaskStore
from desktop.ui import theme as T
from desktop.utils.icon import rounded_window_icon
from desktop.ui.style import apply_app_style
from desktop.ui.window_size import apply_window_size
from desktop.utils.files import package_dir

#: 主窗口标题（单例守卫按它找已有实例的窗口，见 desktop/single_instance.py）
WINDOW_TITLE = "古籍重製"

#: 主窗口**期望**尺寸与最小尺寸（逻辑像素）。**只是期望**：真正落地前会按屏幕
#: 可用区域夹一次（见 desktop/ui/window_size.py），否则 1920×1080 @125% 的
#: 机器上 920 高会顶到任务栏后面去。截图脚本也复用这两个常量，别再写一份。
#:
#: 因为默认启动即最大化（见 WINDOW_START_MAXIMIZED），这两个值的实际角色是
#: **还原尺寸**：用户点标题栏的「还原」按钮/双击标题栏时落到的大小。
#:
#: ⚠️ 最小宽度**要把左侧导航栏那一截算进去**（2026-10-02）：1080 是**正文区**
#: 的设计下限（四个步骤的参数表单在这个宽度下才不被挤扁——第三步的输入框
#: 226px，再窄就掉到 178px），而壳层的导航栏是**常驻外框**、折叠时也占
#: ``NAV_COMPACT_WIDTH``。只写 1080 的话，用户在最小窗口下就正好少这 48px，
#: `tests/selftests/panel_label_fit.py` 的 200px 下限当场就红（实测 178px）。
#: 屏幕不够宽时 window_size.apply_window_size 会把最小尺寸再夹下来，不影响小屏。
CONTENT_MIN_WIDTH = 1080
WINDOW_SIZE = QSize(1440, 920)
WINDOW_MIN_SIZE = QSize(CONTENT_MIN_WIDTH + NAV_COMPACT_WIDTH, 720)

#: 启动时是否直接最大化（用户 2026-10-01 定：「我这个 1920 的屏幕默认就占满
#: 屏幕吧，现在默认宽度跟 1920 差不了多少，最大化最小化没什么意义」）。
#:
#: 理由成立：夹紧后的默认宽度已经是可用宽度的 94%（1536 → 1440），留的那 96px
#: 除了露出桌面什么用都没有；而本程序四个步骤的界面都是"越大越好"，用户开机
#: 十有八九第一件事就是按最大化。索性直接给。
#:
#: ⚠️ 保留了还原尺寸（WINDOW_SIZE）与最小尺寸（WINDOW_MIN_SIZE），所以「还原」
#: 依旧有意义——最大化不等于把窗口定死。这也是**只影响主窗口**的开关：图片
#: 预览/编辑/拼版选图等弹窗一律不最大化（用户明确要的是"程序"占满屏幕）。
WINDOW_START_MAXIMIZED = True


class MainWindow(QMainWindow):
    """主窗口：左侧导航壳层（任务管理 + 独立模块）与详情页跳转。

    2026-10-02 起，窗口中央从「列表页/详情页两页对切」升级为
    :class:`desktop.shell.ModuleShell`：左边一条 qfluentwidgets
    导航栏，右边页面栈。任务管理仍是首页，其余是彼此独立的工具模块
    （图片提取 / 去底色 / 拼图）。

    ⚠️ **对外的属性名一个都没变**：``list_page`` / ``detail_page`` / ``pages``
    / ``store`` 全部转发给壳层同名成员（见下面几个 property）。``tests/gui_shot.py``
    与 ``tests/selftests/_context.py`` 都按这些名字取页面操作控件，转发一层
    既升级了布局、又不改测试契约。
    """

    #: 启动后多久预热详情页（ms）。放在列表首帧画完之后，既不拖慢"窗口出现"，
    #: 又能在用户点进任务之前把那笔 Qt 构造开销付掉（见 _prewarm_detail_page）。
    PREWARM_DELAY_MS = 3000

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        # 期望 1440×920 / 最小 1080×720，但**先按屏幕可用区域夹一次**：
        # 1920×1080 @125% 的机器逻辑可用高只有 824，直接上 920 会让窗口底部
        # （日志状态条、第四步按钮）永远压在任务栏后面，非最大化就够不着。
        apply_window_size(self, WINDOW_SIZE, WINDOW_MIN_SIZE)

        # ========== 加载窗口图标 desktop/static/icon.png ==========
        # 打包后 desktop/ 是 PYZ 内字节码，磁盘上无此路径，改从
        # _internal/desktop/static 取（spec datas 已收集）——用 package_dir()
        #
        # 源图保持直角原图即可：形状由像素决定，圆角在这里统一裁
        # （ICON_RADIUS_RATIO，与打包脚本 tools/make_icon.py 同一套规则）。
        icon_path = package_dir() / "static" / "icon.png"
        if icon_path.exists():
            icon = rounded_window_icon(icon_path)
            self.setWindowIcon(icon if icon else QIcon(str(icon_path)))
        # ==========================================================

        self._store = TaskStore()
        # 壳层持有「导航栏 + 页面栈 + 各模块页」；详情页仍是惰性创建
        # （构造约 400ms，用户还在列表页时不该付这笔钱）。
        self.shell = ModuleShell(self._store)
        self.setCentralWidget(self.shell)
        self.setStyleSheet(f"QMainWindow {{ background: {T.CANVAS}; }}")
        self.shell.list_page.open_detail.connect(self._open_detail)
        # 预热详情页（见 _prewarm_detail_page）：① 刚点完导入；② 启动后空闲。
        # 两处都不占用户的操作响应路径，却把那笔 Qt 构造开销提前付掉。
        self.shell.list_page.import_queued.connect(self._prewarm_detail_page)
        QTimer.singleShot(self.PREWARM_DELAY_MS, self._prewarm_detail_page)

    # ---------------------------------------------------- 对外契约（转发壳层）
    # ⚠️ 这几个 property 是**测试与截图脚本的公开接口**，改名会连带弄坏它们：
    # gui_shot.py 用 ``window.pages.setCurrentWidget(window.list_page)``、
    # _context.py 用 ``window.detail_page`` / ``window.list_page.store``。
    @property
    def store(self):
        """任务存储：转发壳层（壳层与各页面各自持有引用，见 setter 的说明）。"""
        shell = getattr(self, "shell", None)
        return shell.store if shell is not None else self._store

    @store.setter
    def store(self, value) -> None:
        """整体换掉数据目录（测试/截图脚本把 store 指向临时目录时用）。

        ⚠️ 赋值必须**传到壳层**，不能只改 MainWindow 自己：壳层存了一份（惰性
        详情页构造时取它）、列表页存了一份、已建出来的详情页又存了一份。只改
        这里的话，惰性构造的详情页会继续读**真实数据目录**——表现是"打开的是
        同名任务号的另一个任务"（`tests/selftests/last_stage.py` 实测）：
        它给 MainWindow 换 store 后打开 0001，而详情页
        拿的是真实目录里的 0001，于是落到了那台机器上真正停留的步骤。
        """
        self._store = value
        shell = getattr(self, "shell", None)
        if shell is not None:
            shell.rebind_store(value)

    @property
    def pages(self):
        """页面栈（``QStackedWidget``）：转发给壳层，兼容既有调用点。"""
        return self.shell.pages

    @property
    def list_page(self):
        """任务列表页：转发给壳层。"""
        return self.shell.list_page

    @property
    def detail_page(self):
        """详情页实例（惰性构造）：转发给壳层。

        读它本身就等于声明「现在就需要详情页」，因此访问即构造——与启动期
        惰性并不冲突。
        """
        return self.shell.detail_page

    def _prewarm_detail_page(self) -> None:
        """预构造详情页骨架与**第一步**面板（用户一进去看到的就是它）。

        ⚠️ 只预热第一步：第 2/3/4 步的面板**用户不进去就不建**（2026-09-25
        用户明确要求）。构造面板是纯 Qt + Python 密集活，机器若正在跑导入
        后台（PyMuPDF 连续攥 GIL ~160ms/页），同样的代码会被拖慢十几倍——
        所以既不该在点进详情时现造，也不该替没进去的步骤提前造。

        预热时机：① 刚点完导入（列表页 import_queued）；② 启动后
        PREWARM_DELAY_MS（列表已画完、用户还在看列表）。两处都不占用户的
        操作响应路径。
        """
        self.shell.prewarm_detail_page()

    def _open_detail(self, task_id: str) -> None:
        """打开任务详情页（转发壳层；那里才是唯一实现处）。"""
        self.shell.open_detail(task_id)

    def _back_to_list(self) -> None:
        """返回任务列表（转发壳层）。"""
        self.shell.back_to_list()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """←/→ 转发给壳层（详情页翻页）。

        ⚠️ 点击预览大图（QLabel 默认不收焦点）后，焦点落在**主窗口本身**，
        按键只会到这里——不转发的话，用户点完图片按左右毫无反应
        （用户 18:29 实测）。转发实现见 ModuleShell.keyPressEvent。
        """
        self.shell.keyPressEvent(event)
        if not event.isAccepted():
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        """关闭窗口时让壳层收尾所有 worker 子进程与后台线程。

        壳层会把收尾分发给任务列表页、懒建的详情页与已构造的模块页；
        详情页持有 worker 子进程与后台线程的引用，直接退出会让进程被强杀。
        """
        self.shell.shutdown_workers()
        if self.shell._detail_page is not None:
            self.shell._detail_page.closeEvent(event)
        event.accept()  # 文件存储无需关闭


def _install_sigint_handler(app: QApplication) -> None:
    """让 Ctrl+C 能退出 GUI。
    Qt 事件循环阻塞在 C 层，Python 的 SIGINT 处理器只有在上层循环被
    周期性唤醒时才有机会执行，因此配一个空转 QTimer。
    """
    import signal
    from PySide6.QtCore import QTimer

    def _handle_sigint(signum, frame) -> None:
        app.quit()

    try:
        signal.signal(signal.SIGINT, _handle_sigint)
    except (ValueError, OSError):
        return
    keepalive = QTimer()
    keepalive.timeout.connect(lambda: None)
    keepalive.start(200)
    app._sigint_keepalive = keepalive  # 持有引用，防止被 GC


def main() -> int:
    """创建 QApplication、套用样式并显示主窗口，返回退出码。

    设环境变量 ``GUJI_GUI_SELFTEST=1`` 时，主窗口构造并短暂跑过事件循环后
    自动退出（退出码 0）。仅供打包后冒烟使用——GUI 是 windowed 程序，没有
    控制台，导入期崩溃会弹错误框并一直挂住，靠"进程还活着"根本判断不了
    成败；有了这个开关就能用**退出码**判定。
    """
    app = QApplication(sys.argv)
    setTheme(Theme.LIGHT)
    apply_app_style(app)  # 统一字体、主题色、底色与滚动条
    from desktop.ui.widgets import install_button_pointer_cursor

    install_button_pointer_cursor(app)  # 所有按钮 hover 手型光标
    from desktop.ui.font_setup import ensure_cjk_fonts

    ensure_cjk_fonts()  # 没有中文字体时先弹安装引导，再进主界面

    # ---- 子任务目录改名的一次性迁移 ----
    # singletask/<子任务>/ 以前按 spec 中文标题命名（``拼图/``、``去底色/``…），
    # 现已改用不变的 ``disk_key``。里面是缩略图缓存与**用户手改过的版面图**，
    # 不搬就等于丢了（"明明改过版面，重新打开又变回原样"）。放在字体引导
    # 之后、建窗口之前：失败只记日志，不拦启动（见函数 docstring）。
    try:
        from desktop.utils.files import migrate_legacy_singletask_dirs

        for line in migrate_legacy_singletask_dirs():
            print(f"[guji] singletask 目录迁移：{line}")
    except Exception as exc:  # noqa: BLE001 —— 迁移绝不该挡住进主界面
        print(f"[guji] singletask 目录迁移跳过：{exc}")

    # ---- 单例守卫：同一个构建只允许一个 GUI 实例 ----
    # 已有本构建实例在跑 → 把那个窗口恢复并带到前台，本进程直接退出。
    # 身份是 **desktop 包目录**：开发版与正式版的目录不同，因此两个程序可以
    # 同时存在、互不阻拦（用户原则）。冒烟模式（GUJI_GUI_SELFTEST）不检查：
    # 打包冒烟可能在 GUI 开着时运行，不该让它被单例挡住而"空过"。
    if not os.environ.get("GUJI_GUI_SELFTEST"):
        from desktop.single_instance import acquire, activate_existing_window

        if not acquire(str(package_dir())):
            activate_existing_window(WINDOW_TITLE)
            return 0

    window = MainWindow()
    # 默认占满屏幕（见 WINDOW_START_MAXIMIZED）；夹紧后的 WINDOW_SIZE 是还原
    # 尺寸。冒烟模式仍走 show()：无头环境不该依赖窗口管理器对最大化的处理。
    if WINDOW_START_MAXIMIZED and not os.environ.get("GUJI_GUI_SELFTEST"):
        window.showMaximized()
    else:
        window.show()
    # 列表数据推迟到窗口显示之后的**下一拍**：TaskListPage 首次渲染要建每行的
    # 控件、还要读各任务的 runs.json（实测 ~74 ms），放在 show() 之前等于推迟
    # 窗口出现。先给用户一个空壳窗口，再填内容。
    from PySide6.QtCore import QTimer

    QTimer.singleShot(0, window.list_page.refresh)
    # ⚠️ 启动**不再**自动跳回上次任务详情页（用户 2026-10-06 改口径）：一律
    #    停在「任务管理」列表页，由用户自己点哪个任务。任务级「上次停留的
    #    步骤」记忆**照旧**——点进任务详情时仍落到上次那一步，见
    #    `TaskDetailPage._initial_stage_index`。全局 `ui.json` 的 last_task
    #    记录仍照写（历史行为、不再当启动入口），将来若要恢复一键跳回，
    #    只需在这里加一个显式入口，不必重造记录。
    _install_sigint_handler(app)
    if os.environ.get("GUJI_GUI_SELFTEST"):
        from PySide6.QtCore import QTimer

        # 延迟一拍再退出：让事件循环真正转起来，能抓到构造期之外的错误
        QTimer.singleShot(500, app.quit)
    try:
        code = app.exec()
    finally:
        # desktop 关闭 → 释放常驻 YOLO 服务（模型 + torch 运行时约 350MB）。
        # ⚠️ 只在 GUI 路径做：worker 子进程不拥有服务，不该替 GUI 去关它。
        # 用户原则：desktop 关闭，YOLO 就释放；关掉之后下次检测重新拉起服务
        # （约 5 秒）。`shutdown_service` 内部吞掉所有异常，finally 里安全。
        from functions.yolo_service import shutdown_service

        shutdown_service()
    return code
