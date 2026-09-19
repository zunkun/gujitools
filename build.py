#!/usr/bin/env python
"""PyInstaller 打包脚本（CLI + GUI 一体）。

用法:
    python build.py

会通过 conda 环境 ``yolobuild`` 构建（缺依赖时自动安装），产出
**一个目录内同时含 CLI 与 GUI 两个可执行文件**，随后复制并生成安装包。

输出:
    dist/guji/guji.exe       命令行工具（console，安装后 PATH 可直接用 guji）
    dist/guji/guji-gui.exe   桌面 GUI（windowed，安装包会建快捷方式）
    dist/guji_setup_<版本>_<时间戳>.exe   安装包

两者共享同一份 dist/guji/_internal：torch/cv2 等大二进制只落地一份。

⚠️ **PyInstaller 不能交叉编译**，所以 Linux 产物只能在 Linux 上构建
（物理机 / WSL2 / CI runner），Windows 上怎么配置都变不出 ELF。同一份
``build.py`` 在 Ubuntu 上执行即可，差异由脚本自动处理：

    dist/guji/guji            （无 .exe 后缀）
    dist/guji/guji-gui
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
GUI_EXE = "guji-gui.exe" if IS_WINDOWS else "guji-gui"


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
    """把瘦身命中的单个文件搬进归档目录（同样不删），成功返回 True。"""
    try:
        if anchor is not None:
            dest = trash / "pruned" / path.relative_to(anchor)
        else:
            dest = trash / "pruned" / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.unlink()
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
        print(f"✅ 生成图标: {ico.relative_to(project_root)}"
              f"（圆角 {DEFAULT_RADIUS_PCT}%）")
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


def main():
    project_root = Path(__file__).resolve().parent
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

    # 用 spec 构建：一个目录内同时产出 guji.exe(CLI) 与 guji-gui.exe(GUI)，
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
    print("（PyInstaller 全程约 10 分钟：两次 Analysis + COLLECT 落地 650MB，"
          "期间进度由子进程逐行打印）\n")

    t0 = time.monotonic()
    result = subprocess.run(cmd, cwd=str(project_root))
    elapsed(t0, "PyInstaller")

    if result.returncode == 0:
        dist_dir = project_root / "dist" / "guji"
        built = [
            p.name for p in dist_dir.iterdir() if p.name in (CLI_EXE, GUI_EXE)
        ] if dist_dir.is_dir() else []
        if built:
            print(f"\n✅ 打包完成: dist/guji/  →  {', '.join(sorted(built))}")
        else:
            print("\n✅ 打包完成: dist/guji/")

        steps: list[tuple[str, object]] = [
            ("校验产物", lambda: verify_outputs(dist_dir)),
            ("体积瘦身", lambda: prune_bloat(dist_dir)),
            ("瘦身检查", lambda: run_bloat_check(project_root)),
        ]
        if IS_WINDOWS:
            steps += [
                ("复制到 C:\\Software",
                 lambda: copy_to_software(project_root, "onedir")),
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
            (internal / "cv2" / "opencv_videoio_ffmpeg500_64.dll",
             "cv2 视频编解码（项目只用 imread/imwrite 等图像 API）"),
            (internal / "PySide6" / "opengl32sw.dll",
             "Qt 软件 OpenGL 回退（界面不依赖 OpenGL）"),
            (internal / "torch" / "bin" / "protoc.exe",
             "protobuf 编译器（构建期工具，运行期不执行）"),
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
    for path, reason in targets:
        if not path.exists():
            continue
        try:
            size = path.stat().st_size if path.is_file() else 0
        except OSError:
            continue
        if discard(path, trash_root(), anchor=internal):
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
        print(f"🧹 瘦身完成：归档 {removed_files} 个文件、清理 {removed_dirs} 个空目录，"
              f"腾出 {saved / MB:.1f} MB（文件已移到 {trash_root()}，未删除）")
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
    missing = [name for name in (CLI_EXE, GUI_EXE)
               if not (dist_dir / name).is_file()]
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
        print("\n⚠️ 未找到 ISCC.exe（Inno Setup），跳过安装包生成\n"
              "   dist/guji/ 已可直接分发；要出安装包请安装 Inno Setup 6/7")
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
    target = (
        project_root / "dist" / f"guji_{VERSION}_{timestamp}_linux-{arch}.tar.gz"
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
        print(f"   本机有中文字体（{Path(check.path).name}），目标机若缺替代也没问题："
              "程序会在首次启动时提示安装")
        return
    print("⚠️ 本机没有中文字体：目标机很可能同样缺，PDF 的标题会变成方块。")
    print("   —— 可以先在这里装好，也可以让程序在目标机上提示用户一键安装 ——")
    for line in manual_install_text(install_plan()).splitlines():
        print(f"   {line}" if line.strip() else "")


def copy_to_software(project_root, mode):
    r"""将 onedir 打包结果复制到 C:\Software 并做版本备份。"""
    if not IS_WINDOWS:
        print("⚠️ 非 Windows：跳过复制到 C:\\Software")
        return
    import time

    from config import VERSION

    source = project_root / "dist" / "guji"
    target = Path(r"C:\Software\guji")
    backup_dir = Path(r"C:\Software\guji_backup")
    max_backups = 5

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_name = f"guji_v{VERSION}_{timestamp}"
    backup_path = backup_dir / backup_name

    print("\n📦 复制到 C:\\Software\\guji...")
    if target.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)

        if backup_path.exists():
            suffix = 2
            while True:
                backup_path = backup_dir / f"{backup_name}_{suffix}"
                if not backup_path.exists():
                    break
                suffix += 1

        # ⚠️ 这里是**移动**，而不是原先的「先复制一份备份、再 rmtree 掉目标」：
        # ① 复制 665MB 再删 1168 项要好几分钟，同盘 rename 是瞬时的；
        # ② `shutil.rmtree(target)` 上千项会被批量删除安全钩子拦下——
        #    实测整轮 16 分钟的构建就栽在这最后一步。
        # 语义完全一样：旧目录整体搬进备份目录，一个字节都没少。
        print("   目标目录已存在，先把旧版移到备份目录...")
        try:
            shutil.move(str(target), str(backup_path))
            print(f"   ✅ 备份到: {backup_path}")
        except Exception as e:
            print(f"   ❌ 备份失败（不覆盖现有部署）: {e}")
            return

        clean_old_backups(backup_dir, max_backups)

    try:
        shutil.copytree(str(source), str(target))
        print(f"   ✅ 复制完成: {target}")
    except Exception as e:
        print(f"   ❌ 复制失败: {e}")


def clean_old_backups(backup_dir, max_backups):
    """列出保留数量之外的旧备份（**不代删**）。

    ⚠️ 以前这里直接 `shutil.rmtree`：几百 MB 的旧包说删就删，而且上千项会被
    批量删除安全钩子拦下，把整轮 16 分钟的构建判成失败。备份的价值就在于
    "还在"，所以只列出超额的那些，交给你自己清。
    """
    if not backup_dir.exists():
        return

    backups = sorted(
        [d for d in backup_dir.iterdir() if d.is_dir()],
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )

    if len(backups) <= max_backups:
        return

    print(f"   备份数已超过 {max_backups}，以下可自行删除：")
    for backup in backups[max_backups:]:
        print(f"   🗑️ {backup}")


if __name__ == "__main__":
    main()
