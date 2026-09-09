"""
File: functions/init.py
`guji init` 命令的功能实现。

该模块负责交互式生成 `guji.yaml` 配置文件，引导用户输入项目元数据
（名称、描述、版本）和输入路径，并基于模板 `static/guji.yaml`
生成最终的配置文件，同时保留模板中的所有注释和键顺序。

关键行为：
- 如果 `guji.yaml` 已存在且未使用 `--force`，会询问是否覆盖。
- 可以交互式或通过命令行参数 `-i/--input` 提供输入路径。
- **不再询问输出根目录**，`extract.output` 始终保持为空（null）。
- 后续命令（crop/rembg/cropremove）的 `input` 根据输入类型自动计算：
    - 若输入是 PDF 文件 → `<父目录>/<pdf_stem>/<DEFAULT_EXTRACT_NAME>`（实际路径）
    - 若输入是目录 → `<输入目录>/<pdf_file_name>/<DEFAULT_EXTRACT_NAME>`（占位符，用户可自行替换）
- `print` 命令的 `input` 自动指向 `rembg` 的输出目录（`DEFAULT_REMBG_NAME`），
  与其他命令共用相同的 `<pdf_stem>` 或 `<pdf_file_name>` 父目录，
  以便用户直接生成最终的 PDF。
- 依赖 `ruamel.yaml` 保留注释和格式，若未安装则报错提示。
"""

import sys
import os
from pathlib import Path
from functions.base import DEFAULT_TEMP_NAME_MAP

DEFAULT_EXTRACT_NAME = DEFAULT_TEMP_NAME_MAP["extract"]  # 通常为 "images"
DEFAULT_REMBG_NAME = DEFAULT_TEMP_NAME_MAP["rembg"]  # 通常为 "rembg"

# -------- 可选 prompt‑toolkit 懒加载 --------
_pt_available = False
PathCompleter = None
pt_prompt = None
try:
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import PathCompleter

    _pt_available = True
except ImportError:
    pass


def safe_input(prompt_text: str, use_path_completer: bool = False) -> str:
    """统一输入封装，支持路径补全。"""
    if _pt_available and use_path_completer:
        completer = PathCompleter(expanduser=True)
        raw = pt_prompt(prompt_text, completer=completer)
    else:
        raw = input(prompt_text)
    return raw.strip()


class InitFunction:
    def __init__(self, command_args):
        self.args = command_args
        self.force = self.args.get("force", False)
        self.cli_input = self.args.get("input")  # 用户通过 -i 提供的输入路径（或 None）

    @staticmethod
    def _norm_path_str(s: str) -> str:
        """规范化路径：统一分隔符为 '/'，相对路径加 './'。"""
        s = s.replace("\\", "/")
        p = Path(s)
        if not p.is_absolute() and not s.startswith("."):
            s = "./" + s
        return s

    def execute(self):
        target = Path.cwd() / "guji.yaml"

        # 覆盖检查
        if target.exists() and not self.force:
            resp = safe_input("guji.yaml 已存在，是否覆盖？(y/N) ").lower()
            if resp and resp[0] == "n":
                print("已取消生成。")
                return {"status": "cancelled"}

        defaults = {
            "name": "我的古籍项目",
            "description": "示例古籍数字化处理",
            "version": "1.0.0",
            "input": "./sample.pdf",
        }

        input_path = self.cli_input

        # 交互式收集缺失信息（不再询问 output）
        if input_path is None:
            print("请输入项目信息（直接回车使用默认值）：")
            name = (
                safe_input(f"项目名称 (default: {defaults['name']}): ")
                or defaults["name"]
            )
            desc = (
                safe_input(f"项目描述 (default: {defaults['description']}): ")
                or defaults["description"]
            )
            ver = (
                safe_input(f"版本号 (default: {defaults['version']}): ")
                or defaults["version"]
            )
            raw_inp = safe_input(
                f"原始 PDF 或图片目录 (default: {defaults['input']}): ",
                use_path_completer=True,
            )
            inp = raw_inp.strip('"') or defaults["input"]
            input_path = Path(inp)
        else:
            name = defaults["name"]
            desc = defaults["description"]
            ver = defaults["version"]

        # ----- 计算各命令的 input 路径 -----
        is_pdf = input_path.suffix.lower() == ".pdf"
        extract_input_str = self._norm_path_str(str(input_path))

        if is_pdf:
            # PDF 文件 -> 父目录/pdf_stem/DEFAULT_EXTRACT_NAME
            images_dir = input_path.parent / input_path.stem / DEFAULT_EXTRACT_NAME
            post_input = self._norm_path_str(str(images_dir))
        else:
            # 目录 -> 输入目录/<pdf_file_name>/DEFAULT_EXTRACT_NAME (占位符)
            post_input = os.path.join(
                str(input_path), "<pdf_file_name>", DEFAULT_EXTRACT_NAME
            )
            post_input = self._norm_path_str(post_input)

        # print 的 input 指向 rembg 输出目录（与 crop/rembg/cropremove 同级，但子目录不同）
        # 例如：<base>/rembg 而不是 <base>/images
        post_input_path = Path(post_input)
        base_dir = post_input_path.parent  # 即 <pdf_stem> 或 <pdf_file_name> 目录
        print_input_path = base_dir / DEFAULT_REMBG_NAME
        print_input = self._norm_path_str(str(print_input_path))

        # 加载模板
        template_path = Path(__file__).parent.parent / "static" / "guji.yaml"
        if not template_path.exists():
            print(f"ERROR: 模板文件 {template_path} 未找到")
            sys.exit(1)

        try:
            from ruamel.yaml import YAML
        except ImportError:
            print("ERROR: 需要安装 ruamel.yaml 以保留配置注释，请运行：")
            print("    pip install ruamel.yaml")
            sys.exit(1)

        yaml = YAML()
        with open(template_path, "r", encoding="utf-8") as f:
            data = yaml.load(f)

        # 更新元数据
        data["name"] = name
        data["description"] = desc
        data["version"] = ver

        # 更新 extract
        if "extract" in data and isinstance(data["extract"], dict):
            data["extract"]["input"] = extract_input_str
            data["extract"]["output"] = None  # 显式设为 null

        # 更新 crop / rembg / cropremove（它们共用 images 目录）
        for cmd in ["crop", "rembg", "cropremove"]:
            if cmd in data and isinstance(data[cmd], dict):
                data[cmd]["input"] = post_input

        # 更新 print（指向 rembg 输出目录）
        if "print" in data and isinstance(data["print"], dict):
            data["print"]["input"] = print_input

        # 写入最终配置文件
        with open(target, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        print(f"✅ 已生成配置文件: {target}")
        return {"file": str(target)}
