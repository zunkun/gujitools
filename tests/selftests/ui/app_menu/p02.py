# -*- coding: utf-8 -*-
"""5. 检查更新：真发一次后台请求（网络函数被替换），含重入防护 / 5 的测试替身：绝不碰真网络 / 真浏览器 / 真安装器 / 真数据目录 / 6. 退出：走 window.close()（收尾链），用第二个窗口，别关掉 ctx.w"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import _DialogRecorder, _action_of, _menu_of
    from desktop.app import MainWindow
    from pathlib import Path
    from config import VERSION
    from pathlib import Path as _Path
    from PySide6.QtCore import QObject as _QObject
    from PySide6.QtCore import Signal as _Signal
    from PySide6.QtCore import Slot as _Slot
    import desktop.app as app_module
    import desktop.ui.menu as menu
    from tests.selftests._context import ok, pump, wait_until
    from tests.common.tmpdir import temp_dir
    import time
    import desktop.workers.update_worker as update_worker
    st.controller = getattr(st.w, "update_controller", None)
    ok("窗口上挂着更新控制器（菜单项与它同源）",
       st.controller is not None, f"{st.controller}")
    # ⚠️ 断言一次"不是 None"：后面几十处都在用它的私有状态（``_checking`` /
    #    ``_aborted`` / ``_finish``），`getattr(..., None)` 的推断类型是 None，
    #    不钉住的话 Pyright 会把这些访问全判成 ``reportOptionalMemberAccess``。
    assert st.controller is not None, "更新控制器没挂到窗口上"
    st.update_action = _action_of(st.help_menu, menu.ACTION_UPDATE)

    st.recorder = _DialogRecorder()
    st.real_shell_dialog, st.real_fetch = menu.shell_dialog, update_worker.fetch_latest_release
    st.calls: list[int] = []

    #: 替身返回的"有新版本"数据：含四条线路测速排名（两条可用）与拼过最优线路
    #: 前缀的下载地址——「换条线路」「静默检查挂提示」都用它。
    st.newer_payload = {
        "tag_name": "v99.0.1", "name": "v99.0.1", "published_at": "",
        "prerelease": False,
        "html_url": "https://github.com/zunkun/gujitools/releases/tag/v99.0.1",
        "asset": {"name": "guji_setup_v99.exe",
                  "url": "https://github.com/x/guji_setup_v99.exe",
                  "size": 9, "sha256": "f" * 64},
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
        st.calls.append(1)
        time.sleep(0.25)
        return dict(st.newer_payload)
    st._slow_fetch = _slow_fetch
    from pathlib import Path as _Path

    from PySide6.QtCore import QObject as _QObject
    from PySide6.QtCore import Signal as _Signal
    from PySide6.QtCore import Slot as _Slot

    from tests.common.tmpdir import temp_dir

    #: 安装包/待安装记录一律落**临时目录**——``menu.updates_dir`` 指向真实
    #: ``~/Documents/guji/updates``，不换替身会把 pending.json 写进用户文档目录。
    tmp_updates = temp_dir("app_update_")
    browsed: list[str] = []      # QDesktopServices.openUrl 记录
    launched: list[list] = []    # subprocess.Popen 记录
    quits: list[int] = []        # quit_app 记录（别真关掉共享的 ctx.w）

    class _FakeDesktop:
        """替 ``QDesktopServices``：只记一笔，离屏自测**绝不真开浏览器**。"""

        @staticmethod
        def openUrl(url) -> bool:
            browsed.append(url.toString())
            return True

    class _FakeSubprocess:
        """替 ``menu.subprocess``：记下 Popen 参数，**不真启动安装器**。"""

        DEVNULL = -3

        @staticmethod
        def Popen(args, **_kwargs):
            launched.append(list(args))
            return None

    class _FakeDownloadWorker(_QObject):
        """替 ``AppDownloadWorker``：写一个占位安装包后立刻回报成功/失败。"""

        progress = _Signal(int)
        stage = _Signal(str)
        finished = _Signal(dict)
        failed = _Signal(str)

        fail_with = ""          # 类属性：非空则改发 failed（测"换线路重试"）

        def __init__(self, url, dest, sha256="", size=0, timeout=None):
            super().__init__()
            self.dest = _Path(dest)

        def cancel(self) -> None:
            return None

        @_Slot()
        def run(self) -> None:
            if type(self).fail_with:
                self.failed.emit(type(self).fail_with)
                return
            self.progress.emit(50)
            self.stage.emit("verify")
            self.dest.parent.mkdir(parents=True, exist_ok=True)
            self.dest.write_bytes(b"installer")
            self.finished.emit({"path": str(self.dest), "name": self.dest.name,
                                "sha256": "f" * 64, "size": 9})

    real_updates_dir, real_pending_file = menu.updates_dir, menu.pending_install_file
    real_desktop, real_subprocess, real_quit = (
        menu.QDesktopServices, menu.subprocess, menu.quit_app)
    real_download_cls = update_worker.AppDownloadWorker

    try:
        menu.shell_dialog = st.recorder
        menu.updates_dir = lambda: tmp_updates
        menu.pending_install_file = lambda: tmp_updates / "pending.json"
        menu.QDesktopServices = _FakeDesktop
        menu.subprocess = _FakeSubprocess
        menu.quit_app = lambda _window=None: quits.append(1)
        update_worker.AppDownloadWorker = _FakeDownloadWorker
        update_worker.fetch_latest_release = st._slow_fetch
        st.update_action.trigger()
        # ---- 5a. 先出「正在检查」窗（用户 2026-10-15：先弹窗，再反馈结果）----
        # ⚠️ 只断言**语义锚点**（标题含"正在检查"、正文提到最新版、按钮是取消），
        #    不逐字抄文案：这段文案由用户按自己口味改过（面板文案/窗口尺寸都是）。
        checking = st.recorder.calls[0]
        ok("点检查更新：**先**弹「正在检查」窗（非模态、按钮是「取消」）",
           "正在检查" in checking["title"]
           and checking["ok_text"] == "取消"
           and checking["show_cancel"] is False
           and "最新版" in checking["body"],
           f"{checking['title']} / {checking['body'][:40]!r}")
        ok("检查期间：菜单项置灰并改名「正在检查更新…」（用户看得见在跑）",
           st.controller._checking and not st.update_action.isEnabled()
           and st.update_action.text() == menu.ACTION_UPDATE_BUSY,
           f"busy={st.controller._checking} text={st.update_action.text()}")
        st.update_action.trigger()          # 第二次：应被重入防护挡下
        pump(st.app, times=2)
        ok("检查期间再点一次：不发起第二个请求（只提示，不叠加）",
           len(st.calls) == 1, f"calls={len(st.calls)}")
        ok("后台结果回来 → 关掉检查窗、弹出「发现新版本」（用**测速最优线路**的下载地址）",
           wait_until(st.app, lambda: len(st.recorder.calls) > 1, timeout=8.0)
           and st.recorder.calls[-1]["title"] == "发现新版本 v99.0.1"
           and "v6.gh-proxy.org/https://example.invalid/A.exe"
           in st.recorder.calls[-1]["body"]
           and st.recorder.dialogs[0].closed,
           f"{[c['title'] for c in st.recorder.calls]}")
        ok("结果落地后：菜单项恢复可用与原文案",
           st.update_action.text() == menu.ACTION_UPDATE
           and st.update_action.isEnabled(),
           f"text={st.update_action.text()} enabled={st.update_action.isEnabled()}")
        ok("重入防护有效：整个检查只有「检查窗 + 结果窗」两块，没有多弹",
           len(st.recorder.calls) == 2, f"{[c['title'] for c in st.recorder.calls]}")
        # ---- 5b. 主按钮「下载」= 应用内下载；「前往下载页」= 浏览器（备用）----
        result_dialog = st.recorder.calls[-1]
        ok("有新版本时：主按钮「下载」（应用内），次按钮「前往下载页」（备用）",
           result_dialog["ok_text"] == menu.BUTTON_DOWNLOAD
           and result_dialog["show_cancel"] is True
           and result_dialog["cancel_text"] == menu.BUTTON_BROWSER,
           f"{result_dialog}")
        result_dialog["on_cancel"]()
        pump(st.app, times=2)
        ok("点「前往下载页」：用浏览器打开 release 网页（备用路径），没再弹窗",
           browsed == [st.newer_payload["html_url"]] and len(st.recorder.calls) == 2,
           f"browsers={browsed} 弹窗={[c['title'] for c in st.recorder.calls]}")

        # ---- 5c. 点「下载」：应用内下载 → 进度窗 → 「更新已就绪」→ 立即重启安装 ----
        st.recorder.calls.clear()
        st.calls.clear()
        result_dialog["on_ok"]()          # 相当于点了结果窗的「下载」
        pump(st.app, times=3)
        ok("点「下载」：弹出下载进度窗（替身 worker 秒回，菜单项文案随之复位）",
           wait_until(st.app, lambda: any(c["title"].startswith("正在下载")
                                       for c in st.recorder.calls), timeout=8.0),
           f"{[c['title'] for c in st.recorder.calls]} text={st.update_action.text()!r}")
        ok("下载完成：弹出「更新已就绪」（主按钮「立即重启安装」、次按钮「稍后」）",
           wait_until(st.app, lambda: any(c["title"] == "更新已就绪"
                                       for c in st.recorder.calls), timeout=8.0)
           and st.recorder.calls[-1]["ok_text"] == menu.BUTTON_INSTALL
           and st.recorder.calls[-1]["cancel_text"] == menu.BUTTON_LATER
           and st.recorder.calls[-1]["show_cancel"] is True
           and st.update_action.text() == menu.ACTION_UPDATE,
           f"{[c['title'] for c in st.recorder.calls]}")
        ok("安装包与「待安装」记录都落在**用户更新目录**（temp 替身，不污染真实数据目录）",
           (tmp_updates / "guji_setup_v99.exe").is_file()
           and (tmp_updates / "pending.json").is_file(),
           f"{sorted(p.name for p in tmp_updates.iterdir())}")
        # 点「立即重启安装」：启动安装器（分离进程）+ 退出本程序
        install_cb = st.recorder.calls[-1]["on_ok"]
        st.recorder.calls.clear()
        install_cb()
        pump(st.app, times=3)
        ok("点「立即重启安装」：Popen 启动安装器 + 调 quit_app 退出本程序",
           [args[0] for args in launched] == [str(tmp_updates / "guji_setup_v99.exe")]
           and quits == [1],
           f"launched={launched} quits={quits}")

        # ---- 5d. 安装包还在（用户上次点了「稍后」）：再检查直接给「立即重启安装」----
        st.recorder.calls.clear()
        st.calls.clear()
        st.update_action.trigger()
        ok("安装包已下过且文件还在：再检查**不用重下**，直接给「更新已就绪」",
           wait_until(st.app, lambda: len(st.recorder.calls) > 1, timeout=8.0)
           and st.recorder.calls[-1]["title"] == "更新已就绪"
           and st.recorder.calls[-1]["ok_text"] == menu.BUTTON_INSTALL,
           f"{[c['title'] for c in st.recorder.calls]}")

        # ---- 5e. 下载失败：自动换下一条可用线路，给「换条线路重试」----
        (tmp_updates / "pending.json").unlink(missing_ok=True)   # 清掉"免重下"缓存
        st.recorder.calls.clear()
        st.calls.clear()
        _FakeDownloadWorker.fail_with = "network"
        st.update_action.trigger()
        ok("下载失败前置：重新检查拿到结果窗，线路下标复位为 0",
           wait_until(st.app, lambda: len(st.recorder.calls) > 1, timeout=8.0)
           and st.controller._scheme_index == 0,
           f"{[c['title'] for c in st.recorder.calls]} idx={st.controller._scheme_index}")
        st.recorder.calls[-1]["on_ok"]()     # 点「下载」→ 替身 worker 发 failed
        pump(st.app, times=3)
        ok("下载失败：弹出「更新下载失败」，主按钮「换条线路重试」，已自动切到下一条线路",
           wait_until(st.app, lambda: any(c["title"] == "更新下载失败"
                                       for c in st.recorder.calls), timeout=8.0)
           and st.recorder.calls[-1]["ok_text"] == menu.BUTTON_RETRY
           and st.recorder.calls[-1]["cancel_text"] == menu.BUTTON_BROWSER
           and st.controller._scheme_index == 1,
           f"{[c['title'] for c in st.recorder.calls]} idx={st.controller._scheme_index}")
        _FakeDownloadWorker.fail_with = ""

        # ---- 5f. 「正在检查」窗可以取消：取消后**不再弹结果窗** ----
        st.recorder.calls.clear()
        st.calls.clear()
        st.update_action.trigger()
        checking_again = st.recorder.calls[-1]
        st.recorder.calls[-1]["on_ok"]()      # 相当于点了检查窗的「取消」
        ok("检查中点了「取消」：立刻关窗、丢掉这次结果（菜单项也恢复）",
           st.controller._aborted and st.recorder.dialogs[-1].closed
           and st.update_action.text() == menu.ACTION_UPDATE
           and st.update_action.isEnabled(),
           f"aborted={st.controller._aborted} "
           f"closed={st.recorder.dialogs[-1].closed}")
        pump(st.app, times=20)                # 等后台那次请求跑完（替身 sleep 0.25s）
        ok("取消之后请求回来也不弹结果窗（不打扰用户）",
           len(st.calls) == 1 and len(st.recorder.calls) == 1,
           f"requests={len(st.calls)} 弹窗={[c['title'] for c in st.recorder.calls]}")
        del checking_again

        # 失败分支也要走通一次真链路（网络异常 → 失败弹窗）
        st.recorder.calls.clear()

        def _boom(url=None, timeout=None) -> dict:
            raise update_worker.UpdateCheckError("network")

        update_worker.fetch_latest_release = _boom
        st.update_action.trigger()
        ok("后台失败 → 弹出「检查更新失败」（分类文本来自 worker 的 kind）",
           wait_until(st.app, lambda: any(c["title"] == "检查更新失败"
                                       for c in st.recorder.calls), timeout=8.0)
           and st.recorder.calls[-1]["title"] == "检查更新失败"
           and menu.FAILURE_REASONS["network"][:6] in st.recorder.calls[-1]["body"],
           f"{st.recorder.calls}")

        # ---- 5e. 启动时的**后台静默**检查（用户 2026-10-15）----
        # 不弹任何窗；只有发现有新版本时才在菜单项上挂提示。
        st.recorder.calls.clear()
        st.calls.clear()

        def _silent_newer(url=None, timeout=None) -> dict:
            st.calls.append(1)
            return dict(st.newer_payload)

        update_worker.fetch_latest_release = _silent_newer
        st.controller.check_silently()
        ok("静默检查：**不弹任何窗**（启动时不该打扰用户）",
           wait_until(st.app, lambda: not st.controller._checking, timeout=8.0)
           and st.recorder.calls == [] and len(st.calls) == 1,
           f"弹窗={[c['title'] for c in st.recorder.calls]} requests={len(st.calls)}")
        ok("静默检查发现新版本：菜单项挂上「有新版本」提示，版本号进 tooltip",
           menu.NEW_VERSION_SUFFIX in st.update_action.text()
           and "v99.0.1" in st.update_action.toolTip(),
           f"text={st.update_action.text()!r} tip={st.update_action.toolTip()!r}")
        ok("菜单项仍可用（提示不影响点击，点它照样能显式检查）",
           st.update_action.isEnabled(), f"enabled={st.update_action.isEnabled()}")

        # 已是最新：提示要清掉（别留成"鬼影"）
        st.recorder.calls.clear()
        update_worker.fetch_latest_release = lambda url=None, timeout=None: {
            "tag_name": f"v{VERSION}", "html_url": "https://example.invalid/x"}
        st.controller.check_silently()
        ok("静默检查发现已是最新：菜单提示被清掉，且依然没有弹窗",
           wait_until(st.app, lambda: not st.controller._checking, timeout=8.0)
           and st.update_action.text() == menu.ACTION_UPDATE
           and st.recorder.calls == [],
           f"text={st.update_action.text()!r}")

        # 静默检查在飞时点菜单 → **升级**为显式检查（不重复发请求）
        st.recorder.calls.clear()
        st.calls.clear()

        def _slow_again(url=None, timeout=None) -> dict:
            st.calls.append(1)
            time.sleep(0.25)
            return dict(st.newer_payload)

        update_worker.fetch_latest_release = _slow_again
        st.controller.check_silently()
        st.update_action.trigger()
        ok("静默检查在飞时点菜单：升级成显式检查（出现检查窗、请求只发一次）",
           len(st.calls) == 1 and len(st.recorder.calls) == 1
           and "正在检查" in st.recorder.calls[0]["title"],
           f"requests={len(st.calls)} 弹窗={[c['title'] for c in st.recorder.calls]}")
        ok("升级后结果照常弹结果窗（走的还是最优线路）",
           wait_until(st.app, lambda: len(st.recorder.calls) > 1, timeout=8.0)
           and st.recorder.calls[-1]["title"] == "发现新版本 v99.0.1",
           f"{[c['title'] for c in st.recorder.calls]}")

        # 静默检查失败：安静收场（断网/限流都常见），不弹框、也不清掉已有提示
        st.recorder.calls.clear()
        update_worker.fetch_latest_release = _boom
        st.controller.check_silently()
        ok("静默检查失败：不弹任何窗，也不谎报「已是最新」",
           wait_until(st.app, lambda: not st.controller._checking, timeout=8.0)
           and st.recorder.calls == [],
           f"弹窗={[c['title'] for c in st.recorder.calls]}")

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
        menu.shell_dialog = st.real_shell_dialog
        menu.updates_dir = real_updates_dir
        menu.pending_install_file = real_pending_file
        menu.QDesktopServices = real_desktop
        menu.subprocess = real_subprocess
        menu.quit_app = real_quit
        update_worker.AppDownloadWorker = real_download_cls
        update_worker.fetch_latest_release = st.real_fetch
        st.controller._finish()          # 别把窗口的菜单项留在忙态
        st.controller._finish_download()
    probe = MainWindow()
    probe.show()
    pump(st.app, times=3)
    quit_action = _action_of(_menu_of(probe, menu.MENU_FILE), menu.ACTION_QUIT)
    quit_action.trigger()
    pump(st.app, times=3)
    ok("文件→退出：窗口关闭（走 closeEvent → 各层 shutdown_workers 的收尾链）",
       not probe.isVisible(), f"visible={probe.isVisible()}")
    ok("退出后本窗口的后台线程表已收清（WorkerHost 收尾生效）",
       list(getattr(probe, "_threads", [])) == [],
       f"{getattr(probe, '_threads', None)}")

