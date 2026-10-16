# -*- coding: utf-8 -*-
"""顶部菜单栏（文件 / 单任务 / 帮助）自测。

断言线（用户 2026-10-15 提的三组菜单，"点了要真到那儿"）：

1. **结构**：三个顶级菜单与各自的动作文案（含 ``&`` 助记符）；
2. **路由**：点「单任务 → <模块>」真的切到该模块页、左侧导航高亮同步；
   点「文件 → 新建任务」真的落到创建任务页——菜单只做转发，不另建页；
3. **检查更新三分支**：已是最新 / 有新版本 / 查询失败各自的弹窗标题与正文，
   以及**重入防护**（检查期间再点不叠加请求、菜单项置灰改名）；
4. **退出**：走 ``window.close()``（触发 ``closeEvent`` 的 worker 收尾链），
   **不是** ``QApplication.quit()``。

⚠️ 网络与弹窗两处**整体替换**（``update_worker.fetch_latest_release`` /
``menu.shell_dialog``），本用例不碰真网络、不弹真模态；退出用例放在**最后**，
且用**新开的第二个窗口**，不关掉共享的 ``ctx.w``。
"""

from __future__ import annotations

import time

from tests.selftests._context import ok, pump, wait_until

NAME = "app_menu"
TITLE = "顶部菜单栏（文件/单任务/帮助）"
DEPENDS: list[str] = ["tasklist"]


def _menu_of(window, title: str):
    """按文案取顶级菜单——读 ``window.menu_bar``（**不是** ``window.menuBar()``）。

    ⚠️ 千万别在自测里碰 ``window.menuBar()``：``QMainWindow.menuBar()`` 会**就地
    造出**标题栏下面的一整行空菜单栏（这正是用户不要的"另起一行"），一碰就把
    被测窗口的布局改掉了。菜单栏现在的家在**标题栏里**（见 menu.py 的说明）。

    ⚠️ 顺带把菜单"还活着、还有内容"钉住：PySide6 里 ``addMenu("文案")`` 造出的
    ``QMenu`` 归 **Python** 持有，包装对象一被回收 C++ 菜单就销毁，而菜单栏上的
    action 只剩悬空指针——症状正是"菜单条还在、点开没有内容"（真踩过）。
    所以这里只认"**从菜单栏能读出动作**"这条路，而不是直接读 ``window.menus``。
    """
    for action in window.menu_bar.actions():
        if action.text() == title:
            menu = action.menu()
            assert menu is not None, f"菜单 {title} 没有实体"
            assert menu.actions(), f"菜单「{title}」读不到任何动作（QMenu 可能已被回收）"
            return menu
    raise AssertionError(f"没有找到顶级菜单：{title}")


def _action_of(menu, text: str):
    """按文案取菜单项（跳过分隔线）。"""
    for action in menu.actions():
        if not action.isSeparator() and action.text() == text:
            return action
    raise AssertionError(f"菜单里没有动作：{text}")


class _FakeDialog:
    """假弹窗实体：``exec()/show()`` 直接返回、``close()`` 只记一笔（自测里不弹真窗）。

    ⚠️ ``closed`` 要真的记下来：检查更新是"**先弹检查窗、结果回来再关掉它**"，
    "关没关"本身就是被断言的行为。
    """

    def __init__(self) -> None:
        self.closed = False

    def exec(self) -> int:
        return 1

    def show(self) -> None:
        return None

    def adjustSize(self) -> None:
        return None

    def done(self, _result: int = 0) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _DialogRecorder:
    """假弹窗外壳：替 ``menu.shell_dialog``，把每次调用的内容记下来。

    签名与真 ``shell_dialog`` 对齐（含关键字参数），并且**照真货的口径**从内容
    面板里读正文——``_MessagePanel`` / ``_AboutPanel`` 都是真控件，所以断言的是
    "用户真会看到什么"，而不是"传进去什么"。按钮文案/回调也一并记下（「换条线路」
    「取消」这类交互要能点）；``dialogs`` 留着创建出来的实体，好断言"关没关"。
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.dialogs: list[_FakeDialog] = []

    def __call__(self, title, panel, parent=None, **kwargs) -> _FakeDialog:
        from qfluentwidgets import BodyLabel

        labels = panel.findChildren(BodyLabel)
        self.calls.append({
            "title": title,
            "body": "\n".join(label.text() for label in labels),
            "ok_text": kwargs.get("ok_text"),
            "cancel_text": kwargs.get("cancel_text"),
            "show_cancel": kwargs.get("show_cancel"),
            "on_ok": kwargs.get("on_ok"),
            "on_cancel": kwargs.get("on_cancel"),
        })
        dialog = _FakeDialog()
        self.dialogs.append(dialog)
        return dialog


def run(ctx) -> None:
    import desktop.ui.menu as menu
    from config import VERSION
    from desktop.app import MainWindow
    from desktop.modules import MODULES

    app, w = ctx.app, ctx.w

    # ---- 1. 结构：三个顶级菜单 + 动作文案（含助记符）----
    titles = [action.text() for action in w.menu_bar.actions()]
    ok("顶部三个菜单：文件(&F) / 单任务(&S) / 帮助(&H)",
       titles == [menu.MENU_FILE, menu.MENU_SINGLE_TASK, menu.MENU_HELP],
       f"{titles}")
    ok("三个菜单都有活引用（window.menus）且从菜单栏读得到动作",
       sorted(getattr(w, "menus", {})) == sorted(titles)
       and all(m.actions() for m in w.menus.values()),
       f"{sorted(getattr(w, 'menus', {}))}")
    # ---- 1b. 菜单**在标题栏里、跟在标题后面**（用户 2026-10-15 的要求）----
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtWidgets import QMenuBar

    title_bar = w.titleBar
    ok("窗口是无边框的（菜单要跟标题同排，只能用自绘标题栏）",
       bool(w.windowFlags() & _Qt.WindowType.FramelessWindowHint),
       f"flags={w.windowFlags()}")
    ok("菜单栏的父控件就是标题栏（不是独立的菜单行）",
       w.menu_bar.parent() is title_bar, f"{w.menu_bar.parent()}")
    ok("菜单栏在标题栏布局里**紧跟标题**（indexOf(titleLabel)+1）",
       title_bar.hBoxLayout.indexOf(w.menu_bar)
       == title_bar.hBoxLayout.indexOf(title_bar.titleLabel) + 1,
       f"menu={title_bar.hBoxLayout.indexOf(w.menu_bar)} "
       f"title={title_bar.hBoxLayout.indexOf(title_bar.titleLabel)}")
    ok("标题栏显示的是窗口标题（装标题栏后同步过，否则一片空白）",
       title_bar.titleLabel.text() == w.windowTitle() == "古籍重製",
       f"{title_bar.titleLabel.text()!r}")
    ok("标题栏走「菜单位」承载（窗口顶部那一行就是它，中央控件自动让开）",
       w.menuWidget() is w.title_bar_holder, f"{w.menuWidget()}")
    bars = w.findChildren(QMenuBar)
    ok("全窗口只有一个菜单栏——没有另起一行的第二条（且它住在标题栏里）",
       len(bars) == 1 and bars[0].parent() is title_bar,
       f"bars={bars}")
    # ---- 1c. 顶栏文字与底色统一（用户 2026-10-15 的几条要求）----
    # 标题是我们自造的**素 QLabel**：库给的那个 ``CaptionLabel`` 自带 qfluentwidgets
    # 标签样式，外面三条路（setFont / 祖先 QSS / 标签自身 QSS）实测都改不动它的渲染
    # 字号，标题永远比菜单小一截。自造标签的字体只由 ``apply_to`` 决定，与菜单条
    # （只受 ``ui_font`` 影响）必然同款；再加**同高 + 都垂直居中** ⇒ 基线一致
    # （用户："改成一样大小；即使不一致，也要底部对齐"）。
    title_label = getattr(title_bar, "appTitleLabel")
    ok("标题用自造的素 QLabel，库给的 CaptionLabel 只是隐藏（不删，库内部要靠它）",
       not title_label.isHidden() and title_bar.titleLabel.isHidden()
       and title_label.objectName() == "appTitleLabel",
       f"library_hidden={title_bar.titleLabel.isHidden()}")
    ok("自造标题也跟着窗口标题走（windowTitleChanged 已接）",
       title_label.text() == w.windowTitle(), f"{title_label.text()!r}")
    ok("标题与菜单：字号/字族/行高全一致 ⇒ 渲染出来一样大、基线对齐",
       title_label.font().pixelSize() == w.menu_bar.font().pixelSize()
       == menu.TITLE_BAR_FONT_SIZE
       and title_label.font().family() == w.menu_bar.font().family()
       and title_label.height() == w.menu_bar.height()
       == menu.TITLE_BAR_ROW_HEIGHT,
       f"标题={title_label.font().family()}/"
       f"{title_label.font().pixelSize()}/h{title_label.height()} "
       f"菜单={w.menu_bar.font().family()}/"
       f"{w.menu_bar.font().pixelSize()}/h{w.menu_bar.height()}")
    from collections import Counter

    strip = w.title_bar_holder.grab()
    strip_colors = Counter(
        strip.toImage().pixelColor(x, y).name()
        for x in range(0, strip.width(), 3)
        for y in (2, strip.height() - 3)
    )
    ok("顶栏整条**一个底色**（渲染取样众数 = TITLE_BAR_BG，菜单不再自带另一种底）",
       strip.width() > 0 and strip_colors.most_common(1)[0][0] == menu.TITLE_BAR_BG.lower(),
       f"取样={strip_colors.most_common(3)} 期望={menu.TITLE_BAR_BG.lower()}")

    # ---- 1d. 「关于」的值要放得下（长路径/长网址曾只显示半截）----
    # 用**真实现算尺寸**（``_about_size`` 按内容撑宽），再量每个值标签的宽度够不够。
    about_dlg = menu.shell_dialog(
        "关于", menu._AboutPanel(menu.about_rows(w)), None,
        size=menu._about_size(w), ok_text=menu.BUTTON_OK, show_cancel=False,
    )
    about_dlg.show()
    pump(app, times=3)
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
       len(values) == len(menu.about_rows(w)) and not clipped,
       f"值={[v.text() for v in values]} 被截={clipped}")
    about_dlg.close()
    file_menu = _menu_of(w, menu.MENU_FILE)
    ok("文件菜单：新建任务(&N) / 退出(&X)",
       [a.text() for a in file_menu.actions() if not a.isSeparator()]
       == [menu.ACTION_CREATE_TASK, menu.ACTION_QUIT],
       f"{[a.text() for a in file_menu.actions()]}")
    ok("退出项带 &X 助记符（用户点名的写法）",
       menu.ACTION_QUIT.endswith("(&X)"), menu.ACTION_QUIT)
    help_menu = _menu_of(w, menu.MENU_HELP)
    ok("帮助菜单：帮助文档(&D) / 检查更新(&U) / 关于(&A)",
       [a.text() for a in help_menu.actions() if not a.isSeparator()]
       == [menu.ACTION_MANUAL, menu.ACTION_UPDATE, menu.ACTION_ABOUT],
       f"{[a.text() for a in help_menu.actions()]}")

    # ---- 2. 单任务：清单从 MODULES 派生（不写死），逐项都能切过去 ----
    single_menu = _menu_of(w, menu.MENU_SINGLE_TASK)
    expected = [module.title for module in MODULES]
    ok("单任务菜单逐项等于 MODULES 的文案（顺序也一致 = 与左侧导航同源）",
       [a.text() for a in single_menu.actions()] == expected,
       f"菜单={[a.text() for a in single_menu.actions()]} 注册表={expected}")
    for module in MODULES:
        _action_of(single_menu, module.title).trigger()
        pump(app, times=2)
        ok(f"点单任务「{module.title}」：切到该模块页且左侧导航高亮同步",
           w.shell.current_route() == module.key
           and w.shell.selected_route() == module.key,
           f"current={w.shell.current_route()} "
           f"selected={w.shell.selected_route()}")
        ok(f"点单任务「{module.title}」：模块页真的被建出来了",
           w.shell.module_page(module.key) is not None, module.key)
    w.shell.show_tasks()
    pump(app, times=2)

    # ---- 3. 文件 → 新建任务：复用壳层既有入口（含"每次进入复位"）----
    _action_of(file_menu, menu.ACTION_CREATE_TASK).trigger()
    pump(app, times=3)
    ok("文件→新建任务：落到创建任务页（走 shell.open_create）",
       w.shell.current_route() == "create", w.shell.current_route())
    w.shell.show_tasks()
    pump(app, times=2)

    # ---- 4. 检查更新的三分支文案（纯函数，先钉死不碰控件）----
    newer = menu.update_result(
        menu.RESULT_NEWER, current=VERSION,
        latest={"tag_name": "v99.0.1", "html_url": "https://example.invalid/dl",
                "name": "v99.0.1", "prerelease": False},
    )
    ok("有新版本：标题带 tag、正文给当前/最新与下载地址、主按钮是「前往下载」",
       newer.title == "发现新版本 v99.0.1"
       and f"v{VERSION}" in newer.body and "v99.0.1" in newer.body
       and "https://example.invalid/dl" in newer.body
       and newer.ok_text == menu.BUTTON_DOWNLOAD
       and newer.link == "https://example.invalid/dl",
       f"title={newer.title} ok={newer.ok_text} link={newer.link}")
    ok("有新版本（预发布）：正文额外提示这是预发布版",
       "预发布" in menu.update_result(
           menu.RESULT_NEWER, current=VERSION,
           latest={"tag_name": "v99.0.1", "html_url": "", "prerelease": True},
       ).body, "")
    # ---- 4b. 多线路（用户 2026-10-15：github 容易被 ban，可用代理拼接地址）----
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
       and "换条线路" in mirrored.body,
       f"body={mirrored.body!r}")
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
       any(value == f"v{VERSION}" for _key, value in menu.about_rows(w))
       and any(value == menu.PROJECT_URL for _key, value in menu.about_rows(w)),
       f"{menu.about_rows(w)}")

    # ---- 5. 检查更新：真发一次后台请求（网络函数被替换），含重入防护 ----
    controller = getattr(w, "update_controller", None)
    ok("窗口上挂着更新控制器（菜单项与它同源）",
       controller is not None, f"{controller}")
    # ⚠️ 断言一次"不是 None"：后面几十处都在用它的私有状态（``_checking`` /
    #    ``_aborted`` / ``_finish``），`getattr(..., None)` 的推断类型是 None，
    #    不钉住的话 Pyright 会把这些访问全判成 ``reportOptionalMemberAccess``。
    assert controller is not None, "更新控制器没挂到窗口上"
    update_action = _action_of(help_menu, menu.ACTION_UPDATE)

    recorder = _DialogRecorder()
    real_shell_dialog, real_fetch = menu.shell_dialog, update_worker.fetch_latest_release
    calls: list[int] = []

    #: 替身返回的"有新版本"数据：含四条线路测速排名（两条可用）与拼过最优线路
    #: 前缀的下载地址——「换条线路」「静默检查挂提示」都用它。
    newer_payload = {
        "tag_name": "v99.0.1", "name": "v99.0.1", "published_at": "",
        "prerelease": False,
        "html_url": "https://github.com/zunkun/gujitools/releases/tag/v99.0.1",
        "download_url": "https://v6.gh-proxy.org/https://example.invalid/A.exe",
        "mirror_prefix": "https://v6.gh-proxy.org/",
        "mirror_label": "v6.gh-proxy.org", "seconds": 0.38,
        "ranking": [
            {"prefix": "https://v6.gh-proxy.org/", "label": "v6.gh-proxy.org",
             "ok": True, "seconds": 0.38,
             "download_url": "https://v6.gh-proxy.org/https://example.invalid/A.exe"},
            {"prefix": "", "label": "直连", "ok": True, "seconds": 2.42,
             "download_url": "https://example.invalid/direct.exe"},
            {"prefix": "https://v4.gh-proxy.org/", "label": "v4.gh-proxy.org",
             "ok": False, "seconds": 1.3, "download_url": ""},
        ],
    }

    def _slow_fetch(url=None, timeout=None) -> dict:
        """替身：慢一点，好让"检查中再点一次"真的落在在途窗口里。"""
        calls.append(1)
        time.sleep(0.25)
        return dict(newer_payload)

    try:
        menu.shell_dialog = recorder
        update_worker.fetch_latest_release = _slow_fetch
        update_action.trigger()
        # ---- 5a. 先出「正在检查」窗（用户 2026-10-15：先弹窗，再反馈结果）----
        # ⚠️ 只断言**语义锚点**（标题含"正在检查"、正文提到最新版、按钮是取消），
        #    不逐字抄文案：这段文案由用户按自己口味改过（面板文案/窗口尺寸都是）。
        checking = recorder.calls[0]
        ok("点检查更新：**先**弹「正在检查」窗（非模态、按钮是「取消」）",
           "正在检查" in checking["title"]
           and checking["ok_text"] == "取消"
           and checking["show_cancel"] is False
           and "最新版" in checking["body"],
           f"{checking['title']} / {checking['body'][:40]!r}")
        ok("检查期间：菜单项置灰并改名「正在检查更新…」（用户看得见在跑）",
           controller._checking and not update_action.isEnabled()
           and update_action.text() == menu.ACTION_UPDATE_BUSY,
           f"busy={controller._checking} text={update_action.text()}")
        update_action.trigger()          # 第二次：应被重入防护挡下
        pump(app, times=2)
        ok("检查期间再点一次：不发起第二个请求（只提示，不叠加）",
           len(calls) == 1, f"calls={len(calls)}")
        ok("后台结果回来 → 关掉检查窗、弹出「发现新版本」（用**测速最优线路**的下载地址）",
           wait_until(app, lambda: len(recorder.calls) > 1, timeout=8.0)
           and recorder.calls[-1]["title"] == "发现新版本 v99.0.1"
           and "v6.gh-proxy.org/https://example.invalid/A.exe"
           in recorder.calls[-1]["body"]
           and recorder.dialogs[0].closed,
           f"{[c['title'] for c in recorder.calls]}")
        ok("结果落地后：菜单项恢复可用与原文案",
           update_action.text() == menu.ACTION_UPDATE
           and update_action.isEnabled(),
           f"text={update_action.text()} enabled={update_action.isEnabled()}")
        ok("重入防护有效：整个检查只有「检查窗 + 结果窗」两块，没有多弹",
           len(recorder.calls) == 2, f"{[c['title'] for c in recorder.calls]}")
        ok("有新版本时带「换条线路」按钮（排名里不止一条可用线路才会出现）",
           recorder.calls[-1]["ok_text"] == menu.BUTTON_DOWNLOAD
           and recorder.calls[-1]["show_cancel"] is True
           and recorder.calls[-1]["cancel_text"] == "换条线路",
           f"{recorder.calls[-1]}")
        # 点「换条线路」：切到下一条可用线路（直连）再弹一次，且**不重新联网**
        # （此时调过窗的序列是：检查窗 / 结果窗 / 换线路后的结果窗）
        calls.clear()
        recorder.calls[-1]["on_cancel"]()
        pump(app, times=3)
        ok("点「换条线路」：换到直连那条，下载地址跟着换，且没重新联网",
           calls == [] and len(recorder.calls) == 3
           and "下载线路：直连" in recorder.calls[-1]["body"]
           and "https://example.invalid/direct.exe" in recorder.calls[-1]["body"],
           f"requests={calls} 第三次正文={recorder.calls[-1]['body'][:60]!r}")

        # ---- 5c. 「正在检查」窗可以取消：取消后**不再弹结果窗** ----
        recorder.calls.clear()
        calls.clear()
        update_action.trigger()
        checking_again = recorder.calls[-1]
        recorder.calls[-1]["on_ok"]()      # 相当于点了检查窗的「取消」
        ok("检查中点了「取消」：立刻关窗、丢掉这次结果（菜单项也恢复）",
           controller._aborted and recorder.dialogs[-1].closed
           and update_action.text() == menu.ACTION_UPDATE
           and update_action.isEnabled(),
           f"aborted={controller._aborted} "
           f"closed={recorder.dialogs[-1].closed}")
        pump(app, times=20)                # 等后台那次请求跑完（替身 sleep 0.25s）
        ok("取消之后请求回来也不弹结果窗（不打扰用户）",
           len(calls) == 1 and len(recorder.calls) == 1,
           f"requests={len(calls)} 弹窗={[c['title'] for c in recorder.calls]}")
        del checking_again

        # 失败分支也要走通一次真链路（网络异常 → 失败弹窗）
        recorder.calls.clear()

        def _boom(url=None, timeout=None) -> dict:
            raise update_worker.UpdateCheckError("network")

        update_worker.fetch_latest_release = _boom
        update_action.trigger()
        ok("后台失败 → 弹出「检查更新失败」（分类文本来自 worker 的 kind）",
           wait_until(app, lambda: any(c["title"] == "检查更新失败"
                                       for c in recorder.calls), timeout=8.0)
           and recorder.calls[-1]["title"] == "检查更新失败"
           and menu.FAILURE_REASONS["network"][:6] in recorder.calls[-1]["body"],
           f"{recorder.calls}")

        # ---- 5e. 启动时的**后台静默**检查（用户 2026-10-15）----
        # 不弹任何窗；只有发现有新版本时才在菜单项上挂提示。
        recorder.calls.clear()
        calls.clear()

        def _silent_newer(url=None, timeout=None) -> dict:
            calls.append(1)
            return dict(newer_payload)

        update_worker.fetch_latest_release = _silent_newer
        controller.check_silently()
        ok("静默检查：**不弹任何窗**（启动时不该打扰用户）",
           wait_until(app, lambda: not controller._checking, timeout=8.0)
           and recorder.calls == [] and len(calls) == 1,
           f"弹窗={[c['title'] for c in recorder.calls]} requests={len(calls)}")
        ok("静默检查发现新版本：菜单项挂上「有新版本」提示，版本号进 tooltip",
           menu.NEW_VERSION_SUFFIX in update_action.text()
           and "v99.0.1" in update_action.toolTip(),
           f"text={update_action.text()!r} tip={update_action.toolTip()!r}")
        ok("菜单项仍可用（提示不影响点击，点它照样能显式检查）",
           update_action.isEnabled(), f"enabled={update_action.isEnabled()}")

        # 已是最新：提示要清掉（别留成"鬼影"）
        recorder.calls.clear()
        update_worker.fetch_latest_release = lambda url=None, timeout=None: {
            "tag_name": f"v{VERSION}", "html_url": "https://example.invalid/x"}
        controller.check_silently()
        ok("静默检查发现已是最新：菜单提示被清掉，且依然没有弹窗",
           wait_until(app, lambda: not controller._checking, timeout=8.0)
           and update_action.text() == menu.ACTION_UPDATE
           and recorder.calls == [],
           f"text={update_action.text()!r}")

        # 静默检查在飞时点菜单 → **升级**为显式检查（不重复发请求）
        recorder.calls.clear()
        calls.clear()

        def _slow_again(url=None, timeout=None) -> dict:
            calls.append(1)
            time.sleep(0.25)
            return dict(newer_payload)

        update_worker.fetch_latest_release = _slow_again
        controller.check_silently()
        update_action.trigger()
        ok("静默检查在飞时点菜单：升级成显式检查（出现检查窗、请求只发一次）",
           len(calls) == 1 and len(recorder.calls) == 1
           and "正在检查" in recorder.calls[0]["title"],
           f"requests={len(calls)} 弹窗={[c['title'] for c in recorder.calls]}")
        ok("升级后结果照常弹结果窗（走的还是最优线路）",
           wait_until(app, lambda: len(recorder.calls) > 1, timeout=8.0)
           and recorder.calls[-1]["title"] == "发现新版本 v99.0.1",
           f"{[c['title'] for c in recorder.calls]}")

        # 静默检查失败：安静收场（断网/限流都常见），不弹框、也不清掉已有提示
        recorder.calls.clear()
        update_worker.fetch_latest_release = _boom
        controller.check_silently()
        ok("静默检查失败：不弹任何窗，也不谎报「已是最新」",
           wait_until(app, lambda: not controller._checking, timeout=8.0)
           and recorder.calls == [],
           f"弹窗={[c['title'] for c in recorder.calls]}")

        # ---- 5f. 启动接线：静默检查挂在 main() 上（不是 MainWindow.__init__）----
        from pathlib import Path

        import desktop.app as app_module

        app_src = Path(app_module.__file__).read_text(encoding="utf-8")
        ok("启动接线：main() 里调度「后台静默检查更新」（而不是塞在 MainWindow.__init__）",
           "check_silently" in app_src
           and "STARTUP_UPDATE_CHECK_MS" in app_src
           and getattr(app_module, "STARTUP_UPDATE_CHECK_MS", 0) > 0,
           f"delay={getattr(app_module, 'STARTUP_UPDATE_CHECK_MS', None)}")
    finally:
        menu.shell_dialog = real_shell_dialog
        update_worker.fetch_latest_release = real_fetch
        controller._finish()          # 别把窗口的菜单项留在忙态

    # ---- 6. 退出：走 window.close()（收尾链），用第二个窗口，别关掉 ctx.w ----
    probe = MainWindow()
    probe.show()
    pump(app, times=3)
    quit_action = _action_of(_menu_of(probe, menu.MENU_FILE), menu.ACTION_QUIT)
    quit_action.trigger()
    pump(app, times=3)
    ok("文件→退出：窗口关闭（走 closeEvent → 各层 shutdown_workers 的收尾链）",
       not probe.isVisible(), f"visible={probe.isVisible()}")
    ok("退出后本窗口的后台线程表已收清（WorkerHost 收尾生效）",
       list(getattr(probe, "_threads", [])) == [],
       f"{getattr(probe, '_threads', None)}")
