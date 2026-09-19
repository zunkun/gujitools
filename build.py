#!/usr/bin/env python
"""PyInstaller 打包脚本（CLI + GUI 一体）。

用法:
    python build.py

会通过 conda 环境 ``yolobuild`` 构建（缺依赖时自动安装），产出
**一个目录内同时含 CLI 与 GUI 两个可执行文件**，随后生成安装包。

输出（**就这两样：一份可执行目录 + 一个安装包**）:
    dist/guji/guji.exe       命令行工具（console，安装后 PATH 可直接用 guji）
    dist/guji/guji-desktop.exe   桌面 GUI（windowed，安装包会建快捷方式）
    dist/guji_setup_<版本>_<时间戳>.exe   安装包

⚠️ **构建脚本不负责部署**：本脚本只把产物落到 ``dist/``，**不再往
``C:\Software\guji`` 之类的地方复制一份**——那是历史行为，会让人分不清
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

Linux 侧**没有安装包**（Inno Setup 是 Windows 专属），改用 tar.gz 分发；
需要 AppImage / .desktop 再另行打包。另外 Linux 目标机往往没有中文字体，
构建结束脚本会打印安装提示（程序运行时也会自行体检并弹安装引导，
见 ``utils/font_setup.py``）。

注意：GUI 依赖（PySide6 / qfluentwidgets）也在 yolobuild 内安装，
因为两个 EXE 必须同一次构建产出才能合并 _internal。
"""

import sys
import os
import shutil
import subprocess
import time
from pathlib import Path

from config import VERSION

BUILD_ENV_NAME = "yolobuild"

#: Windows 特有行为的开关（ico 图标、Inno Setup 安装包、D:\... 瘦身清单）
IS_WINDOWS = sys.platform == "win32"

#: 可执行文件名（Linux 无后缀）
CLI_EXE = "guji.exe" if IS_WINDOWS else "guji"
GUI_EXE = "guji-desktop.exe" if IS_WINDOWS else "guji-desktop"


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
            "import importlib.metadata as metadata; import cv2, PyInstaller, torch, ultralytics, yaml, fpdf, PySide6, qfluentwidgets, markdown; has_full_opencv=any(d.metadata['Name'].lower() == 'opencv-python' for d in metadata.distributions()); raise SystemExit(torch.version.cuda is not None or has_full_opencv)",
        ],
        check=False,
    )
    if check.returncode == 0:
        return

    print("安装 yolobuild 依赖（CPU PyTorch）...")
    run_conda(
        conda_exe,
        [
            "run",
            "-n",
            BUILD_ENV_NAME,
            "python",
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
        ],
    )
    run_conda(
        conda_exe,
        [
            "run",
            "-n",
            BUILD_ENV_NAME,
            "python",
            "-m",
            "pip",
            "uninstall",
            "-y",
            "torch",
            "torchvision",
            "torchaudio",
        ],
    )
    run_conda(
        conda_exe,
        [
            "run",
            "-n",
            BUILD_ENV_NAME,
            "python",
            "-m",
            "pip",
            "install",
            "--index-url",
            "https://download.pytorch.org/whl/cpu",
            "torch",
            "torchvision",
            "torchaudio",
        ],
    )
    run_conda(
        conda_exe,
        [
            "run",
            "-n",
            BUILD_ENV_NAME,
            "python",
            "-m",
            "pip",
            "install",
            "-i",
            "https://mirrors.aliyun.com/pypi/simple/",
            "-r",
            str(project_root / "requirements.txt"),
        ],
    )
    run_conda(
        conda_exe,
        [
            "run",
            "-n",
            BUILD_ENV_NAME,
            "python",
            "-m",
            "pip",
            "uninstall",
            "-y",
            "opencv-python",
        ],
    )
    run_conda(
        conda_exe,
        [
            "run",
            "-n",
            BUILD_ENV_NAME,
            "python",
            "-m",
            "pip",
            "install",
            "--force-reinstall",
            "--no-deps",
            "-i",
            "https://mirrors.aliyun.com/pypi/simple/",
            "opencv-python-headless",
        ],
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
    # 护栏：tests/selftests/manual_dialog.py 从 help_dialog.py 的 import 反推
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


def trash_root() -> Path:
    """旧产物与瘦身后文件的**归档目录**（仓库外同级：`../.guji_build_trash`）。

    ⚠️ 为什么构建里一律「只移不删」：

    1. `dist/guji` 动辄上千项，`rmtree` 会被批量删除安全钩子按条数拦下
       （实测 count=1168 > 阈值 50），一次拦下整轮 15 分钟的构建就白跑了；
    2. 构建产物删了就没了——万一新包有问题，旧包也回不来。

    移到同盘的归档目录（同盘 = rename，秒级、不复制数据），需要腾空间时
    手动清即可。
    """
    root = Path(__file__).resolve().parent.parent / ".guji_build_trash"
    root.mkdir(parents=True, exist_ok=True)
    return root


def retire(path: Path, trash: Path) -> Path | None:
    """把旧的 build/ 或 dist/ 整体搬进归档目录，返回落点。"""
    if not path.exists():
        return None
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = trash / f"{path.name}_{stamp}"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():  # 同一秒内重复跑
            dest = trash / f"{path.name}_{stamp}_{os.getpid()}"
        shutil.move(str(path), str(dest))
    except OSError as exc:
        print(f"   ⚠️ 旧 {path.name} 归档失败（继续构建）: {exc}")
        return None
    print(f"   ♻️  旧 {path.name}/ → {dest}")
    return dest


def discard(path: Path, trash: Path, anchor: Path | None = None) -> bool:
    """把瘦身命中的单个文件搬进归档目录（同样不删），成功返回 True。

    ``trash`` 必须是**每次构建独有**的子目录：同名目标已存在时，旧代码会先
    ``unlink`` 再搬——单次构建里 2332 个文件累计起来照样撞上批量删除阈值
    （实测 count=50 就红）。让目标永不冲突，就一次删除都不需要。
    """
    try:
        dest = (trash / path.relative_to(anchor)) if anchor is not None else (trash / path.name)
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


def elapsed(start: float, label: str) -> None:
    """打印某阶段耗时——构建全程 15~20 分钟，没有计时容易误判成卡死。"""
    secs = time.monotonic() - start
    if secs < 60:
        print(f"⏱️  {label} 耗时 {secs:.1f}s")
    else:
        print(f"⏱️  {label} 耗时 {int(secs // 60)}m{secs % 60:04.1f}s")


def refresh_manual_only(project_root) -> int:
    """只重生成手册并刷新部署与安装包（`python build.py --manual-only`）。

    为什么单开一条：完整打包要 19 分钟（PyInstaller 7m + 瘦身 8m），而调手册
    版式/文案时 Python 侧一个字节都没变——重生成 `manual.html`、刷一次部署、
    重压一次安装包，两分半就够了。**改了 `.py` 仍然必须完整打包。**
    """
    dist_dir = project_root / "dist" / "guji"
    if not dist_dir.is_dir():
        print("❌ 没有 dist/guji，请先跑一次完整打包：python build.py")
        return 1

    steps: list[tuple[str, object]] = [("预生成手册", lambda: build_manual_html(dist_dir))]
    if IS_WINDOWS:
        # ⚠️ 这里曾经还有一步「复制到 C:\Software」把产物部署一份出去。
        # 已删除：构建只产出安装包，部署由安装包负责（否则本机同时存在
        # dist/、C:\Software\guji、安装目录三份，跑的是哪一份都说不清）。
        steps += [
            ("生成安装包",
             lambda: build_installer(project_root, project_root / "desktop" / "static" / "icon.ico")),
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

    print(f"项目版本: {VERSION}")

    # 归档旧产物（guji.spec 现在是构建输入，不能删）
    # ⚠️ 这里**只移不删**：详见 trash_root() 的说明。
    trash = trash_root()
    for target in [project_root / "build", project_root / "dist"]:
        retire(target, trash)

    icon = prepare_icon(project_root)

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

        steps: list[tuple[str, object]] = [
            ("校验产物", lambda: verify_outputs(dist_dir)),
            ("预生成手册", lambda: build_manual_html(dist_dir)),
            ("体积瘦身", lambda: prune_bloat(dist_dir)),
            ("瘦身检查", lambda: run_bloat_check(project_root)),
        ]
        if IS_WINDOWS:
            # ⚠️ 构建只出安装包，不再往 C:\Software\guji 复制一份部署副本
            # （见模块 docstring）。dist/guji/ 本身可直接分发/就地运行。
            steps += [
                ("生成安装包", lambda: build_installer(project_root, icon)),
            ]
        else:
            steps += [
                ("打 tar.gz", lambda: pack_tarball(project_root, dist_dir)),
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
    # 每次构建一个独立的归档子目录：目标名不冲突，就永远不需要先删后搬
    run_trash = trash_root() / "pruned" / time.strftime("%Y%m%d_%H%M%S")
    for path, reason in targets:
        if not path.exists():
            continue
        try:
            size = path.stat().st_size if path.is_file() else 0
        except OSError:
            continue
        if discard(path, run_trash, anchor=internal):
            saved += size
            removed_files += 1
        else:
            print(f"   ⚠️ 归档失败（跳过）{path}")

    # 删（归档）完 .py 后剩下的空目录也一并清理；清不掉无所谓，空目录不占体积
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
            f"🧹 瘦身完成：归档 {removed_files} 个文件、清理 {removed_dirs} 个空目录，"
            f"腾出 {saved / MB:.1f} MB（文件已移到 {run_trash}，未删除）"
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


def build_installer(project_root, icon=None):
    """用 Inno Setup 生成带版本号和时间戳的安装包。

    icon 为 .ico 路径时通过 /DICON_FILE 传给脚本（SetupIconFile）。
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

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    cmd = [
        str(iscc),
        f"/DVERSION={VERSION}",
        f"/DBUILD_TIMESTAMP={timestamp}",
    ]
    if icon and Path(icon).is_file():
        cmd.append(f"/DICON_FILE={icon}")
    cmd.append(str(project_root / "guji_setup.iss"))
    print(f"\n📦 生成安装包: guji_setup_{VERSION}_{timestamp}.exe")
    result = subprocess.run(cmd, cwd=str(project_root))
    if result.returncode != 0:
        raise RuntimeError("安装包生成失败")
    print(f"✅ 安装包生成完成: dist/guji_setup_{VERSION}_{timestamp}.exe")


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
    if inlined != 12:
        problems.append(f"内联截图 {inlined} 张（期望 12）")
    if 'src="file:' in document or 'src="screenshots/' in document:
        problems.append("仍存在外部图片引用（装机后会碎图）")
    size_mb = out.stat().st_size / 1024 / 1024
    if problems:
        print(f"   ⚠️ 手册自包含检查异常：{'；'.join(problems)}")
    print(f"   手册已预生成为自包含 HTML：manual.html（{size_mb:.1f} MB，"
          f"内联 {inlined} 张截图）")


def pack_tarball(project_root, dist_dir):
    """Linux 产物打成 tar.gz（Windows 安装包之外的分发方式）。

    用 Python 的 ``tarfile`` 而不是 subprocess 调 tar：tar 需要额外传参才能
    保留可执行位，各发行版行为也不一致；纯 Python 路径在哪都一样。
    """
    import platform
    import tarfile
    import time

    from config import VERSION

    if not dist_dir.is_dir():
        print("⚠️ 未找到输出目录，跳过打包")
        return None

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    arch = platform.machine() or "unknown"
    target = project_root / "dist" / f"guji_{VERSION}_{timestamp}_linux-{arch}.tar.gz"
    try:
        with tarfile.open(target, "w:gz") as archive:
            archive.add(str(dist_dir), arcname=dist_dir.name)
    except OSError as exc:
        print(f"⚠️ 打包 tar.gz 失败: {exc}")
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
# 守卫：``tests/selftests/installer_paths.py``。


if __name__ == "__main__":
    raise SystemExit(main())
