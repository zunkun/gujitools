# -*- coding: utf-8 -*-
"""1. 结构：四个顶级菜单 + 动作文案（含助记符） / 1b. 菜单**在标题栏里、跟在标题后面**（用户 2026-10-15 的要求） / 1c. 顶栏文字与底色统一（用户 2026-10-15 的几条要求） / 1c2. 顶部「有新版本」提示条（用户 2026-11-02） / 1d. 「关于」的值要放得下（长路径/长网址曾只显示半截） / 真点一遍：动作必须转发到 ``edit_<能力>`` / 2. 独立功能：清单从 MODULES 派生（不写死），逐项都能切过去 / 3. 文件 → 新建任务：复用壳层既有入口（含\"每次进入复位\"） / 3b. 文件 → 快速任务：选 PDF 后**直接建任务**（不进创建页） / 4. 检查更新的三分支文案（纯函数，先钉死不碰控件） / 4b. 多线路（用户 2026-10-15：github 容易被 ban，可用代理拼接地址） / 4c. 下载完「重启安装」/ 下载失败「换线路重试」的纯文案 / 4d. 安装包下载内核（AppDownloadWorker）：下到 .part → 校验摘要 → 落盘"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import _action_of, _menu_of
    from qfluentwidgets import BodyLabel
    from collections import Counter
    from desktop.modules import MODULES
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QMenuBar
    from PySide6.QtWidgets import QWidget
    from desktop.shell import ROUTE_MODULES
    from config import VERSION
    from PySide6.QtCore import Qt as _Qt
    import hashlib as _hashlib
    from tests.common.tmpdir import temp_dir as _temp_dir
    import utils.download as _ud
    import desktop.ui.menu as menu
    from tests.selftests._context import ok, pump, wait_until
    import desktop.workers.update_worker as update_worker
    titles = [action.text() for action in st.w.menu_bar.actions()]
    ok("顶部四个菜单：文件(&F) / 编辑(&E) / 独立功能(&S) / 帮助(&H)",
       titles == [menu.MENU_FILE, menu.MENU_EDIT, menu.MENU_MODULES,
                  menu.MENU_HELP],
       f"{titles}")
    ok("四个菜单都有活引用（window.menus）且从菜单栏读得到动作",
       sorted(getattr(st.w, "menus", {})) == sorted(titles)
       and all(m.actions() for m in st.w.menus.values()),
       f"{sorted(getattr(st.w, 'menus', {}))}")
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtWidgets import QMenuBar

    st.title_bar = st.w.titleBar
    ok("窗口是无边框的（菜单要跟标题同排，只能用自绘标题栏）",
       bool(st.w.windowFlags() & _Qt.WindowType.FramelessWindowHint),
       f"flags={st.w.windowFlags()}")
    ok("菜单栏的父控件就是标题栏（不是独立的菜单行）",
       st.w.menu_bar.parent() is st.title_bar, f"{st.w.menu_bar.parent()}")
    ok("菜单栏在标题栏布局里**紧跟标题**（indexOf(titleLabel)+1）",
       st.title_bar.hBoxLayout.indexOf(st.w.menu_bar)
       == st.title_bar.hBoxLayout.indexOf(st.title_bar.titleLabel) + 1,
       f"menu={st.title_bar.hBoxLayout.indexOf(st.w.menu_bar)} "
       f"title={st.title_bar.hBoxLayout.indexOf(st.title_bar.titleLabel)}")
    ok("标题栏显示的是窗口标题（装标题栏后同步过，否则一片空白）",
       st.title_bar.titleLabel.text() == st.w.windowTitle() == "古籍重製",
       f"{st.title_bar.titleLabel.text()!r}")
    ok("标题栏走「菜单位」承载（窗口顶部那一行就是它，中央控件自动让开）",
       st.w.menuWidget() is st.w.title_bar_holder, f"{st.w.menuWidget()}")
    bars = st.w.findChildren(QMenuBar)
    ok("全窗口只有一个菜单栏——没有另起一行的第二条（且它住在标题栏里）",
       len(bars) == 1 and bars[0].parent() is st.title_bar,
       f"bars={bars}")
    title_label = getattr(st.title_bar, "appTitleLabel")
    ok("标题用自造的素 QLabel，库给的 CaptionLabel 只是隐藏（不删，库内部要靠它）",
       not title_label.isHidden() and st.title_bar.titleLabel.isHidden()
       and title_label.objectName() == "appTitleLabel",
       f"library_hidden={st.title_bar.titleLabel.isHidden()}")
    ok("自造标题也跟着窗口标题走（windowTitleChanged 已接）",
       title_label.text() == st.w.windowTitle(), f"{title_label.text()!r}")
    ok("标题与菜单：字号/字族/行高全一致 ⇒ 渲染出来一样大、基线对齐",
       title_label.font().pixelSize() == st.w.menu_bar.font().pixelSize()
       == menu.TITLE_BAR_FONT_SIZE
       and title_label.font().family() == st.w.menu_bar.font().family()
       and title_label.height() == st.w.menu_bar.height()
       == menu.TITLE_BAR_ROW_HEIGHT,
       f"标题={title_label.font().family()}/"
       f"{title_label.font().pixelSize()}/h{title_label.height()} "
       f"菜单={st.w.menu_bar.font().family()}/"
       f"{st.w.menu_bar.font().pixelSize()}/h{st.w.menu_bar.height()}")
    from collections import Counter

    strip = st.w.title_bar_holder.grab()
    strip_colors = Counter(
        strip.toImage().pixelColor(x, y).name()
        for x in range(0, strip.width(), 3)
        for y in (2, strip.height() - 3)
    )
    ok("顶栏整条**一个底色**（渲染取样众数 = TITLE_BAR_BG，菜单不再自带另一种底）",
       strip.width() > 0 and strip_colors.most_common(1)[0][0] == menu.TITLE_BAR_BG.lower(),
       f"取样={strip_colors.most_common(3)} 期望={menu.TITLE_BAR_BG.lower()}")
    banner = getattr(st.w, "update_banner", None)
    ok("主窗口里有顶部提示条，且默认收起", banner is not None
       and banner.isHidden(), f"banner={banner}")
    st.w._show_update_notice("app", "发现新版本 v9.9")
    pump(st.app, times=2)
    ok("检查到新版本：顶部提示条显示且文案正确",
       not banner.isHidden() and "v9.9" in banner.message(),
       f"hidden={banner.isHidden()} text={banner.message()!r}")
    st.w._show_update_notice("data", "数据包有新版本 v105")
    ok("程序更新与数据包更新两个来源的提示互不覆盖",
       "v9.9" in banner.message() and "v105" in banner.message(),
       f"text={banner.message()!r}")
    banner.close_button.click()
    pump(st.app, times=2)
    ok("点提示条右侧关闭按钮 → 提示收起（用户可关掉这条提示）",
       banner.isHidden(), f"hidden={banner.isHidden()}")
    st.w._show_update_notice("app", "")
    st.w._show_update_notice("data", "")
    # 关于弹窗宽度上限 900（小屏兜底）：测试临时数据目录远长于真实的
    # ``~/Documents/guji``，超过上限被裁是设计内行为。这里换成真实长度的
    # 数据目录再验证"值放得下"，避免测的其实是 tmp 路径长度。
    _store = getattr(st.w, "store", None)
    _real_root = getattr(_store, "root", None)
    if _store is not None:
        from pathlib import Path
        _store.root = Path.home() / "Documents" / "guji"
    about_dlg = menu.shell_dialog(
        "关于", menu._AboutPanel(menu.about_rows(st.w)), None,
        size=menu._about_size(st.w), ok_text=menu.BUTTON_OK, show_cancel=False,
        fit_height=True,
    )
    about_dlg.show()
    pump(st.app, times=3)
    from PySide6.QtGui import QFontMetrics
    from qfluentwidgets import BodyLabel

    values = [
        label for label in about_dlg.findChildren(BodyLabel)
        if label.textInteractionFlags() & _Qt.TextInteractionFlag.TextSelectableByMouse
    ]
    clipped = [
        label.text() for label in values
        if label.width() < QFontMetrics(label.font()).horizontalAdvance(label.text())
    ]
    ok("「关于」的每个值都放得下（被压成半截就会进这份名单）",
       len(values) == len(menu.about_rows(st.w)) and not clipped,
       f"值={[v.text() for v in values]} 被截={clipped}")
    # 用户 2026-11-27：Linux 下行高更大，写死的 180 高度把四行挤叠在一起。
    # 行高被压 = 标签实际高度小于一个字高。
    squeezed = [
        label.text() for label in values
        if label.height() < QFontMetrics(label.font()).height()
    ]
    ok("「关于」的行高没被压缩（高度按内容量，不写死；Linux/Windows 都不挤）",
       not squeezed and about_dlg.height() >= 180,
       f"被压={squeezed} 弹窗高={about_dlg.height()}")
    about_dlg.close()
    if _store is not None and _real_root is not None:
        _store.root = _real_root
    st.file_menu = _menu_of(st.w, menu.MENU_FILE)
    ok("文件菜单：新建任务(&N) / 快速任务(&Q) / 退出(&X)",
       [a.text() for a in st.file_menu.actions() if not a.isSeparator()]
       == [menu.ACTION_CREATE_TASK, menu.ACTION_QUICK_TASK, menu.ACTION_QUIT],
       f"{[a.text() for a in st.file_menu.actions()]}")
    ok("退出项带 &X 助记符（用户点名的写法）",
       menu.ACTION_QUIT.endswith("(&X)"), menu.ACTION_QUIT)
    st.edit_menu = _menu_of(st.w, menu.MENU_EDIT)
    ok("编辑菜单：删除选中 / 插入图片 / 下载图片 / 打印图片",
       [a.text() for a in st.edit_menu.actions() if not a.isSeparator()]
       == [menu.ACTION_DELETE_SELECTED, menu.ACTION_INSERT_IMAGES,
           menu.ACTION_DOWNLOAD_IMAGE, menu.ACTION_PRINT_IMAGE],
       f"{[a.text() for a in st.edit_menu.actions()]}")
    # 依赖模块（tasklist）跑完可能停在详情页；先回到任务列表再验可用性。
    st.w.pages.setCurrentWidget(st.w.list_page)
    ok("编辑菜单四项都问当前页要可用性（任务列表页不认识 → 全不可点）",
       all(menu._can_edit_action(st.w, capability) is False
           for capability, _text, _tip in menu.EDIT_MENU_ITEMS), "")
    from PySide6.QtWidgets import QWidget

    class _EditProbe(QWidget):
        """只实现编辑钩子的假页面（放进页面栈当"当前页"）。"""

        def __init__(self):
            super().__init__()
            self.fired: list[str] = []

        def can_edit_delete_selected(self):
            return True

        def can_edit_insert_images(self):
            return True

        def can_edit_download_image(self):
            return True

        def can_edit_print_image(self):
            return True

        def edit_delete_selected(self):
            self.fired.append("delete_selected")

        def edit_insert_images(self):
            self.fired.append("insert_images")

        def edit_download_image(self):
            self.fired.append("download_image")

        def edit_print_image(self):
            self.fired.append("print_image")

    probe_page = _EditProbe()
    st.w.pages.addWidget(probe_page)
    st.w.pages.setCurrentWidget(probe_page)
    edit_actions = [a for a in st.edit_menu.actions() if not a.isSeparator()]
    st.edit_menu.aboutToShow.emit()
    ok("编辑菜单四项在能力齐全的页面上全部可点",
       all(a.isEnabled() for a in edit_actions),
       f"{[(a.text(), a.isEnabled()) for a in edit_actions]}")
    for action in edit_actions:
        action.trigger()
    ok("编辑菜单四项动作真的转发到当前页（不是点了没反应）",
       probe_page.fired == [capability for capability, _t, _tip
                            in menu.EDIT_MENU_ITEMS],
       f"{probe_page.fired}")
    st.w.pages.setCurrentWidget(st.w.list_page)
    st.w.pages.removeWidget(probe_page)
    probe_page.deleteLater()
    st.help_menu = _menu_of(st.w, menu.MENU_HELP)
    ok("帮助菜单：帮助文档(&D) / 检查更新(&U) / 检查数据包(&M) / 关于(&A)",
       [a.text() for a in st.help_menu.actions() if not a.isSeparator()]
       == [menu.ACTION_MANUAL, menu.ACTION_UPDATE, menu.ACTION_DATA_PACKAGE,
           menu.ACTION_ABOUT],
       f"{[a.text() for a in st.help_menu.actions()]}")
    single_menu = _menu_of(st.w, menu.MENU_MODULES)
    expected = [module.title for module in MODULES]
    ok("独立功能菜单逐项等于 MODULES 的文案（顺序也一致 = 与入口页同源）",
       [a.text() for a in single_menu.actions()] == expected,
       f"菜单={[a.text() for a in single_menu.actions()]} 注册表={expected}")
    from desktop.shell import ROUTE_MODULES

    for module in MODULES:
        _action_of(single_menu, module.title).trigger()
        pump(st.app, times=2)
        ok(f"点独立功能「{module.title}」：切到该模块页且导航高亮在「独立功能」",
           st.w.shell.current_route() == module.key
           and st.w.shell.selected_route() == ROUTE_MODULES,
           f"current={st.w.shell.current_route()} "
           f"selected={st.w.shell.selected_route()}")
        ok(f"点独立功能「{module.title}」：模块页真的被建出来了",
           st.w.shell.module_page(module.key) is not None, module.key)
    st.w.shell.show_tasks()
    pump(st.app, times=2)
    _action_of(st.file_menu, menu.ACTION_CREATE_TASK).trigger()
    pump(st.app, times=3)
    ok("文件→新建任务：落到创建任务页（走 shell.open_create）",
       st.w.shell.current_route() == "create", st.w.shell.current_route())
    st.w.shell.show_tasks()
    pump(st.app, times=2)
    class _FakeFileDialog:
        """替身文件对话框：只记被问过、并按脚本给一个"用户选择"。"""

        path = ""

        @staticmethod
        def getOpenFileName(*_args, **_kwargs):
            return (_FakeFileDialog.path, "")

    quick_calls: list = []
    original_quick = st.w.shell.quick_task
    original_dialog = menu.QFileDialog
    st.w.shell.quick_task = lambda path: quick_calls.append(path)
    menu.QFileDialog = _FakeFileDialog  # type: ignore[assignment]
    try:
        _FakeFileDialog.path = ""          # 用户按了取消
        _action_of(st.file_menu, menu.ACTION_QUICK_TASK).trigger()
        pump(st.app, times=2)
        ok("快速任务：在文件对话框里取消 ⇒ 什么都不做（不建任务、不切页）",
           quick_calls == [] and st.w.shell.current_route() == "tasks",
           f"calls={quick_calls} route={st.w.shell.current_route()}")
        _FakeFileDialog.path = r"C:\books\b1.pdf"      # 选好一个 PDF
        _action_of(st.file_menu, menu.ACTION_QUICK_TASK).trigger()
        pump(st.app, times=2)
        ok("快速任务：选好 PDF 后把路径交给 shell.quick_task",
           quick_calls == [r"C:\books\b1.pdf"], str(quick_calls))
        ok("快速任务：**不**跳到创建任务页（那是「新建任务」的路子）",
           st.w.shell.current_route() == "tasks", st.w.shell.current_route())
    finally:
        st.w.shell.quick_task = original_quick
        menu.QFileDialog = original_dialog  # type: ignore[assignment]

    # shell.quick_task 喂给既有链路的参数：任务名 = PDF 文件名；diagram=None ⇒ 默认流程
    seen_create: list = []
    original_start = st.w.shell.list_page.start_create
    st.w.shell.list_page.start_create = lambda *a: seen_create.append(a)
    try:
        st.w.shell.quick_task("C:/books/b1.pdf")
    finally:
        st.w.shell.list_page.start_create = original_start
    ok("shell.quick_task：复用 start_create，任务名 = PDF 文件名（b1，不带 .pdf）",
       seen_create == [("C:/books/b1.pdf", "b1", None)], str(seen_create))
    seen_create.clear()
    original_start = st.w.shell.list_page.start_create
    st.w.shell.list_page.start_create = lambda *a: seen_create.append(a)
    try:
        st.w.shell.quick_task("C:\\books\\某本古籍.下册.PDF")
    finally:
        st.w.shell.list_page.start_create = original_start
    ok("shell.quick_task：名字取 stem（去掉最后一级后缀，中文名也照用）",
       seen_create == [("C:\\books\\某本古籍.下册.PDF", "某本古籍.下册", None)],
       str(seen_create))
    newer = menu.update_result(
        menu.RESULT_NEWER, current=VERSION,
        latest={"tag_name": "v99.0.1", "html_url": "https://example.invalid/dl",
                "name": "v99.0.1", "prerelease": False},
    )
    ok("有新版本：主按钮是「下载」（应用内），另给「前往下载页」作备用",
       newer.title == "发现新版本 v99.0.1"
       and f"v{VERSION}" in newer.body and "v99.0.1" in newer.body
       and "https://example.invalid/dl" in newer.body
       and newer.ok_text == menu.BUTTON_DOWNLOAD
       and newer.link == "https://example.invalid/dl"
       and newer.browser_url == "https://example.invalid/dl",
       f"title={newer.title} ok={newer.ok_text} browser={newer.browser_url}")
    ok("有新版本：正文里**不出现 markdown 星号**（QLabel 会原样显示 `**`）",
       "**" not in newer.body, f"{newer.body!r}")
    ok("有新版本（预发布）：正文额外提示这是预发布版",
       "预发布" in menu.update_result(
           menu.RESULT_NEWER, current=VERSION,
           latest={"tag_name": "v99.0.1", "html_url": "", "prerelease": True},
       ).body, "")
    import desktop.workers.update_worker as update_worker

    ok("四种方案 = 直连 + 三个 gh-proxy 镜像，且就是**前缀直接拼在原地址前**",
       len(update_worker.MIRROR_PREFIXES) == 4
       and update_worker.MIRROR_PREFIXES[0] == ""
       and set(update_worker.MIRROR_PREFIXES[1:]) == {
           "https://v6.gh-proxy.org/", "https://v4.gh-proxy.org/",
           "https://cdn.gh-proxy.org/",
       }
       and update_worker.build_url("", menu.PROJECT_URL) == menu.PROJECT_URL
       and update_worker.build_url("https://v6.gh-proxy.org/", menu.PROJECT_URL)
       == "https://v6.gh-proxy.org/" + menu.PROJECT_URL
       and update_worker.mirror_label("") == "直连"
       and update_worker.mirror_label("https://v6.gh-proxy.org/")
       == "v6.gh-proxy.org",
       f"prefixes={update_worker.MIRROR_PREFIXES}")
    ranked_payload = {
        "tag_name": "v99.0.1",
        "html_url": "https://github.com/zunkun/gujitools/releases/tag/v99.0.1",
        "download_url": "https://v6.gh-proxy.org/https://github.com/x/A.exe",
        "mirror_prefix": "https://v6.gh-proxy.org/",
        "mirror_label": "v6.gh-proxy.org",
        "seconds": 0.38,
        "ranking": [
            {"prefix": "https://v6.gh-proxy.org/", "label": "v6.gh-proxy.org",
             "ok": True, "seconds": 0.38,
             "download_url": "https://v6.gh-proxy.org/https://github.com/x/A.exe"},
            {"prefix": "", "label": "直连", "ok": True, "seconds": 2.42,
             "download_url": "https://github.com/x/A.exe"},
            {"prefix": "https://v4.gh-proxy.org/", "label": "v4.gh-proxy.org",
             "ok": False, "seconds": 1.3, "download_url": ""},
        ],
    }
    mirrored = menu.update_result(
        menu.RESULT_NEWER, current=VERSION, latest=ranked_payload)
    ok("有新版本：正文报出**走哪条线路、多快**，下载地址是拼过该前缀的那个",
       "下载线路：v6.gh-proxy.org（0.38s）" in mirrored.body
       and mirrored.link == ranked_payload["download_url"]
       and mirrored.browser_url == ranked_payload["html_url"],
       f"body={mirrored.body!r}")
    ready = menu._ready_verdict("v99.0.1")
    ok("安装包就绪：主按钮「立即重启安装」、次按钮「稍后」，正文带版本号",
       ready.title == "更新已就绪"
       and ready.ok_text == menu.BUTTON_INSTALL
       and menu.BUTTON_INSTALL in ready.body and menu.BUTTON_LATER in ready.body
       and "v99.0.1" in ready.body,
       f"{ready}")
    failed_dl = menu._download_failed_verdict("network", "https://example.invalid/dl")
    ok("下载失败：主按钮「换条线路重试」、次按钮「前往下载页」（备用，带 release 网页）",
       failed_dl.title == "更新下载失败"
       and failed_dl.ok_text == menu.BUTTON_RETRY
       and failed_dl.browser_url == "https://example.invalid/dl"
       and menu.FAILURE_REASONS["network"][:6] in failed_dl.body,
       f"{failed_dl}")
    ok("检查失败时也说明「四条线路都试过」，不让人以为只试了直连",
       "直连与三个镜像都试过" in menu.update_result("network", current=VERSION).body,
       "")
    latest_state = menu.update_result(
        menu.RESULT_LATEST, current=VERSION,
        latest={"tag_name": f"v{VERSION}", "html_url": "https://example.invalid/x"},
    )
    ok("已是最新：标题写明、正文报当前版本、只有「好的」一个按钮",
       latest_state.title == "已是最新版本"
       and f"v{VERSION}" in latest_state.body
       and latest_state.ok_text == menu.BUTTON_OK
       and latest_state.link == "",
       f"title={latest_state.title}")
    failed = menu.update_result("network", current=VERSION)
    ok("查询失败（network）：中文原因 + 项目主页指引，不谎报有新版本",
       failed.title == "检查更新失败"
       and menu.FAILURE_REASONS["network"][:6] in failed.body
       and menu.PROJECT_URL in failed.body
       and failed.link == "",
       f"title={failed.title}")
    ok("查询失败（http:500 这类未知分类）：仍给得出可读文案（不抛异常）",
       "HTTP 500" in menu.update_result("http:500", current=VERSION).body,
       menu.update_result("http:500", current=VERSION).body)
    ok("关于：行里有版本（config.VERSION 唯一来源）与项目地址",
       any(value == f"v{VERSION}" for _key, value in menu.about_rows(st.w))
       and any(value == menu.PROJECT_URL for _key, value in menu.about_rows(st.w)),
       f"{menu.about_rows(st.w)}")
    import hashlib as _hashlib

    import utils.download as _ud
    from tests.common.tmpdir import temp_dir as _temp_dir

    class _Resp:
        """内存假响应（够 ``urlopen`` 那条读链路用）。"""

        def __init__(self, data: bytes) -> None:
            self._data, self._pos = data, 0
            self.headers = {"Content-Length": str(len(data))}

        def read(self, size: int = -1) -> bytes:
            chunk = (self._data[self._pos:] if size < 0
                     else self._data[self._pos:self._pos + size])
            self._pos += len(chunk)
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *_exc) -> bool:
            return False

    blob = b"guji-installer-bytes" * 500
    digest = _hashlib.sha256(blob).hexdigest()
    setup = _temp_dir("app_dl_") / "guji_setup_v99.exe"
    real_urlopen = _ud.urllib.request.urlopen
    try:
        _ud.urllib.request.urlopen = (  # type: ignore[assignment]
            lambda request, timeout=None: _Resp(blob))
        worker = update_worker.AppDownloadWorker(
            "https://example.invalid/setup.exe", setup,
            sha256=digest, size=len(blob))
        result = worker._download()
        ok("安装包下载内核：内容落盘、无残留 .part、sha256 与摘要一致",
           setup.read_bytes() == blob
           and not setup.with_name(setup.name + ".part").exists()
           and result["sha256"] == digest and result["size"] == len(blob),
           f"{result}")
        bad = update_worker.AppDownloadWorker(
            "https://example.invalid/setup.exe", setup, sha256="0" * 64)
        raised = False
        try:
            bad._download()
        except ValueError:
            raised = True
        ok("安装包摘要不符：抛错并删掉下好的安装包（不留可被误装的坏包）",
           raised and not setup.exists(), f"raised={raised} exists={setup.exists()}")
    finally:
        _ud.urllib.request.urlopen = real_urlopen  # type: ignore[assignment]

