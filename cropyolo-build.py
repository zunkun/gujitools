import os
import sys
import subprocess


def run_cmd(cmd: str):
    print(f"\n执行命令: {cmd}\n")
    ret = subprocess.call(cmd, shell=True)
    if ret != 0:
        print(f"命令执行失败，退出码: {ret}")
        sys.exit(ret)


def main():
    # 检查主程序是否存在
    main_script = "cropyolo.py"
    if not os.path.exists(main_script):
        print(f"错误：找不到 {main_script}")
        return

    # 打包参数，已经配置好瘦身排除项、资源路径
    pyinstaller_args = [
        "pyinstaller",
        "--onefile",
        "--clean",
        # 排除无用大库瘦身
        "--exclude-module=torchvision",
        "--exclude-module=tensorflow",
        "--exclude-module=keras",
        "--exclude-module=pandas",
        "--exclude-module=scipy",
        "--exclude-module=IPython",
        "--exclude-module=tkinter",
        # 资源文件
        '--add-data="weights/detect.pt;weights/"',
        "--name=cropyolo",
        main_script,
    ]

    cmd = " ".join(pyinstaller_args)
    run_cmd(cmd)
    print("\n打包完成！产物在 dist/ 文件夹内")


if __name__ == "__main__":
    main()
