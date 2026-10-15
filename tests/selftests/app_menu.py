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
    """按文案取顶级菜单——走 ``QMenuBar.actions()[i].menu()``，即**用户窗口上的那一个**。

    ⚠️ 顺带把菜单"还活着、还有内容"钉住：PySide6 里 ``addMenu("文案")`` 造出的
    ``QMenu`` 归 **Python** 持有，包装对象一被回收 C++ 菜单就销毁，而菜单栏上的
    action 只剩悬空指针——症状正是"菜单条还在、点开没有内容"（真踩过）。
    所以这里只认"**从菜单栏能读出动作**"这条路，而不是直接读 ``window.menus``。
    """
    for action in window.menuBar().actions():
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
    """假弹窗实体：``exec()`` 直接返回（自测里不该有真模态循环）。"""

    def exec(self) -> int:
        return 1


class _DialogRecorder:
    """假弹窗外壳：替 ``menu.shell_dialog``，把每次调用的内容记下来。

    签名与真 ``shell_dialog`` 对齐（含关键字参数），并且**照真货的口径**从内容
    面板里读正文——``_MessagePanel`` / ``_AboutPanel`` 都是真控件，所以断言的是
    "用户真会看到什么"，而不是"传进去什么"。
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, title, panel, parent=None, **kwargs) -> _FakeDialog:
        from qfluentwidgets import BodyLabel

        labels = panel.findChildren(BodyLabel)
        self.calls.append({
            "title": title,
            "body": "\n".join(label.text() for label in labels),
            "ok_text": kwargs.get("ok_text"),
        })
        return _FakeDialog()


def run(ctx) -> None:
    import desktop.ui.menu as menu
    from config import VERSION
    from desktop.app import MainWindow
    from desktop.modules import MODULES

    app, w = ctx.app, ctx.w

    # ---- 1. 结构：三个顶级菜单 + 动作文案（含助记符）----
    titles = [action.text() for action in w.menuBar().actions()]
    ok("顶部三个菜单：文件(&F) / 单任务(&S) / 帮助(&H)",
       titles == [menu.MENU_FILE, menu.MENU_SINGLE_TASK, menu.MENU_HELP],
       f"{titles}")
    ok("三个菜单都有活引用（window.menus）且从菜单栏读得到动作",
       sorted(getattr(w, "menus", {})) == sorted(titles)
       and all(m.actions() for m in w.menus.values()),
       f"{sorted(getattr(w, 'menus', {}))}")
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
    import desktop.workers.update_worker as update_worker

    controller = getattr(w, "update_controller", None)
    ok("窗口上挂着更新控制器（菜单项与它同源）",
       controller is not None, f"{controller}")
    update_action = _action_of(help_menu, menu.ACTION_UPDATE)

    recorder = _DialogRecorder()
    real_shell_dialog, real_fetch = menu.shell_dialog, update_worker.fetch_latest_release
    calls: list[int] = []

    def _slow_fetch(url=None, timeout=None) -> dict:
        """替身：慢一点，好让"检查中再点一次"真的落在在途窗口里。"""
        calls.append(1)
        time.sleep(0.25)
        return {"tag_name": "v99.0.1", "html_url": "https://example.invalid/dl",
                "name": "v99.0.1", "published_at": "", "prerelease": False}

    try:
        menu.shell_dialog = recorder
        update_worker.fetch_latest_release = _slow_fetch
        update_action.trigger()
        ok("检查期间：菜单项置灰并改名「正在检查更新…」（用户看得见在跑）",
           controller._checking and not update_action.isEnabled()
           and update_action.text() == menu.ACTION_UPDATE_BUSY,
           f"busy={controller._checking} text={update_action.text()}")
        update_action.trigger()          # 第二次：应被重入防护挡下
        pump(app, times=2)
        ok("检查期间再点一次：不发起第二个请求（只提示，不叠加）",
           len(calls) == 1, f"calls={len(calls)}")
        ok("后台结果回来 → 弹出「发现新版本」弹窗",
           wait_until(app, lambda: bool(recorder.calls), timeout=8.0)
           and recorder.calls[-1]["title"] == "发现新版本 v99.0.1"
           and "https://example.invalid/dl" in recorder.calls[-1]["body"],
           f"{recorder.calls}")
        ok("结果落地后：菜单项恢复可用与原文案",
           update_action.text() == menu.ACTION_UPDATE
           and update_action.isEnabled(),
           f"text={update_action.text()} enabled={update_action.isEnabled()}")
        ok("重入防护有效：整个检查只弹了一次弹窗",
           len(recorder.calls) == 1, f"{len(recorder.calls)}")

        # 失败分支也要走通一次真链路（网络异常 → 失败弹窗）
        recorder.calls.clear()

        def _boom(url=None, timeout=None) -> dict:
            raise update_worker.UpdateCheckError("network")

        update_worker.fetch_latest_release = _boom
        update_action.trigger()
        ok("后台失败 → 弹出「检查更新失败」（分类文本来自 worker 的 kind）",
           wait_until(app, lambda: bool(recorder.calls), timeout=8.0)
           and recorder.calls[-1]["title"] == "检查更新失败"
           and menu.FAILURE_REASONS["network"][:6] in recorder.calls[-1]["body"],
           f"{recorder.calls}")
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
