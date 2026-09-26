# -*- coding: utf-8 -*-
"""中文字体体检与 Linux 自动补装。

为什么需要这一层
----------------
Windows 自带仿宋 / 宋体，`utils.fonts` 的候选表几乎必然命中；而
Ubuntu / Debian 的最小安装**一个中文字体都没有**。问题是：缺字体时代码
不会报错，只会静默降级——

- PDF 标题与页码（`utils.pdf_draw.register_fonts`）退回 ``Helvetica`` →
  中文变方块或整段消失；
- 检测框标注（`utils.box_draw.find_cjk_font`）退回 ASCII 的 ``L`` / ``R`` / ``U``。

**产物是错的，界面却毫无提示**。所以 GUI 启动时先体检一次：

1. 找到中文字体 → 静默通过（Windows / macOS 基本都是这条路）；
2. 没找到 → 弹窗。Linux 上给「自动安装」：从发行版仓库拉一个中文字体包，
   **首选真正的仿宋** ``fonts-cwtex-fs``，其次 AR PL UMing、Noto CJK、文泉驿；
3. 自动装不上（无网络 / 无管理员权限 / 没有已知包管理器）→ 退回提示，
   给出可直接复制的手装命令。

依赖方向：只用标准库 + `utils.fonts`，属 `utils` 最底层，任何层都能引用。
**刻意不依赖 Qt**：安装要跑漫长的子进程并sudo/pkexec 提权，把它做成纯函数，
命令行、自测、GUI 三条路才能共用同一份判断（ GUI 侧只负责套壳与流式日志）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import sys
from dataclasses import dataclass
from pathlib import Path

from utils.fonts import GUJI_FONT_ENV, first_existing_cjk_font

# ---------------------------------------------------------------------- 常量

#: 字体文件扩展名（扫描用户自己安装的字体时用）
from utils.fonts import FONT_EXTS as _FONT_EXTS  # 唯一定义处在 utils/fonts.py（见那里的说明）

#: Linux 额外扫描的字体目录。发行版把字体装到哪、包名叫什么都不一样，
#: 光靠 utils.fonts 的静态候选表会漏掉「用户手动拷进去的 simfang.ttf」。
_FONT_DIRS = (
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "~/.local/share/fonts",
    "~/.fonts",
)

#: 字体**文件名**里出现这些词才认作中文字体（避免把某个拉丁字体误判成中文）。
#: 全部小写比较；注意这里只用于决定「要不要弹窗」，宁可宽松也不该漏报。
_CJK_NAME_HINTS = (
    "noto-cjk", "notoserifcjk", "notosanscjk", "sourcehan", "wqy",
    "droidsansfallback", "arphic", "uming", "ukai", "cns11643",
    "tw-kai", "tw-sung", "cwtex", "fandol", "simsun", "simfang",
    "simhei", "msyh", "songti", "heiti", "kaiti", "fangsong",
    "song", "hei", "fang", "kai", "ming", "zenhei", "microhei",
)


@dataclass(frozen=True)
class FontPackage:
    """一个可安装的中文字体包。

    - ``name``：包管理器里的包名；
    - ``label``：给用户看的一行说明（为什么要装它）；
    - ``families``：装完后得到的字体族名（`fc-list` 里显示的名字）。
    """

    name: str
    label: str
    families: str


#: 各包管理器下的候选项，**顺序即优先级**：先仿宋，再宋体/明体，最后才兜底到黑体。
_FONT_PLANS: dict[str, tuple[FontPackage, ...]] = {
    "apt": (
        FontPackage("fonts-cwtex-fs", "cwTeX 仿宋體 — 正经仿宋，最接近 Windows 的仿宋",
                    "cwTeXFangSong / TW-Kai"),
        FontPackage("fonts-arphic-uming", "文鼎明體 — 宋体骨架，字形端正、笔画清晰",
                    "AR PL UMing TW / CN"),
        FontPackage("fonts-noto-cjk", "Noto CJK — 思源系列，Ubuntu 默认也是它，覆盖最全",
                    "Noto Serif / Sans CJK SC"),
        FontPackage("fonts-wqy-zenhei", "文泉驿正黑", "WenQuanYi Zen Hei"),
        FontPackage("fonts-wqy-microhei", "文泉驿微米黑", "WenQuanYi Micro Hei"),
    ),
    "dnf": (
        FontPackage("google-noto-serif-cjk-fonts", "Noto Serif CJK — 思源宋体，字形端正",
                    "Noto Serif CJK SC"),
        FontPackage("cjkuni-uming-fonts", "文鼎明體 AR PL UMing — 宋体骨架", "AR PL UMing CN"),
        FontPackage("google-noto-sans-cjk-fonts", "Noto Sans CJK — 思源黑体", "Noto Sans CJK SC"),
        FontPackage("wqy-zenhei-fonts", "文泉驿正黑", "WenQuanYi Zen Hei"),
    ),
    "pacman": (
        FontPackage("adobe-source-han-serif-cn-fonts", "思源宋体 CN — 宋体骨架",
                    "Source Han Serif CN"),
        FontPackage("noto-fonts-cjk", "Noto CJK — 覆盖最全", "Noto Sans CJK SC"),
        FontPackage("wqy-zenhei", "文泉驿正黑", "WenQuanYi Zen Hei"),
    ),
    "zypper": (
        FontPackage("noto-sans-cjk-fonts", "Noto CJK — 覆盖最全", "Noto Sans CJK SC"),
        FontPackage("wqy-zenhei-fonts", "文泉驿正黑", "WenQuanYi Zen Hei"),
        FontPackage("wqy-microhei-fonts", "文泉驿微米黑", "WenQuanYi Micro Hei"),
    ),
}
# yum（CentOS 7 / RHEL 7）与 dnf 用同一套包名
_FONT_PLANS["yum"] = _FONT_PLANS["dnf"]

#: 安装命令的构造方式。注意都带非交互参数：GUI 里没有终端，绝不能让 debconf
#: 停下来问问题。
_INSTALL_ARGS: dict[str, tuple[str, ...]] = {
    "apt": ("apt-get", "install", "-y"),
    "dnf": ("dnf", "install", "-y"),
    "yum": ("yum", "install", "-y"),
    "pacman": ("pacman", "-S", "--noconfirm"),
    "zypper": ("zypper", "--non-interactive", "install"),
}

#: 刷新仓库元数据的命令（apt 的索引可能过期，此时 apt-get install 会报
#: 「无法定位软件包」，刷新一次再试就能救回来）。dnf/pacman/zypper 自己会刷新。
_REFRESH_ARGS: dict[str, tuple[str, ...]] = {
    "apt": ("apt-get", "update"),
    "dnf": ("dnf", "makecache"),
    "yum": ("yum", "makecache"),
    "pacman": ("pacman", "-Sy"),
    "zypper": ("zypper", "refresh"),
}

#: 失败归因关键词（全部小写比较）。中英双语：目标用户是中文环境，
#: LANG=zh_CN 时 apt/dnf 的输出是中文，只认英文会误判成「未知失败」。
_NET_MARKERS = (
    "failed to fetch", "temporary failure resolving", "network is unreachable",
    "could not resolve", "unable to connect", "no longer a valid mirror",
    "cannot initiate the connection", "connection timed out", "no internet",
    "无法连接", "无法下载", "暂时不能解析", "网络不可达", "连接超时",
)
_PERM_MARKERS = (
    "not authorized", "user canceled", "cancelled by user", "polkit",
    "authentication failed", "authentication is required", "incorrect password",
    "permission denied", "no askpass", "no tty present", "sudoers",
    "未授权", "认证失败", "需要认证", "拒绝访问", "权限不足", "取消",
)
_REFRESH_MARKERS = (
    "unable to locate package", "has no installation candidate",
    "no package provides", "unable to find a match",
    "无法定位软件包", "没有可用的软件包", "找不到套件",
)


@dataclass(frozen=True)
class FontCheck:
    """体检结果。

    - ``found``：本机是否有可用的中文字体；
    - ``path``：命中的字体文件（``found`` 为假时是 ``None``）；
    - ``source``：命中来源，``env``（``GUJI_CJK_FONT``）/ ``table``（内置候选表）
      / ``scan``（扫描字体目录）/ ``none``；
    - ``platform``：``windows`` / ``macos`` / ``linux`` / 其它（``sys.platform``）。
    """

    platform: str
    found: bool
    path: str | None
    source: str = "none"
    checked: tuple[str, ...] = ()


@dataclass(frozen=True)
class InstallResult:
    """安装尝试的结果。

    ``status`` 取值
    - ``ok``：装上了，且重新体检确实能找到中文字体；
    - ``network``：软件源不可达 / 下载失败 → 应提示用户手动安装；
    - ``permission``：提权失败或用户取消 → 同上；
    - ``unsupported``：非 Linux 或没有已知包管理器 → 同上；
    - ``failed``：其它失败（``output`` 里留了日志尾部，供排查）。
    """

    status: str
    message: str = ""
    command: tuple[str, ...] = ()
    output: str = ""
    installed: tuple[str, ...] = ()
    check: FontCheck | None = None

    @property
    def ok(self) -> bool:
        """是否成功装上并被系统识别。"""
        return self.status == "ok"


# ---------------------------------------------------------------------- 体检


def platform_name() -> str:
    """把 ``sys.platform`` 归一成 ``windows`` / ``macos`` / ``linux`` 三类。"""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def scan_font_dirs(limit: int = 8) -> tuple[str, ...]:
    """扫描常见字体目录里**看起来是中文**的字体文件（Linux 为主）。

    为什么要扫：静态候选表只能覆盖"发行版把 Noto/文泉驿装在标准位置"这一种
    情况。用户从 Windows 拷来的 ``simfang.ttf``、装到 ``~/.local/share/fonts``
    的自定义字体都不在表里——不扫就会明明有字体却提示缺字体。

    判定只按**文件名关键词**（见 ``_CJK_NAME_HINTS``）：读字体内部元数据要额外
    依赖。这里是"决定要不要弹窗"的启发式，宁可宽松也不漏报。
    """
    if platform_name() == "windows":
        return ()
    hits: list[str] = []
    for raw in _FONT_DIRS:
        base = Path(os.path.expanduser(raw))
        if not base.is_dir():
            continue
        try:
            files = sorted(p for p in base.rglob("*") if p.is_file())
        except OSError:
            continue
        for file in files:
            if file.suffix.lower() not in _FONT_EXTS:
                continue
            lowered = file.name.lower()
            if any(hint in lowered for hint in _CJK_NAME_HINTS):
                hits.append(str(file))
                if len(hits) >= limit:
                    return tuple(hits)
    return tuple(hits)


def check_cjk_font() -> FontCheck:
    """体检本机有没有可用的中文字体（不弹任何 UI，纯判断）。

    三级判定：``GUJI_CJK_FONT`` 环境变量 → 内置候选表 → 扫描字体目录。
    任何一级命中即认为可用。
    """
    platform = platform_name()
    from utils.fonts import cjk_font_paths

    table = tuple(cjk_font_paths())

    override = os.environ.get(GUJI_FONT_ENV, "").strip()
    if override and Path(override).exists():
        return FontCheck(platform, True, override, "env", table)

    path = first_existing_cjk_font()
    if path:
        return FontCheck(platform, True, path, "table", table)

    for scanned in scan_font_dirs(limit=1):
        return FontCheck(platform, True, scanned, "scan", table)

    return FontCheck(platform, False, None, "none", table)


# ---------------------------------------------------------------------- 安装计划


def detect_package_manager() -> str | None:
    """返回可用的包管理器键名（``apt`` / ``dnf`` / ``yum`` / ``pacman`` / ``zypper``）。"""
    for key, exe in (
        ("apt", "apt-get"), ("dnf", "dnf"), ("yum", "yum"),
        ("pacman", "pacman"), ("zypper", "zypper"),
    ):
        if shutil.which(exe):
            return key
    return None


def install_plan(manager: str | None = None) -> tuple[FontPackage, ...]:
    """返回该平台的字体安装候选（顺序即优先级）；未知包管理器返回空元组。"""
    if platform_name() != "linux":
        return ()
    key = manager or detect_package_manager()
    return _FONT_PLANS.get(key or "", ())


def available_packages(plan: tuple[FontPackage, ...], manager: str,
                       timeout: float = 10.0) -> tuple[FontPackage, ...]:
    """筛掉仓库里**确实没有**的包，避免浪费一次提权。

    只有 apt 能廉价地先问一次（`apt-cache policy` 不需要 root）；dnf/pacman/
    zypper 会自己刷新元数据，直接尝试即可。若一个都查不出来（索引为空的容器镜像
    很常见），原样返回——交给 `install_cjk_fonts` 先刷新再重试，别在这里把路堵死。
    """
    if not plan or manager != "apt" or not shutil.which("apt-cache"):
        return plan
    kept: list[FontPackage] = []
    for package in plan:
        try:
            proc = subprocess.run(
                ["apt-cache", "policy", package.name],
                capture_output=True, text=True, errors="replace", timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return plan
        blob = (proc.stdout or "") + "\n" + (proc.stderr or "")
        has_candidate = any(
            line.strip().startswith("Candidate:")
            and "(none)" not in line
            for line in blob.splitlines()
        )
        if has_candidate:
            kept.append(package)
    return tuple(kept) if kept else plan


# ---------------------------------------------------------------------- 网络探测

#: 各发行版软件源的主域名，用于「能不能连上软件源」的快速探测。
_PROBE_HOSTS: dict[str, str] = {
    "ubuntu": "http://archive.ubuntu.com/",
    "debian": "http://deb.debian.org/",
    "fedora": "https://mirrors.fedoraproject.org/",
    "rhel": "https://cdn.redhat.com/",
    "centos": "https://mirrors.centos.org/",
    "arch": "https://archive.archlinux.org/",
    "opensuse": "https://download.opensuse.org/",
}


def _os_id() -> str:
    """读 /etc/os-release 里的 ID；读不到返回空串。"""
    try:
        text = Path("/etc/os-release").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        if line.startswith("ID="):
            return line[3:].strip().strip('"').lower()
    return ""


def repo_reachable(timeout: float = 4.0) -> bool | None:
    """探测软件源是否可达。

    返回 ``True`` / ``False``；**判断不了**（非 Linux、认不出发行版）返回
    ``None``——此时不该拦人，直接尝试安装即可。

    为什么先探一次：apt 的 DNS 失败要等 30 秒以上才超时，用户会以为卡死了；
    主动探一下能在 4 秒内给出「连不上软件源」的明确结论。
    """
    if platform_name() != "linux":
        return None
    import urllib.error
    import urllib.request

    host = _PROBE_HOSTS.get(_os_id()) or _PROBE_HOSTS.get("debian")
    if not host:
        return None
    try:
        with urllib.request.urlopen(host, timeout=timeout) as response:
            return getattr(response, "status", 200) < 500
    except (urllib.error.URLError, OSError):
        return False


# ---------------------------------------------------------------------- 执行


def classify_failure(returncode: int, output: str) -> str:
    """把一次安装命令的失败归类成 ``network`` / ``permission`` / ``refresh`` / ``failed``。

    ``refresh`` 是一个特例：它不是真失败，而是「仓库索引过期，刷新一次就好了」，
    调用方据此重试而不是直接劝退用户。

    先判权限再判网络：polkit 撤销 / sudo 密码错误的输出最具体，
    且 apt 在得不到写权限时会先报一堆无关的话，顺序反了会误归因。
    """
    if returncode == 0:
        return "ok"
    blob = (output or "").lower()
    if any(marker in blob for marker in _PERM_MARKERS):
        return "permission"
    if any(marker in blob for marker in _REFRESH_MARKERS):
        return "refresh"
    if any(marker in blob for marker in _NET_MARKERS):
        return "network"
    return "failed"


def _escalation() -> list[str] | None:
    """返回提权前缀；已经是 root 返回空列表，没有可用手段返回 ``None``。

    **pkexec 优先于 sudo**：GUI 里没有终端，``sudo`` 会直接失败
    （``no tty present and no askpass program``），而 pkexec 弹的是图形授权框。
    """
    if getattr(os, "geteuid", None) and os.geteuid() == 0:
        return []
    if shutil.which("pkexec"):
        return ["pkexec"]
    if shutil.which("sudo"):
        return ["sudo"]
    return None


def _run(command: tuple[str, ...], timeout: float, on_line=None) -> tuple[int, str]:
    """跑一条命令并把输出逐行喂给 ``on_line``（用于 GUI 流式日志）。

    始终合并 stderr 到 stdout：apt/dnf 的进度、警告都在 stdout，分开读会
    让日志缺一半。apt 额外设 ``DEBIAN_FRONTEND=noninteractive``，避免它在
    没有终端的情况下卡在 debconf 提问上。
    """
    env = dict(os.environ)
    env.setdefault("DEBIAN_FRONTEND", "noninteractive")
    try:
        proc = subprocess.Popen(
            list(command), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", bufsize=1, env=env,
        )
    except OSError as exc:
        return 127, f"{exc}"
    lines: list[str] = []
    assert proc.stdout is not None
    # ⚠️ 用**读取线程 + 截止时间**读，不能 `for line in proc.stdout:`（2026-09-26
    #    审计）：那样是阻塞读到 EOF，而超时只在读完之后才生效 —— 包管理器挂起
    #    且不再输出时（保持 stdout 打开），`timeout` 形同虚设，GUI 的字体安装
    #    工作线程会**永久**卡在"安装中"。这里超时就杀进程（stdout 随之关闭、
    #    读取线程自然退出），保证调用方一定能拿到结果。
    done = threading.Event()

    def _drain() -> None:
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                stripped = line.rstrip("\n")
                lines.append(stripped)
                if on_line is not None:
                    try:
                        on_line(stripped)
                    except Exception:  # noqa: BLE001 - 回调挂了不能连累安装进程
                        pass
        finally:
            done.set()

    reader = threading.Thread(
        target=_drain, name="guji-font-install-log", daemon=True
    )
    reader.start()
    if not done.wait(timeout):
        proc.kill()
        done.wait(5)  # 等读取线程收尾，把已拿到的日志交出去
        return 124, "\n".join(lines)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    return proc.returncode, "\n".join(lines)


def _tail(text: str, limit: int = 2000) -> str:
    """截日志尾部，避免超长的 apt 输出塞爆对话框。"""
    return text[-limit:]


def install_cjk_fonts(
    packages: tuple[str, ...] | None = None,
    manager: str | None = None,
    probe_network: bool = True,
    timeout: float = 900.0,
    on_line=None,
) -> InstallResult:
    """从发行版仓库安装中文字体（Linux 专用，其它平台直接返回 ``unsupported``）。

    流程：候选包 →（apt）筛掉仓库里没有的 → 探网络 → 提权 → 逐个安装；
    中途遇到「索引过期」会先刷一次元数据再重试同一个包。任何一个包装上、
    且重新体检能在系统里找到中文字体，即返回 ``ok``。

    ``packages`` 可用来收敛到指定包（自测 / 命令行）；省略则用 `install_plan`。

    ⚠️ 本函数**会阻塞并可能弹文件外的系统授权框**（pkexec/sudo），GUI 里必须
    放进子线程，回调回控件要排队回主线程。
    """
    if platform_name() != "linux":
        return InstallResult(
            "unsupported",
            "自动安装只支持 Linux；Windows / macOS 请手动安装中文字体。",
        )

    key = manager or detect_package_manager()
    if key is None:
        return InstallResult(
            "unsupported",
            "没找到已知的包管理器（apt / dnf / yum / pacman / zypper），请手动安装。",
        )

    if packages:
        plan = tuple(p for p in install_plan(key) if p.name in packages) or tuple(
            FontPackage(name, "", "") for name in packages
        )
    else:
        plan = install_plan(key)
    if not plan:
        return InstallResult("unsupported", "该包管理器下没有登记的中文字体候选。")

    plan = available_packages(plan, key)
    names = tuple(p.name for p in plan)

    if probe_network and repo_reachable() is False:
        return InstallResult(
            "network",
            "连不上软件源，没能下载字体。（常见于离线环境或内网未配镜像）",
            tuple(_INSTALL_ARGS[key]) + names,
        )

    prefix = _escalation()
    if prefix is None:
        return InstallResult(
            "permission",
            "没有可用的提权方式（pkexec / sudo 都没有），无法写入系统目录。",
            tuple(_INSTALL_ARGS[key]) + names,
        )

    command = (*prefix, *_INSTALL_ARGS[key], *names)
    refreshed = False
    last_code, last_output = 0, ""
    installed: tuple[str, ...] = ()

    for name in names:
        current = (*prefix, *_INSTALL_ARGS[key], name)
        code, output = _run(tuple(current), timeout, on_line)
        reason = classify_failure(code, output)
        if code == 0:
            installed = (name,)
            break
        last_code, last_output, command = code, output, tuple(current)
        if reason == "refresh" and not refreshed:
            # 索引过期：刷一次元数据再重试同一个包（apt 最常见）
            refreshed = True
            refresh_cmd = tuple((*prefix, *_REFRESH_ARGS[key])) if key in _REFRESH_ARGS else ()
            if refresh_cmd:
                if on_line is not None:
                    try:
                        on_line("$ " + " ".join(refresh_cmd))
                    except Exception:
                        pass
                _run(refresh_cmd, min(timeout, 300.0), on_line)
                code, output = _run(tuple(current), timeout, on_line)
                if code == 0:
                    installed = (name,)
                    break
                last_code, last_output = code, output
        if reason in ("permission", "network"):
            break

    if not installed:
        reason = classify_failure(last_code, last_output)
        messages = {
            "permission": "授权没通过（可能被取消），字体没装上。",
            "network": "下载失败：连不上软件源。",
            "failed": "安装命令返回非零状态，请看下方的命令输出。",
        }
        return InstallResult(
            reason if reason in messages else "failed",
            messages.get(reason, messages["failed"]),
            command, _tail(last_output),
        )

    # 刷新字体缓存：fc-cache 通常被包管理器的钩子触发，但 AppImage / 极简镜像
    # 里可能没有钩子，手动补一次更稳（失败也无所谓，不影响结果）。
    if shutil.which("fc-cache"):
        _run((*prefix, "fc-cache", "-f"), 60.0, None)

    check = check_cjk_font()
    if not check.found:
        return InstallResult(
            "failed",
            f"{installed[0]} 已经装上，但系统里还没认到中文字体"
            "（可能需要注销重新登录，或把字体所在目录加入 fontconfig）。",
            command, "", installed, check,
        )
    return InstallResult("ok", f"已安装 {installed[0]}", command, "", installed, check)


# ---------------------------------------------------------------------- 手装文案


def manual_install_text(plan: tuple[FontPackage, ...] | None = None) -> str:
    """返回可直接照抄的手动安装说明（自动安装失败时给用户看）。

    内容包含三条路：包管理器装、手动放字体文件到用户目录、用环境变量指定。
    前两条按主次给出命令，最后一条是因为容器 / 精简镜像往往连 root 都没有，
    ``~/.local/share/fonts`` 是唯一不求人的路。
    """
    platform = platform_name()
    if platform == "windows":
        return (
            "Windows 一般会自带仿宋 / 宋体。若确实一个中文字体都没有：\n"
            "  1. 从其它机器复制 simfang.ttf（仿宋）到 C:\\Windows\\Fonts\\；\n"
            "  2. 或设置环境变量 GUJI_CJK_FONT 指向任意一个中文字体文件。\n"
        )

    plan = plan if plan is not None else install_plan()
    lines = ["方案 A · 用包管理器安装（推荐，自动进 fontconfig）："]
    key = detect_package_manager()
    if plan and key:
        for item in plan[:3]:
            lines.append(f"  sudo {' '.join(_INSTALL_ARGS[key])} {item.name}")
            lines.append(f"      # {item.label}")
    else:
        lines.append("  （本机没有已知的包管理器，可用方案 B / C）")

    lines += [
        "",
        "方案 B · 手动放字体文件（不需要 root）：",
        "  mkdir -p ~/.local/share/fonts",
        "  cp <你的中文字体>.ttf ~/.local/share/fonts/",
        "  fc-cache -f -v",
        "  # 想要仿宋：可从 Windows 复制 C:\\Windows\\Fonts\\simfang.ttf",
        "",
        "方案 C · 指认任意一个字体文件（容器 / CI 最省事）：",
        "  export GUJI_CJK_FONT=/path/to/simfang.ttf",
        "  # GUI 在本机重启一次后生效；命令行同一终端立即生效",
    ]
    return "\n".join(lines)
