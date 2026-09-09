#!/usr/bin/env python
"""PyInstaller 打包脚本。

用法:
    python build.py             # onedir 模式（推荐，启动快）
    python build.py --onefile   # 单文件模式（分发方便，启动较慢）

输出:
    dist/guji/guji.exe          (onedir)
    dist/guji.exe               (onefile)
"""

import sys
import shutil
import subprocess
import time
from pathlib import Path

from config import VERSION


def main():
    project_root = Path(__file__).resolve().parent
    mode = "onefile" if "--onefile" in sys.argv else "onedir"

    # 清理旧产物
    for target in [
        project_root / "build",
        project_root / "dist",
        project_root / "guji.spec",
    ]:
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    # PyInstaller 数据分隔符: Windows 用 ;  Unix 用 :
    sep = ";" if sys.platform == "win32" else ":"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        "guji",
        f"--{mode}",
        "--console",
        "--noconfirm",
        "--clean",
        # 运行时数据文件（路径解析基于 __file__，打包后仍生效）
        f"--add-data",
        f"weights{sep}weights",  # YOLO 权重 detect.pt
        f"--add-data",
        f"docs/functions{sep}docs/functions",  # help 系统的 .md 文档
        # ultralytics: 不手动指定，靠 PyInstaller 自动分析 + 内置 hook
        # （手动 --collect-all/--hidden-import 会拉入训练模块→matplotlib/scipy）
        # functions/ 和 utils/ 使用 importlib.import_module 延迟加载，
        # PyInstaller 静态分析无法检测，需显式收集全部子模块
        "--collect-submodules",
        "functions",
        "--collect-submodules",
        "utils",
        # 函数内延迟导入的第三方库
        "--hidden-import",
        "pymupdf",
        # 排除运行时不需要的依赖
        # polars: ultralytics 训练/绘图模块延迟导入，推理不触发（174MB）
        # scipy/pandas: 未被 from ultralytics import YOLO 导入，安全排除
        # matplotlib: 被 ultralytics 顶层导入，通过 yolo_utils.py 的 stub hook 满足
        # torchvision: NMS 推理时实际调用 torchvision.ops.nms，必须保留（仅 9MB）
        "--exclude-module",
        "polars",
        "--exclude-module",
        "scipy",
        "--exclude-module",
        "matplotlib",
        "--exclude-module",
        "pandas",
        "--exclude-module",
        "IPython",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "pytest",
        "--exclude-module",
        "cython",
        "--exclude-module",
        "setuptools",
        # 入口
        "main.py",
    ]

    print(f"打包模式: {mode}")
    print(f"工作目录: {project_root}")
    print(f"命令: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=str(project_root))

    if result.returncode == 0:
        exe = "guji.exe" if sys.platform == "win32" else "guji"
        if mode == "onefile":
            print(f"\n✅ 打包完成: dist/{exe}")
        else:
            print(f"\n✅ 打包完成: dist/guji/{exe}")
            copy_to_software(project_root, mode)
            build_installer(project_root)
    else:
        print("\n❌ 打包失败，请检查上方日志")
        sys.exit(1)


def build_installer(project_root):
    """用 Inno Setup 生成带版本号和时间戳的安装包。"""
    if sys.platform != "win32":
        print("\n⚠️ 非 Windows 环境，跳过安装包生成")
        return

    iscc_candidates = [
        shutil.which("ISCC.exe"),
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
        raise FileNotFoundError("未找到 ISCC.exe，请安装 Inno Setup")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    cmd = [
        str(iscc),
        f"/DVERSION={VERSION}",
        f"/DBUILD_TIMESTAMP={timestamp}",
        str(project_root / "guji_setup.iss"),
    ]
    print(f"\n📦 生成安装包: guji_setup_{VERSION}_{timestamp}.exe")
    result = subprocess.run(cmd, cwd=str(project_root))
    if result.returncode != 0:
        raise RuntimeError("安装包生成失败")
    print(f"✅ 安装包生成完成: dist/guji_setup_{VERSION}_{timestamp}.exe")


def copy_to_software(project_root, mode):
    """将 onedir 打包结果复制到 C:\Software\ 并做版本备份。"""
    import time

    from config import VERSION

    source = project_root / "dist" / "guji"
    target = Path(r"C:\Software\guji")
    backup_dir = Path(r"C:\Software\guji_backup")
    max_backups = 5

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_name = f"guji_v{VERSION}_{timestamp}"
    backup_path = backup_dir / backup_name

    print(f"\n📦 复制到 C:\\Software\\guji...")
    if target.exists():
        print(f"   目标目录已存在，先备份...")
        backup_dir.mkdir(parents=True, exist_ok=True)

        if backup_path.exists():
            suffix = 2
            while True:
                backup_path = backup_dir / f"{backup_name}_{suffix}"
                if not backup_path.exists():
                    break
                suffix += 1

        try:
            shutil.copytree(str(target), str(backup_path))
            print(f"   ✅ 备份到: {backup_path}")
        except Exception as e:
            print(f"   ⚠️  备份失败: {e}")

        shutil.rmtree(str(target))

        clean_old_backups(backup_dir, max_backups)

    try:
        shutil.copytree(str(source), str(target))
        print(f"   ✅ 复制完成: {target}")
    except Exception as e:
        print(f"   ❌ 复制失败: {e}")


def clean_old_backups(backup_dir, max_backups):
    """清理超过保留数量限制的旧备份。"""
    if not backup_dir.exists():
        return

    backups = sorted(
        [d for d in backup_dir.iterdir() if d.is_dir()],
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )

    if len(backups) <= max_backups:
        return

    to_delete = backups[max_backups:]
    print(f"   清理旧备份（保留最近{max_backups}个）...")
    for backup in to_delete:
        try:
            shutil.rmtree(str(backup))
            print(f"   🗑️ 删除: {backup.name}")
        except Exception as e:
            print(f"   ⚠️ 删除失败 {backup.name}: {e}")


if __name__ == "__main__":
    main()
