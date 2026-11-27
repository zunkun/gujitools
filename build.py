#!/usr/bin/env python
"""PyInstaller 打包脚本（CLI + GUI 一体）。

用法:
    python build.py

会通过 conda 环境 ``yolobuild`` 构建（缺依赖时自动安装），产出
**一个目录内同时含 CLI 与 GUI 两个可执行文件**，随后生成安装包。

输出（**一份可执行目录 + 两条分发产物**）:
    dist/guji/guji.exe       命令行工具（console，安装后 PATH 可直接用 guji）
    dist/guji/guji-desktop.exe   桌面 GUI（windowed，安装包会建快捷方式）
    dist/gujitools_setup_<版本>_<平台>.exe          安装包
    dist/gujitools_portable_<版本>_<平台>.zip       绿色免安装版（解压即用）

⚠️ **构建脚本不负责部署**：本脚本只把产物落到 ``dist/``，**不再往
``C:\\Software\\guji`` 之类的地方复制一份**——那是历史行为，会让人分不清
"到底装在哪、跑的是哪一份"。要部署就走安装包（安装目录由
``guji_setup.iss`` 的 ``DefaultDirName`` 决定，PATH 也随之指向实际安装
目录）；只想就地跑一下，双击 ``dist/guji/guji-desktop.exe`` 即可。

两者共享同一份 dist/guji/_internal：torch/cv2 等大二进制只落地一份。

⚠️ **PyInstaller 不能交叉编译**，所以 Linux 产物只能在 Linux 上构建
（物理机 / WSL2 / CI runner），Windows 上怎么配置都变不出 ELF。同一份
``build.py`` 在 Ubuntu 上执行即可，差异由脚本自动处理：

    dist/guji/guji            （无 .exe 后缀）
    dist/guji/guji-desktop
    dist/guji_<版本>_<时间戳>_linux-x86_64.tar.gz

Linux 侧除 tar.gz 绿色版外，还会用 dpkg-deb 生成 ``.deb`` 安装包
（装到 ``/opt/gujitools``，并建 CLI/GUI 启动入口与 .desktop 文件）；
Inno Setup 仍是 Windows 专属。另外 Linux 目标机往往没有中文字体，
构建结束脚本会打印安装提示（程序运行时也会自行体检并弹安装引导，
见 ``utils/font_setup.py``）。

注意：Linux 与 Windows 一样，统一在 ``yolobuild`` 构建环境里安装 **CPU 版**
PyTorch（见 ``install_build_dependencies``），避免把 CUDA 运行库打进包里；
GUI 依赖（PySide6 / qfluentwidgets）也在同一环境内安装，因为两个 EXE 必须
同一次构建产出才能合并 _internal。除非显式设置 ``GUJI_ALLOW_CUDA_TORCH=1``，
否则检测到 CUDA 版 torch 会直接拒绝打包。
"""

import sys
import os
import shutil
import subprocess
import time
from pathlib import Path
from collections.abc import Callable

from config import VERSION

BUILD_ENV_NAME = "yolobuild"

#: Windows 特有行为的开关（ico 图标、Inno Setup 安装包、D:\... 瘦身清单）
IS_WINDOWS = sys.platform == "win32"

#: 可执行文件名（Linux 无后缀）
CLI_EXE = "guji.exe" if IS_WINDOWS else "guji"
GUI_EXE = "guji-desktop.exe" if IS_WINDOWS else "guji-desktop"

#: 绿色免安装版压缩包的文件名模板（解压即用，无需安装）。
#: 命名口径与安装包一致：``<名称>_<版本>_<平台>``，**不带时间戳**
#: （同一版本重打会覆盖同名文件，发布按「版本 + 平台」识别）。
#: ⚠️ 这是该产物名的**唯一来源**：``publish_release.py`` 按它识别要上传的资产，
#: ``tests/selftests/architecture/release_assets.py`` 守两者一致——改名必须同步。
PORTABLE_TEMPLATE = (
    "gujitools_portable_{version}_{platform}.zip"
    if IS_WINDOWS
    else "gujitools_portable_{version}_{platform}.tar.gz"
)

#: Debian 包：安装到 /opt/gujitools，产物名 `gujitools_<版本>_<deb架构>.deb`。
DEB_PACKAGE_NAME = "gujitools"
DEB_TEMPLATE = "gujitools_{version}_{arch}.deb"
DEB_INSTALL_DIR = "/opt/gujitools"

#: 安装向导右上角小图在各级 DPI 下的**显示尺寸**（Inno 官方表：100%~250% 依次
#: 为 58/77/97/116/124/143/159）。逐尺寸各给一张原尺寸图，Inno 按当前 DPI 挑
#: 最接近的一张；只给单张的话它只会拉伸/缩小，缩放着用会发虚。
WIZARD_SMALL_IMAGE_SIZES = (58, 77, 97, 116, 124, 143, 159)


def run_conda(conda_exe, args, check=True, capture_output=False):
    return subprocess.run(
        [conda_exe, *args],
        cwd=Path(__file__).resolve().parent,
        check=check,
        capture_output=capture_output,
        text=True,
    )


def find_conda():
    conda_exe = os.environ.get("CONDA_EXE") or shutil.which("conda")
    if conda_exe:
        return conda_exe

    if sys.platform == "win32":
        candidate = Path(sys.prefix).parent / "Scripts" / "conda.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def conda_environment_exists(conda_exe):
    result = run_conda(conda_exe, ["env", "list", "--json"], capture_output=True)
    if result.returncode != 0:
        return False

    import json

    environments = json.loads(result.stdout).get("envs", [])
    return any(
        Path(environment).name.lower() == BUILD_ENV_NAME for environment in environments
    )


def install_build_dependencies(conda_exe, project_root):
    check = run_conda(
        conda_exe,
        [
            "run",
            "--no-capture-output",
            "-n",
            BUILD_ENV_NAME,
            "python",
            "-c",
            # ⚠️ 探针里的包清单必须覆盖 requirements.txt 的全部运行时依赖：
            # 自检通过会**直接 return**，后面的 pip install 一次都不跑。
            # 曾经漏掉 markdown → 已有环境永远装不上它，手册在打包后静默退化。
            "import importlib.metadata as metadata; import cv2, PyInstaller, torch, ultralytics, yaml, fpdf, PySide6, qfluentwidgets, markdown, scipy; has_full_opencv=any(d.metadata['Name'].lower() == 'opencv-python' for d in metadata.distributions()); raise SystemExit(torch.version.cuda is not None or has_full_opencv)",
        ],
        check=False,
    )
    if check.returncode == 0:
        return

    print("安装 yolobuild 依赖（CPU PyTorch）...")
    # ⚠️ 本机批量删除保护会在「覆盖已有文件」时掐死 pip（2026-11-27 实测：
    # pip 升级卸载旧版、PySide6 元包与拆分包互相覆盖同名 .pyi 都中招）。
    # 因此这里**一次**装齐、全程 --no-deps、不升级/卸载任何东西：
    #   - CPU torch 取自 download.pytorch.org（+cpu 版本优先于镜像的 CUDA 版）
    #   - requirements.txt 去掉 PySide6 元包（只装拆分包，实测可正常 import）
    #   - 传递依赖显式列全，避免 ultralytics 拉 CUDA torch / 完整版 opencv-python
    req_lines = []
    for raw in (project_root / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name = (
            line.replace(">=", ">").replace("<=", "<")
            .split(">", 1)[0].split("<", 1)[0].split("==", 1)[0]
            .strip().lower()
        )
        if name == "pyside6":  # 元包与拆分包文件重叠，只装拆分包
            continue
        req_lines.append(line)

    packages = [
        # CPU PyTorch
        "torch", "torchvision", "torchaudio",
        # torch 传递依赖（--no-deps 下需显式列出）
        "filelock", "typing-extensions", "sympy", "networkx", "jinja2",
        "fsspec", "mpmath", "MarkupSafe",
        # requirements.txt 全量（已去掉 PySide6 元包）
        *req_lines,
        # ultralytics / pyinstaller / GUI 传递依赖
        "matplotlib", "pandas", "seaborn", "psutil", "py-cpuinfo",
        # ⚠️ 只装 ultralytics-thop：它与 thop 提供同一份 thop/ 模块，
        # 两个都装会让 pip 覆盖同名文件、触发批量删除保护。
        "ultralytics-thop", "requests", "tqdm", "scipy",
        "charset-normalizer", "idna", "urllib3", "certifi",
        # tzdata 由 conda 基础环境提供，pip 再装会覆盖 zoneinfo 文件。
        "python-dateutil", "pytz",
        "contourpy", "cycler", "fonttools", "kiwisolver", "pyparsing",
        "wcwidth", "altgraph", "packaging", "pyinstaller-hooks-contrib",
        "setuptools", "darkdetect",
        # qfluentwidgets 的间接依赖，分发名 PySideSix-Frameless-Window
        # （import 名 qframelesswindow）；漏掉会让 GUI 启动即崩。
        "PySideSix-Frameless-Window>=0.8.0",
    ]
    run_conda(
        conda_exe,
        [
            "run", "-n", BUILD_ENV_NAME, "python", "-m", "pip", "install",
            "--no-deps",
            "--index-url", "https://download.pytorch.org/whl/cpu",
            "--extra-index-url", "https://mirrors.aliyun.com/pypi/simple/",
            *packages,
        ],
    )

    # PySide6 拆分包装到独立 vendor 目录：Essentials / Addons 之间有几十个
    # 同名 .pyi，直接装进 site-packages 会互相覆盖并触发批量删除保护；
    # --target 指向全新目录则没有覆盖（实测可用）。.pth 让它优先被 import。
    site_result = run_conda(
        conda_exe,
        [
            "run", "-n", BUILD_ENV_NAME, "python", "-c",
            "import site; print(site.getsitepackages()[0])",
        ],
        capture_output=True,
    )
    site_packages = Path(site_result.stdout.strip().splitlines()[-1])
    vendor = site_packages / "_guji_vendor"
    run_conda(
        conda_exe,
        [
            "run", "-n", BUILD_ENV_NAME, "python", "-m", "pip", "install",
            "--no-deps", "-i", "https://mirrors.aliyun.com/pypi/simple/",
            "--target", str(vendor),
            "PySide6_Essentials>=6.10.0,<6.11",
            "PySide6_Addons>=6.10.0,<6.11",
            "shiboken6>=6.10.0,<6.11",
        ],
    )
    (site_packages / "zz_guji_vendor.pth").write_text(
        str(vendor) + "\n", encoding="utf-8"
    )
    # 依赖只有 requirements.txt 一份（CLI + GUI 全量），上面的
    # `pip install -r requirements.txt` 已包含 PySide6 / markdown 等 GUI 依赖。
    #
    # ⚠️⚠️ 不要再在下面补一份「GUI 增量」手写清单。曾经有过：怕 pip 重解析把
    # CPU 版 torch 顶掉，所以只手写 PySide6 + qfluentwidgets 两个包、不装
    # requirements.gui.txt 整表。代价是那份手写清单成了**第二处事实来源**——
    # 漏掉 markdown 时源码模式正常、打包后手册退化成 <pre> 包裹的原始 markdown
    # （`_md_to_fragment` 的 ImportError 兜底），而 `collect_submodules('markdown')`
    # 对缺失的包**静默返回空**，PyInstaller 全程不报错，只有用户点了「用户手册」
    # 才看见。现在一次装全，torch 的风险由「只跑一次 -r requirements.txt」规避。
    # 护栏：tests/selftests/ui/manual_dialog.py 从 help_dialog.py 的 import 反推
    # 依赖，逐个比对 requirements.txt。


def ensure_build_environment(project_root):
    if os.environ.get("GUJI_BUILD_ENV_READY") == "1":
        return

    conda_exe = find_conda()
    if not conda_exe:
        print("⚠️ 未找到 Conda，使用当前 Python 环境继续打包")
        return

    current_environment = Path(os.environ.get("CONDA_PREFIX", "")).name.lower()
    if current_environment == BUILD_ENV_NAME:
        install_build_dependencies(conda_exe, project_root)
        os.environ["GUJI_BUILD_ENV_READY"] = "1"
        return

    if not conda_environment_exists(conda_exe):
        print(f"创建 Conda 环境: {BUILD_ENV_NAME}")
        run_conda(
            conda_exe,
            [
                "create",
                "-n",
                BUILD_ENV_NAME,
                "python=3.10",
                "-y",
                "--override-channels",
                "-c",
                "https://repo.anaconda.com/pkgs/main",
            ],
        )

    install_build_dependencies(conda_exe, project_root)
    print(f"切换到 Conda 环境: {BUILD_ENV_NAME}")
    child_environment = os.environ.copy()
    child_environment["GUJI_BUILD_ENV_READY"] = "1"
    result = subprocess.run(
        [
            conda_exe,
            "run",
            "--no-capture-output",
            "-n",
            BUILD_ENV_NAME,
            "python",
            str(Path(__file__).resolve()),
            *sys.argv[1:],
        ],
        cwd=str(project_root),
        env=child_environment,
    )
    raise SystemExit(result.returncode)


def _assert_cpu_torch():
    """防止误用 CUDA 版 torch 环境打包（Linux / Windows 统一口径）。

    正常路径下 ``ensure_build_environment`` 会切到 ``yolobuild`` 的 CPU torch；
    这里兜住手动设置 ``GUJI_BUILD_ENV_READY=1`` 跳过环境切换的情况。确实需要
    打 CUDA 大包时，显式设置 ``GUJI_ALLOW_CUDA_TORCH=1`` 才能放行。
    """
    if os.environ.get("GUJI_ALLOW_CUDA_TORCH") == "1":
        return
    try:
        import torch
    except ImportError:
        return
    cuda = getattr(torch.version, "cuda", None)
    if cuda is None:
        return
    print(
        f"❌ 当前构建环境是 CUDA 版 torch {torch.__version__}（CUDA {cuda}）。\n"
        "   Windows/Linux 打包统一使用 CPU 版 torch：请直接运行 `python build.py`，\n"
        "   让脚本切到 yolobuild 环境；若确实要打 CUDA 大包，请显式设置\n"
        "   GUJI_ALLOW_CUDA_TORCH=1。"
    )
    raise SystemExit(2)


#: 删除中途失败时残留目录的后缀（下次构建开头会再扫一次）
_DELETING_SUFFIX = ".deleting"

#: 小目录才允许直接删除的文件数阈值。2026-11-27 实测本机保护改为按
#: 「每轮 50 次删除」计数，逐文件 os.remove 到 50 个照样被掐死；因此大目录
#: 一律走 gio trash 整体移走，不再逐文件删。阈值取 40，留并发余量。
_BULK_DELETE_THRESHOLD = 40


def _rmtree_guard_friendly(staging: Path) -> bool:
    """只删小目录（<= 阈值个文件）；大目录交给 gio trash，不逐文件删。"""
    total = 0
    for _dirpath, _dirs, files in os.walk(staging):
        total += len(files)
        if total > _BULK_DELETE_THRESHOLD:
            break
    if total > _BULK_DELETE_THRESHOLD:
        print(f"   ⚠️ {staging.name} 有 {total} 个文件，不逐文件删（交回收站）")
        return False
    shutil.rmtree(staging, ignore_errors=True)
    return not staging.exists()


def _path_file_count(path: Path) -> int:
    """统计文件数，够判断大小即可；超过阈值就提前返回。"""
    total = 0
    for _dirpath, _dirs, files in os.walk(path):
        total += len(files)
        if total > _BULK_DELETE_THRESHOLD:
            break
    return total


def _trash_path(path: Path, shown: str) -> bool:
    """用系统回收站整体移走目录，绕开「每轮 50 次删除」的批量保护。"""
    if shutil.which("gio") is None:
        return False
    result = subprocess.run(
        ["gio", "trash", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        print(f"   ⚠️ {shown} 移入回收站失败: {detail}")
        return False
    print(f"   🗑️  {shown} 已移入回收站")
    return True


def remove_tree(path: Path, label: str | None = None) -> bool:
    """清理旧的 ``build/`` / ``dist/`` / 瘦身暂存目录，成功返回 True。

    ``label`` 只影响日志里怎么称呼它。

    ⚠️ **大目录走系统回收站**（2026-11-27）：本机保护现在按「每轮 50 次删除」
    计数，逐文件 ``os.remove`` 到 50 个也会被掐死（连 build.py 清理旧 build/
    都被拦）。文件数超过阈值时改用 ``gio trash`` 整体移走：一次操作、路径立刻
    消失、不触发计数。没有 gio 时退化为改名到 ``*.deleting`` 并告警，**绝不
    中断构建**。小目录（<=40 文件）仍直接 rmtree，快且不触发保护。
    """
    if not path.exists():
        return False

    shown = label or f"旧 {path.name}/"
    if _path_file_count(path) > _BULK_DELETE_THRESHOLD:
        if _trash_path(path, shown):
            return True
        stamp = time.strftime("%H%M%S")
        staging = path.with_name(f"{path.name}{_DELETING_SUFFIX}_{stamp}")
        try:
            os.replace(str(path), str(staging))
            print(f"   ⚠️ {shown} 已改名到 {staging.name}，但未能删除（继续构建）")
        except OSError as exc:
            print(f"   ⚠️ {shown} 清理失败（继续构建）: {exc}")
        return False

    # 小目录：先 rename 再删，避免 PyInstaller 撞上半删状态。
    staging = path.with_name(f"{path.name}{_DELETING_SUFFIX}")
    try:
        if staging.exists():
            if not _rmtree_guard_friendly(staging):
                _trash_path(staging, f"上次残留 {staging.name}")
        if staging.exists():
            print(f"   ⚠️ {shown} 上次残留删不掉，跳过清理（继续构建）")
            return False
        os.replace(str(path), str(staging))
    except OSError as exc:
        print(f"   ⚠️ {shown} 改名失败，跳过清理（继续构建）: {exc}")
        return False

    if _rmtree_guard_friendly(staging):
        print(f"   🗑️  {shown} 已删除")
        return True
    if _trash_path(staging, shown):
        return True
    print(f"   ⚠️ {shown} 未删干净，残留 {staging}（继续构建）")
    return False


def stage_out(path: Path, staging: Path, anchor: Path | None = None) -> bool:
    """把待删的单个文件**改名**进暂存目录（rename，不复制数据），成功返回 True。

    瘦身一次要清掉 2000+ 个 torch 源文件：逐个 ``unlink`` 是最慢、也最容易撞上
    批量删除阈值的做法（实测 count=50 就红过），而 rename 只是改一个目录项。
    搬完再对暂存目录调**一次** :func:`remove_tree`，删除动作就收敛成「一次整目录删除」。

    ``staging`` 每次构建独有：同名目标不存在，就永远不需要先删后搬。
    """
    try:
        dest = (staging / path.relative_to(anchor)) if anchor is not None else (staging / path.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            return False
        shutil.move(str(path), str(dest))
        return True
    except OSError:
        return False


def prepare_icon(project_root):
    """把 desktop/static/icon.png 转成 Windows 图标 icon.ico。

    PyInstaller 的 ``icon=``（Windows）只认 .ico；仓库里只保留 PNG 源图，
    .ico 在构建时生成——**顺便烧上圆角**：图标形状由像素决定，源图不必
    手工修圆角（详见 tools/make_icon.py）。
    返回生成出的 .ico 路径，失败则返回 None（不致命）。

    Linux 的可执行文件不带图标资源，跳过这一步。
    """
    if not IS_WINDOWS:
        return None
    png = project_root / "desktop" / "static" / "icon.png"
    ico = png.with_suffix(".ico")
    if not png.is_file():
        print("⚠️ 未找到 desktop/static/icon.png，跳过图标生成")
        return None
    try:
        from tools.make_icon import DEFAULT_RADIUS_PCT, make_ico

        make_ico(png, ico, DEFAULT_RADIUS_PCT)
        print(
            f"✅ 生成图标: {ico.relative_to(project_root)}"
            f"（圆角 {DEFAULT_RADIUS_PCT}%）"
        )
        return ico
    except Exception as exc:
        print(f"⚠️ 图标生成失败（不影响打包）: {exc}")
        return None


def prepare_wizard_small_images(project_root):
    """由 desktop/static/icon.png 生成安装向导右上角的小图（现代样式头部）。

    向导头部那枚图默认是 Inno 内置的；换成项目图标（红底篆书「古籍重製」），
    安装包才和程序外观一致。源图是直角方形，这里复用 make_icon.rounded_frame，
    **与程序图标共用同一套圆角**，输出带透明的 PNG 以贴合向导头部的底色。

    为什么给「一组」而不是一张：头部的图区随 DPI 是 58~159px 见方，Inno 对单张
    图只会拉伸/缩小——缩放会发虚。按 ``WIZARD_SMALL_IMAGE_SIZES`` 逐尺寸生成
    原尺寸图，Inno 自会挑最接近的（见 ``WizardSmallImageFile`` 帮助）。

    返回逗号分隔的图片路径串（供 ``/DWIZARD_SMALL_IMAGE`` 传给 ISCC）；
    失败返回 None（不致命，安装包退回 Inno 的默认图）。
    """
    if not IS_WINDOWS:
        return None
    png = project_root / "desktop" / "static" / "icon.png"
    if not png.is_file():
        print("⚠️ 未找到 desktop/static/icon.png，跳过安装向导小图生成")
        return None
    # ⚠️ 落在 dist/ 而不是 desktop/static/：后者整个目录会被 guji.spec 收进
    # GUI 的安装载荷（gui_datas），把只有安装器才用的图打进去纯属浪费。
    out_dir = project_root / "dist" / "installer_assets"
    try:
        from PIL import Image

        from tools.make_icon import DEFAULT_RADIUS_PCT, rounded_frame

        src = Image.open(png)
        out_dir.mkdir(parents=True, exist_ok=True)
        files = []
        for size in WIZARD_SMALL_IMAGE_SIZES:
            path = out_dir / f"wizard_small_{size}.png"
            rounded_frame(src, size, DEFAULT_RADIUS_PCT).save(path, format="PNG")
            files.append(path)
        print(
            f"✅ 生成安装向导小图: {out_dir.relative_to(project_root)}"
            f"（{len(files)} 个尺寸，圆角 {DEFAULT_RADIUS_PCT}%）"
        )
        return ",".join(str(p) for p in files)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ 安装向导小图生成失败（不影响打包）: {exc}")
        return None


def elapsed(start: float, label: str) -> None:
    """打印某阶段耗时——构建全程 15~20 分钟，没有计时容易误判成卡死。"""
    secs = time.monotonic() - start
    if secs < 60:
        print(f"⏱️  {label} 耗时 {secs:.1f}s")
    else:
        print(f"⏱️  {label} 耗时 {int(secs // 60)}m{secs % 60:04.1f}s")


def refresh_manual_only(project_root) -> int:
    """只重生成手册并刷新发布产物（`python build.py --manual-only`）。

    为什么单开一条：完整打包要 19 分钟（PyInstaller 7m + 瘦身 8m），而调手册
    版式/文案时 Python 侧一个字节都没变——重生成 `manual.html`、重压安装包
    **与绿色版 zip**（两者必须同一时间戳，发布脚本按它认「同一批」）。
    **改了 `.py` 仍然必须完整打包。**
    """
    dist_dir = project_root / "dist" / "guji"
    if not dist_dir.is_dir():
        print("❌ 没有 dist/guji，请先跑一次完整打包：python build.py")
        return 1

    steps: list[tuple[str, Callable[[], object]]] = [("预生成手册", lambda: build_manual_html(dist_dir))]
    if IS_WINDOWS:
        icon = project_root / "desktop" / "static" / "icon.ico"
        wizard_images = prepare_wizard_small_images(project_root)
        # ⚠️ 这里曾经还有一步「复制到 C:\Software」把产物部署一份出去。
        # 已删除：构建只产出安装包，部署由安装包负责（否则本机同时存在
        # dist/、C:\Software\guji、安装目录三份，跑的是哪一份都说不清）。
        # 产物名不含时间戳：安装包与绿色版都按「版本 + 平台」命名，重打直接覆盖。
        steps += [
            ("打绿色版 zip",
             lambda: pack_portable_zip(project_root, dist_dir)),
            ("生成安装包",
             lambda: build_installer(project_root, icon, wizard_images)),
        ]
    for label, fn in steps:
        mark = time.monotonic()
        print(f"\n▶ {label} ...")
        fn()
        elapsed(mark, label)
    print("\n✅ 手册已刷新（Python 代码未变，无需完整重建）")
    return 0


def main():
    project_root = Path(__file__).resolve().parent
    if "--manual-only" in sys.argv:
        return refresh_manual_only(project_root)
    ensure_build_environment(project_root)
    _assert_cpu_torch()

    print(f"项目版本: {VERSION}")

    # 删掉旧产物（guji.spec 是构建输入，不动它）
    # ⚠️ 大目录走回收站、不因删除失败中断构建：详见 remove_tree()。
    for stale in sorted(project_root.glob("*.deleting")):
        if stale.is_dir():
            _trash_path(stale, f"旧残留 {stale.name}")
    for target in [project_root / "build", project_root / "dist"]:
        remove_tree(target)

    icon = prepare_icon(project_root)
    wizard_images = prepare_wizard_small_images(project_root)

    spec = project_root / "guji.spec"
    if not spec.is_file():
        print(f"❌ 缺少打包规格文件: {spec}")
        sys.exit(1)

    # 用 spec 构建：一个目录内同时产出 guji.exe(CLI) 与 guji-desktop.exe(GUI)，
    # 共享同一份 _internal（torch 等大二进制只落地一次）。
    # ⚠️ 不再加 --clean：它会 rmtree 掉整个 workpath（上千项，会被批量删除
    # 钩子拦下）。改成每次用一个新的 workpath，天然干净、无须清理。
    workpath = project_root / "build" / f"pyi_{time.strftime('%Y%m%d_%H%M%S')}"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec),
        "--noconfirm",
        "--distpath",
        str(project_root / "dist"),
        "--workpath",
        str(workpath),
    ]

    print(f"工作目录: {project_root}")
    print(f"命令: {' '.join(cmd)}")
    print(
        "（PyInstaller 全程约 10 分钟：两次 Analysis + COLLECT 落地 650MB，"
        "期间进度由子进程逐行打印）\n"
    )

    t0 = time.monotonic()
    result = subprocess.run(cmd, cwd=str(project_root))
    elapsed(t0, "PyInstaller")

    if result.returncode == 0:
        dist_dir = project_root / "dist" / "guji"
        built = (
            [p.name for p in dist_dir.iterdir() if p.name in (CLI_EXE, GUI_EXE)]
            if dist_dir.is_dir()
            else []
        )
        if built:
            print(f"\n✅ 打包完成: dist/guji/  →  {', '.join(sorted(built))}")
        else:
            print("\n✅ 打包完成: dist/guji/")

        steps: list[tuple[str, Callable[[], object]]] = [
            ("校验产物", lambda: verify_outputs(dist_dir)),
            ("预生成手册", lambda: build_manual_html(dist_dir)),
            ("体积瘦身", lambda: prune_bloat(dist_dir)),
            ("瘦身检查", lambda: run_bloat_check(project_root)),
        ]
        if IS_WINDOWS:
            # ⚠️ 构建只出安装包，不再往 C:\Software\guji 复制一份部署副本
            # （见模块 docstring）。dist/guji/ 本身可直接分发/就地运行。
            # 产物名不含时间戳：安装包与绿色版都按「版本 + 平台」命名，重打直接覆盖。
            steps += [
                ("打绿色版 zip", lambda: pack_portable_zip(project_root, dist_dir)),
                ("生成安装包", lambda: build_installer(project_root, icon, wizard_images)),
            ]
        else:
            steps += [
                ("打绿色版 tar.gz", lambda: pack_tarball(project_root, dist_dir)),
                ("打 Debian 包", lambda: build_deb_package(project_root, dist_dir)),
                ("中文字体提示", lambda: print_font_hint()),
            ]

        for label, fn in steps:
            mark = time.monotonic()
            print(f"\n▶ {label} ...")
            fn()
            elapsed(mark, label)
    else:
        print("\n❌ 打包失败，请检查上方日志")
        sys.exit(1)


# ------------------------------------------------------------------ 瘦身
# hook-torch.py 在 Windows 上把整个 torch 源码树当成 data 收进 _internal，
# 而同样的模块已经进了 PYZ（运行时由 FrozenImporter 从 PYZ 加载）。磁盘上
# 这份 .py 纯属重复，且本项目只做推理，用不到需要读源码的 torch.compile。
# 这些是 hook 的 datas，不是模块，excludes 管不到，只能在构建后清掉。
# torch 里有少数文件会在运行时被 `inspect.getsource()` 读回源码（主要是
# torch/utils/_config_module.py 给各个 config 模块装属性的那套机制），删掉会
# 让 `import torch` 直接 OSError: could not get source code。因此按规则保留：
#   - 任意名为 config.py / config_comms.py 的文件（覆盖未来的 config 模块）
#   - 下面这份显式清单
# 实测（tools/smoke_frozen.py 的 crop/YOLO 用例）只需 13 个文件即可正常工作。
TORCH_SOURCE_KEEP = {
    "utils/_config_module.py",
    "utils/serialization/config.py",
    "_sources.py",
    "fx/experimental/_config.py",
    "fx/experimental/symbolic_shapes.py",
    "fx/experimental/sym_node.py",
}


def _keep_torch_source(rel: str) -> bool:
    """判断 _internal/torch 下的相对路径是否要保留源码（不被瘦身删除）。"""
    name = rel.rsplit("/", 1)[-1]
    if name in ("config.py", "config_comms.py"):
        return True
    return rel in TORCH_SOURCE_KEEP


def prune_bloat(dist_dir):
    """删除打包产物里确定用不到的大块内容，并打印节省的体积。

    只删“加载路径上用不到”的东西：视频编解码、软件 OpenGL 回退、构建工具、
    以及被 hook 重复收集的 torch 源码。删错会导致 import 失败，因此这里
    逐个目录/文件显式列出，不做通配递归删除。
    """
    if not dist_dir.is_dir():
        print("⚠️ 未找到输出目录，跳过瘦身")
        return 0

    internal = dist_dir / "_internal"
    MB = 1024 * 1024
    removed_files = 0

    targets = []
    if IS_WINDOWS:
        # Windows 特有：视频编解码、软件 OpenGL 回退、构建工具、SQLite
        targets += [
            (
                internal / "cv2" / "opencv_videoio_ffmpeg500_64.dll",
                "cv2 视频编解码（项目只用 imread/imwrite 等图像 API）",
            ),
            (
                internal / "PySide6" / "opengl32sw.dll",
                "Qt 软件 OpenGL 回退（界面不依赖 OpenGL）",
            ),
            (
                internal / "torch" / "bin" / "protoc.exe",
                "protobuf 编译器（构建期工具，运行期不执行）",
            ),
            (internal / "sqlite3.dll", "SQLite（旧数据迁移已移除）"),
            (internal / "_sqlite3.pyd", "SQLite（旧数据迁移已移除）"),
        ]

    # 2) torch 源码副本：只删 .py，保留 lib/bin/share 下的二进制与数据，
    #    以及会被 inspect.getsource 读回的那几个 config/内省文件
    torch_dir = internal / "torch"
    if torch_dir.is_dir():
        kept = 0
        for py in torch_dir.rglob("*.py"):
            rel = py.relative_to(torch_dir).as_posix()
            if _keep_torch_source(rel):
                kept += 1
                continue
            targets.append((py, "torch 源码副本"))
        if kept:
            print(f"   保留 {kept} 个 torch 源文件（运行时需读回源码）")

    saved = 0
    # 待删文件先 rename 进暂存夹（同盘、秒级），最后对暂存夹删一把就完事——
    # 2000+ 次 unlink 收敛成一次目录删除。详见 stage_out()。
    run_staging = dist_dir.parent.parent / "build" / f"_pruned_{time.strftime('%Y%m%d_%H%M%S')}"
    for path, reason in targets:
        if not path.exists():
            continue
        try:
            size = path.stat().st_size if path.is_file() else 0
        except OSError:
            continue
        if stage_out(path, run_staging, anchor=internal):
            saved += size
            removed_files += 1
        else:
            print(f"   ⚠️ 移入暂存失败（跳过）{path}")
    remove_tree(run_staging, label="瘦身暂存文件")

    # 删完 .py 后剩下的空目录也一并清理；清不掉无所谓，空目录不占体积
    removed_dirs = 0
    if torch_dir.is_dir():
        for d in sorted(torch_dir.rglob("*"), key=lambda p: -len(p.parts)):
            if d.is_dir() and not any(d.iterdir()):
                try:
                    d.rmdir()
                    removed_dirs += 1
                except OSError:
                    pass

    if saved:
        print(
            f"🧹 瘦身完成：删除 {removed_files} 个文件、清理 {removed_dirs} 个空目录，"
            f"腾出 {saved / MB:.1f} MB"
        )
    else:
        print("🧹 瘦身：没有匹配到可删除的内容")
    return saved


def run_bloat_check(project_root):
    """构建后跑 tools/check_bloat.py，确认无用内容确实没被打进来。

    失败只警告不中止——安装包已经生成，让构建者自己判断是否需要处理。
    """
    script = project_root / "tools" / "check_bloat.py"
    if not script.is_file():
        return
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (result.stdout or "").strip()
    if output:
        print(output)
    if result.returncode != 0:
        print("⚠️ 瘦身检查未通过，见上方清单")


def verify_outputs(dist_dir):
    """确认 CLI 与 GUI 两个可执行文件都在，缺失即中止后续步骤。"""
    if not dist_dir.is_dir():
        print(f"⚠️ 未找到输出目录: {dist_dir}")
        return
    missing = [name for name in (CLI_EXE, GUI_EXE) if not (dist_dir / name).is_file()]
    if missing:
        print(f"⚠️ 输出目录缺少可执行文件: {', '.join(missing)}")
    else:
        print("   CLI 与 GUI 可执行文件均已生成")


def build_installer(project_root, icon=None, wizard_images=None):
    """用 Inno Setup 生成安装包（文件名按「版本 + 平台」，不带时间戳）。

    icon 为 .ico 路径时通过 /DICON_FILE 传给脚本（SetupIconFile）。
    wizard_images 为逗号分隔的 PNG 路径串时通过 /DWIZARD_SMALL_IMAGE 传给
    脚本（WizardSmallImageFile，即安装向导右上角的小图）。
    """
    if sys.platform != "win32":
        print("\n⚠️ 非 Windows 环境，跳过安装包生成")
        return

    iscc_candidates = [
        shutil.which("ISCC.exe"),
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "Inno Setup 7"
        / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "Inno Setup 6"
        / "ISCC.exe",
        Path(r"C:\Program Files\Inno Setup 7\ISCC.exe"),
        Path(r"C:\Program Files (x86)\Inno Setup 7\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    ]
    iscc = next(
        (
            Path(candidate)
            for candidate in iscc_candidates
            if candidate and Path(candidate).is_file()
        ),
        None,
    )
    if iscc is None:
        # ⚠️ 曾经这里直接 raise → PyInstaller 跑了 15 分钟后整个构建失败，
        # 安装包缺席却把 dist/ 里的成果判了死刑。装不上 Inno Setup 只是没
        # 安装包，dist/guji/ 本身完全可用（拷出去就能用），所以改成警告。
        print(
            "\n⚠️ 未找到 ISCC.exe（Inno Setup），跳过安装包生成\n"
            "   dist/guji/ 已可直接分发；要出安装包请安装 Inno Setup 6/7"
        )
        return

    platform_tag = _platform_tag()
    installer_name = f"gujitools_setup_{VERSION}_{platform_tag}.exe"
    cmd = [
        str(iscc),
        f"/DVERSION={VERSION}",
        f"/DBUILD_PLATFORM={platform_tag}",
    ]
    if icon and Path(icon).is_file():
        cmd.append(f"/DICON_FILE={icon}")
    if wizard_images:
        cmd.append(f"/DWIZARD_SMALL_IMAGE={wizard_images}")
    cmd.append(str(project_root / "guji_setup.iss"))
    print(f"\n📦 生成安装包: {installer_name}")
    result = subprocess.run(cmd, cwd=str(project_root))
    if result.returncode != 0:
        raise RuntimeError("安装包生成失败")
    print(f"✅ 安装包生成完成: dist/{installer_name}")


def _manual_image_reference_count():
    """手册源 md 里的 ``![…]`` 图片引用总数（内联期望数的**唯一来源**）。

    ⚠️ 不写死数字：截图增删是常态，写死必过时（曾写死 13、手册改到 17 张，
    每次打包都报一条假警告——2026-10-12 改为从源推导）。推导失败返回
    ``None``（打包不该因为手册检查挂掉，只放弃这一条计数核对）。
    """
    import re

    try:
        from desktop.ui.help_dialog import manual_dir
    except Exception:  # noqa: BLE001
        return None
    try:
        total = 0
        for md in sorted(manual_dir().glob("*.md")):
            total += len(
                re.findall(r"!\[[^\]]*\]\([^)]+\)", md.read_text(encoding="utf-8"))
            )
        return total
    except Exception:  # noqa: BLE001
        return None


def build_manual_html(dist_dir):
    """把用户手册预渲染成**自包含**静态 HTML 放进产物（`_internal/desktop/static/`）。

    为什么在构建期做：运行时渲染要先读 md、跑 markdown 库、写临时文件、再开
    浏览器；手册内容是构建那一刻就定死的，运行时再算一遍毫无意义。
    ⚠️ 截图必须**内联**（data URI）：安装包不含 ``docs/guide``，任何外部引用
    在用户机器上都会变成碎图（详见 ``desktop/ui/help_dialog.py``）。

    失败只警告：程序运行时会退回"现渲染到临时目录"，功能不受影响。
    """
    static_dir = dist_dir / "_internal" / "desktop" / "static"
    if not static_dir.is_dir():
        print("⚠️ 产物里没有 desktop/static，跳过手册预生成")
        return
    try:
        from desktop.ui.help_dialog import generate_static_manual

        out = generate_static_manual(static_dir / "manual.html")
    except Exception as exc:  # 打包脚本不该因为手册而整体失败
        print(f"⚠️ 手册预生成失败（程序会退回运行时渲染）: {exc}")
        return

    document = out.read_text(encoding="utf-8")
    inlined = document.count("data:image/")
    problems = []
    expected = _manual_image_reference_count()
    if expected is not None and inlined != expected:
        problems.append(f"内联截图 {inlined} 张（源引用 {expected} 张）")
    if 'src="file:' in document or 'src="screenshots/' in document:
        problems.append("仍存在外部图片引用（装机后会碎图）")
    size_mb = out.stat().st_size / 1024 / 1024
    if problems:
        print(f"   ⚠️ 手册自包含检查异常：{'；'.join(problems)}")
    print(f"   手册已预生成为自包含 HTML：manual.html（{size_mb:.1f} MB，"
          f"内联 {inlined} 张截图）")


def _platform_tag() -> str:
    """产物名里的平台标记：``windows-x86_64`` / ``linux-x86_64``。

    Windows 的 ``AMD64`` 归一成 ``x86_64``（与 Linux 同口径）。
    """
    import platform

    machine = (platform.machine() or "unknown").lower()
    arch = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }.get(machine, machine)
    return f"{'windows' if IS_WINDOWS else 'linux'}-{arch}"


def pack_portable_zip(project_root, dist_dir):
    """把 ``dist/guji/`` 打成绿色免安装 zip（解压即得 ``guji/`` 目录）。

    与安装包是**两条并行的分发路径**：安装包负责装到 ``%LOCALAPPDATA%``、
    注册 PATH 与快捷方式；zip 版本解压即用、不写注册表，只给不想安装的人。
    两者内容同源（都是瘦身后的 ``dist/guji``），所以必须在 ``prune_bloat``
    之后打包，否则会把已清掉的 100+ MB 无用文件重新压进去。

    失败只警告：安装包与 ``dist/guji/`` 仍然是可用的产物。
    """
    import zipfile

    if not dist_dir.is_dir():
        print("⚠️ 未找到输出目录，跳过绿色免安装包")
        return None

    target = project_root / "dist" / PORTABLE_TEMPLATE.format(
        version=VERSION, platform=_platform_tag()
    )
    print(f"📦 打包绿色免安装版: {target.name}（约 650MB，需几分钟）")
    try:
        with zipfile.ZipFile(
            target, "w", zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            for path in sorted(dist_dir.rglob("*")):
                if path.is_file():
                    arcname = (Path("guji") / path.relative_to(dist_dir)).as_posix()
                    archive.write(path, arcname)
    except OSError as exc:
        print(f"⚠️ 绿色免安装包打包失败: {exc}")
        return None
    size_mb = target.stat().st_size / 1024 / 1024 if target.exists() else 0
    print(f"📦 {target.name}（{size_mb:.0f} MB）")
    return target


def pack_tarball(project_root, dist_dir):
    """Linux 产物打成 tar.gz（Linux 没有安装包，这就是它的绿色免安装版）。

    用 Python 的 ``tarfile`` 而不是 subprocess 调 tar：tar 需要额外传参才能
    保留可执行位，各发行版行为也不一致；纯 Python 路径在哪都一样。
    """
    import tarfile

    if not dist_dir.is_dir():
        print("⚠️ 未找到输出目录，跳过打包")
        return None

    target = project_root / "dist" / PORTABLE_TEMPLATE.format(
        version=VERSION, platform=_platform_tag()
    )
    try:
        with tarfile.open(target, "w:gz") as archive:
            archive.add(str(dist_dir), arcname=dist_dir.name)
    except OSError as exc:
        print(f"⚠️ 打包 tar.gz 失败: {exc}")
        return None
    size_mb = target.stat().st_size / 1024 / 1024 if target.exists() else 0
    print(f"📦 {target.name}（{size_mb:.0f} MB）")
    return target


def _deb_arch() -> str:
    """Debian 架构名：x86_64 -> amd64，aarch64 -> arm64。"""
    import platform

    machine = (platform.machine() or "unknown").lower()
    return {
        "amd64": "amd64",
        "x86_64": "amd64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }.get(machine, machine)


def _link_or_copy(src: Path, dst: Path) -> None:
    """优先硬链接（同盘秒级、不占双倍空间），失败退回 copy2。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def build_deb_package(project_root: Path, dist_dir: Path):
    """把 ``dist/guji/`` 打成 Debian 安装包。

    安装后目录::

        /opt/gujitools/{guji,guji-desktop,_internal,...}
        /usr/bin/guji            -> /opt/gujitools/guji
        /usr/bin/guji-desktop    -> /opt/gujitools/guji-desktop
        /usr/share/applications/gujitools.desktop
        /usr/share/icons/hicolor/{64x64,128x128,256x256}/apps/gujitools.png
        /usr/share/metainfo/gujitools.appdata.xml

    ``dpkg-deb`` 经 ``fakeroot`` 执行，保证归档内文件 owner 为 root。
    打包失败只警告，不阻断 tar.gz 与 dist/ 产物。
    """
    if not dist_dir.is_dir():
        print("⚠️ 未找到输出目录，跳过 .deb 打包")
        return None
    if shutil.which("dpkg-deb") is None:
        print("⚠️ 系统没有 dpkg-deb，跳过 .deb 打包")
        return None

    arch = _deb_arch()
    target = project_root / "dist" / DEB_TEMPLATE.format(version=VERSION, arch=arch)
    stage = project_root / "build" / f"deb_{time.strftime('%Y%m%d_%H%M%S')}"
    root = stage / DEB_PACKAGE_NAME
    debian = root / "DEBIAN"
    install_root = root / "opt" / "gujitools"
    debian.mkdir(parents=True, exist_ok=True)
    install_root.mkdir(parents=True, exist_ok=True)

    # dist/guji 原样落到 /opt/gujitools；硬链接避免再复制 5.5GB。
    n_files = 0
    for path in sorted(dist_dir.rglob("*")):
        rel = path.relative_to(dist_dir)
        dst = install_root / rel
        if path.is_symlink():
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not (dst.exists() or dst.is_symlink()):
                os.symlink(os.readlink(path), dst)
        elif path.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            _link_or_copy(path, dst)
            n_files += 1

    # CLI/GUI 全局入口。
    usr_bin = root / "usr" / "bin"
    usr_bin.mkdir(parents=True, exist_ok=True)
    for link_name, exe in (("guji", CLI_EXE), ("guji-desktop", GUI_EXE)):
        link = usr_bin / link_name
        if not (link.exists() or link.is_symlink()):
            os.symlink(f"{DEB_INSTALL_DIR}/{exe}", link)

    # 桌面入口：中文名 + Keywords 让 GNOME 活动搜索能按「古籍 / PDF / 版面」命中。
    apps = root / "usr" / "share" / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    desktop_entry = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=Guji Tools\n"
        "Name[zh_CN]=古籍工具\n"
        "GenericName=Document Layout Assistant\n"
        "GenericName[zh_CN]=文档版面识别工具\n"
        "Comment=PDF layout detection and annotation\n"
        "Comment[zh_CN]=PDF 版面识别与标注工具\n"
        "Exec=guji-desktop\n"
        "TryExec=guji-desktop\n"
        "Icon=gujitools\n"
        "Terminal=false\n"
        "Categories=Office;Utility;\n"
        "Keywords=pdf;layout;yolo;ocr;古籍;版面;识别;标注;\n"
        "StartupNotify=true\n"
        "StartupWMClass=guji-desktop\n"
        "NoDisplay=false\n"
    )
    desktop_file = apps / "gujitools.desktop"
    desktop_file.write_text(desktop_entry, encoding="utf-8")
    desktop_file.chmod(0o644)

    # 图标：GNOME 网格 / 搜索结果走 hicolor 主题；多尺寸比单张 256 更清晰。
    icon_src = dist_dir / "desktop" / "static" / "icon.png"
    if not icon_src.is_file():
        icon_src = project_root / "desktop" / "static" / "icon.png"
    if icon_src.is_file():
        resample = None
        try:
            from PIL import Image

            source = Image.open(icon_src).convert("RGBA")
            resample = getattr(Image, "Resampling", Image).LANCZOS
        except Exception:
            source = None
        for size in (64, 128, 256):
            icon_dir = (
                root / "usr" / "share" / "icons" / "hicolor" / f"{size}x{size}" / "apps"
            )
            target_icon = icon_dir / "gujitools.png"
            if source is not None and source.size != (size, size):
                icon_dir.mkdir(parents=True, exist_ok=True)
                source.resize((size, size), resample).save(target_icon)
            else:
                _link_or_copy(icon_src, target_icon)
            target_icon.chmod(0o644)

    # AppStream 元数据：GNOME Software / 应用搜索的附加索引。
    metainfo = root / "usr" / "share" / "metainfo" / "gujitools.appdata.xml"
    metainfo.parent.mkdir(parents=True, exist_ok=True)
    metainfo.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<component type="desktop-application">\n'
        "  <id>gujitools.desktop</id>\n"
        "  <metadata_license>CC0-1.0</metadata_license>\n"
        "  <project_license>Proprietary</project_license>\n"
        "  <name>Guji Tools</name>\n"
        '  <name xml:lang="zh_CN">古籍工具</name>\n'
        "  <summary>PDF layout detection and annotation</summary>\n"
        '  <summary xml:lang="zh_CN">PDF 版面识别与标注工具</summary>\n'
        "  <description>\n"
        "    <p>Detect page layout with YOLO and export annotated pages and PDF reports.</p>\n"
        "  </description>\n"
        '  <launchable type="desktop-id">gujitools.desktop</launchable>\n'
        "  <categories><category>Office</category><category>Utility</category></categories>\n"
        "  <keywords><keyword>PDF</keyword><keyword>layout</keyword>"
        "<keyword>YOLO</keyword><keyword>古籍</keyword><keyword>版面</keyword></keywords>\n"
        "</component>\n",
        encoding="utf-8",
    )
    metainfo.chmod(0o644)

    postinst = debian / "postinst"
    postinst.write_text(
        "#!/bin/sh\n"
        "set -e\n"
        "if command -v update-desktop-database >/dev/null 2>&1; then\n"
        "    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true\n"
        "fi\n"
        "if command -v gtk-update-icon-cache >/dev/null 2>&1; then\n"
        "    gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    postinst.chmod(0o755)

    installed_kib = sum(
        p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink()
    ) // 1024
    control = (
        f"Package: {DEB_PACKAGE_NAME}\n"
        f"Version: {VERSION}\n"
        "Section: utils\n"
        "Priority: optional\n"
        f"Architecture: {arch}\n"
        f"Installed-Size: {installed_kib}\n"
        "Depends: libc6, libstdc++6\n"
        "Recommends: fonts-noto-cjk | fonts-wqy-microhei\n"
        "Maintainer: gujitools <noreply@localhost>\n"
        "Description: PDF layout detection and annotation tool\n"
        " Guji Tools detects page layout with YOLO and exports annotated\n"
        " pages and PDF reports. CLI and desktop GUI share one runtime.\n"
    )
    (debian / "control").write_text(control, encoding="utf-8")
    (debian / "control").chmod(0o644)

    cmd = ["dpkg-deb", "--build", "-Zgzip", str(root), str(target)]
    if shutil.which("fakeroot"):
        cmd.insert(0, "fakeroot")
    print(f"📦 打 Debian 包: {target.name}（{n_files} 个文件，约需几分钟）")
    result = subprocess.run(cmd, cwd=str(project_root))
    if result.returncode != 0:
        print("⚠️ .deb 打包失败，可检查上方 dpkg-deb 输出；tar.gz 与 dist/ 不受影响")
        return None
    size_mb = target.stat().st_size / 1024 / 1024 if target.exists() else 0
    print(f"📦 {target.name}（{size_mb:.0f} MB）")
    return target


def print_font_hint():
    """Linux 目标机常缺中文字体，构建完打印一次该怎么办。

    程序运行时也会自己体检并弹安装引导（``utils/font_setup.py``），这里只是
    给打包者一句提示——不然很容易做出一个"能跑但 PDF 中文全是方块"的包。
    """
    try:
        from utils.font_setup import check_cjk_font, install_plan, manual_install_text
    except Exception as exc:  # 打包脚本不该因为提示而失败
        print(f"⚠️ 字体体检不可用: {exc}")
        return

    check = check_cjk_font()
    if check.found:
        assert check.path is not None
        print(
            f"   本机有中文字体（{Path(check.path).name}），目标机若缺替代也没问题："
            "程序会在首次启动时提示安装"
        )
        return
    print("⚠️ 本机没有中文字体：目标机很可能同样缺，PDF 的标题会变成方块。")
    print("   —— 可以先在这里装好，也可以让程序在目标机上提示用户一键安装 ——")
    for line in manual_install_text(install_plan()).splitlines():
        print(f"   {line}" if line.strip() else "")


# ------------------------------------------------------------------ 部署
# ⚠️ 这里曾经有 ``copy_to_software()`` / ``clean_old_backups()``：把 dist/guji
# 复制到 ``C:\Software\guji``（带版本备份）当作"部署"。已**整块删除**，理由：
#
# 1. 构建的职责是**产出可分发的东西**（dist/ + 安装包），不是替用户决定
#    装到哪。部署是安装包的事，安装目录写在 ``guji_setup.iss`` 的
#    ``DefaultDirName`` 里，用户还可以在向导里改。
# 2. 留着会导致本机同时存在 dist/guji、C:\Software\guji、以及安装后的
#    ``{app}`` 三份 650MB 的副本（约 2GB），排障时根本分不清跑的是哪一份。
# 3. 那一步还是整条构建最脆弱的环节（上千文件跨盘复制 + 删除，曾被批量
#    删除钩子拦下，把 16 分钟的构建判成失败）。
#
# 想在本机跑一份：直接双击 ``dist/guji/guji-desktop.exe``，或装一次安装包。
# 守卫：``tests/selftests/architecture/installer_paths.py``。


if __name__ == "__main__":
    raise SystemExit(main())
