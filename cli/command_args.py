"""
File: cli/command_args.py
命令行参数标准化容器。
将 argparse.Namespace 或 config 字典中的参数统一为功能模块可直接使用的字典结构。
约定:
- 不在此阶段进行文件系统创建/校验（如创建输出目录）；
- `input` 标准化为 Path 并 expanduser().resolve()；
- `output` 保留为原始字符串，由上层功能决定如何解析；
- 各命令的特定参数按默认值注入；
- **所有默认值统一在此维护**，命令行解析器不再设置 default。
- 从 kwargs 取值时，若键不存在或值为 None，则使用默认值。
"""

import multiprocessing
from pathlib import Path
from typing import Dict, Any, List, Optional, Union


class CommandArgs:
    """
    解析后参数的轻量容器。
    通过 `get(key, default)` 按字典风格获取参数，兼容 FunctionBase 的使用方式。
    """

    def __init__(self, **kwargs):
        command = kwargs.get("command", None)
        self.command = command
        self.args: Dict[str, Any] = {"command": command}
        self._build_args(**kwargs)

    def get(self, key: str, default: Any = None) -> Any:
        """按字典风格获取参数。"""
        return self.args.get(key, default)

    def _get_with_default(self, key: str, default: Any, kwargs: dict) -> Any:
        """
        安全取值：仅当键不存在或值为 None 时返回默认值，否则返回实际值。
        这样可以正确处理 argparse 未指定参数时值为 None 的情况。
        """
        if key not in kwargs or kwargs[key] is None:
            return default
        return kwargs[key]

    @staticmethod
    def _normalize_margin_value(
        value: Any, default: Optional[List[float]] = None
    ) -> Optional[List[float]]:
        """
        将 CSS 风格的 margin 简写标准化为 [上, 右, 下, 左] 四元素列表。
        支持：
          - 单值: 20 或 [20] → [20,20,20,20]
          - 两值: [20,30] → [20,30,20,30]  (上下, 左右)
          - 三值: [20,30,25] → [20,30,25,30] (上, 左右, 下)
          - 四值: [20,30,25,35] → 原样
          - 字符串: "20", "20,30" 等 → 解析后同上
          - 空字符串、空列表、None → 返回 default
        若输入为空或 None 且 default 为 None，则返回 None。
        """
        if value is None:
            return default
        # 如果是字符串，去除首尾空格，若为空则返回 default
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return default
            # 按逗号分割
            parts = [p.strip() for p in value.split(",") if p.strip() != ""]
            if not parts:
                return default
            # 转换为数字
            try:
                vals = [float(p) for p in parts]
            except ValueError:
                # 如果转换失败，则视为无效，返回 default
                return default
        elif isinstance(value, (list, tuple)):
            if len(value) == 0:
                return default
            try:
                vals = [float(v) for v in value]
            except (ValueError, TypeError):
                return default
        else:
            # 其他类型（如 int, float）直接转为单值列表
            try:
                vals = [float(value)]
            except (ValueError, TypeError):
                return default

        # 截取前4个
        vals = vals[:4]
        if len(vals) == 1:
            return [vals[0], vals[0], vals[0], vals[0]]
        elif len(vals) == 2:
            return [vals[0], vals[1], vals[0], vals[1]]
        elif len(vals) == 3:
            return [vals[0], vals[1], vals[2], vals[1]]
        else:  # 4个
            return [vals[0], vals[1], vals[2], vals[3]]

    def _build_args(self, **kwargs) -> None:
        """
        对常用参数做统一预处理，并按命令注入特定默认值。
        所有默认值在此定义，命令行解析器不再设置 default。
        只做内存级别的标准化，不触及磁盘 I/O。
        """
        # -------- 通用参数（所有命令共享） --------
        # input: 标准化为绝对 Path，默认当前目录
        input_raw = self._get_with_default("input", ".", kwargs)
        # 如果 input_raw 是空字符串，也视为默认
        if isinstance(input_raw, str) and input_raw.strip() == "":
            input_raw = "."
        input_path = Path(input_raw).expanduser().resolve()
        self.args["input"] = input_path

        # output: 保留原始字符串（可能为 None、相对名或绝对路径），允许为 None
        self.args["output"] = kwargs.get("output", None)

        # workers: 默认 CPU 核心数
        self.args["workers"] = self._get_with_default(
            "workers", multiprocessing.cpu_count(), kwargs
        )

        # clean: 布尔值，默认 False
        self.args["clean"] = self._get_with_default("clean", False, kwargs)

        command = self.command

        # -------- 命令特有参数 --------
        if command == "extract":
            self.args.update(
                {
                    "zoom": self._get_with_default("zoom", 1, kwargs),
                    "quick": self._get_with_default("quick", True, kwargs),
                    "ext": self._get_with_default("ext", "jpg", kwargs),
                    "pages": self._get_with_default("pages", None, kwargs),
                    "start": self._get_with_default("start", None, kwargs),
                    "end": self._get_with_default("end", None, kwargs),
                    "batch_size": self._get_with_default("batch_size", 4, kwargs),
                }
            )

        elif command == "crop":
            self.args.update(
                {
                    "area": self._get_with_default("area", 1, kwargs),
                    "border": self._get_with_default("border", None, kwargs),
                    "ext": self._get_with_default("ext", "png", kwargs),
                }
            )

        elif command == "rembg":
            self.args.update(
                {
                    "offset": self._get_with_default("offset", 0, kwargs),
                    "type": self._get_with_default("type", 1, kwargs),
                    "seal": self._get_with_default("seal", False, kwargs),
                    "sealcolor": self._get_with_default("sealcolor", False, kwargs),
                    "sealarea": self._get_with_default("sealarea", 80, kwargs),
                    "sealmin_sat": self._get_with_default("sealmin_sat", 50, kwargs),
                }
            )

        elif command == "cropremove":
            self.args.update(
                {
                    "offset": self._get_with_default("offset", 0, kwargs),
                    "type": self._get_with_default("type", 1, kwargs),
                    "seal": self._get_with_default("seal", False, kwargs),
                    "ext": self._get_with_default("ext", "png", kwargs),
                    "sealcolor": self._get_with_default("sealcolor", False, kwargs),
                    "sealarea": self._get_with_default("sealarea", 80, kwargs),
                    "sealmin_sat": self._get_with_default("sealmin_sat", 50, kwargs),
                    "area": self._get_with_default("area", 1, kwargs),
                    "border": self._get_with_default("border", None, kwargs),
                }
            )

        # -------- print --------
        elif command == "print":
            # 处理边距参数，支持 CSS 简写
            # page_margins: 默认 [20,20,20,20]
            raw_page_margins = kwargs.get("page_margins")
            page_margins = self._normalize_margin_value(
                raw_page_margins, default=[20, 20, 20, 20]
            )
            self.args["page_margins"] = page_margins

            # left_page_margins: 若未提供则为 None
            raw_left = kwargs.get("left_page_margins")
            left_page_margins = self._normalize_margin_value(raw_left, default=None)
            self.args["left_page_margins"] = left_page_margins

            # right_page_margins: 若未提供则为 None
            raw_right = kwargs.get("right_page_margins")
            right_page_margins = self._normalize_margin_value(raw_right, default=None)
            self.args["right_page_margins"] = right_page_margins

            # 其余参数直接使用 _get_with_default（它们不需要特殊标准化）
            self.args.update(
                {
                    "pdf_name": self._get_with_default("pdf_name", None, kwargs),
                    "paper_size": self._get_with_default("paper_size", "A4", kwargs),
                    "orientation": self._get_with_default(
                        "orientation", "landscape", kwargs
                    ),
                    "title_printing": self._get_with_default(
                        "title_printing", False, kwargs
                    ),
                    "title_text": self._get_with_default("title_text", "", kwargs),
                    "title_font_size": self._get_with_default(
                        "title_font_size", 18, kwargs
                    ),
                    "title_color": self._get_with_default(
                        "title_color", "0,0,0", kwargs
                    ),
                    "title_position": self._get_with_default(
                        "title_position", "top", kwargs
                    ),
                    "title_orientation": self._get_with_default(
                        "title_orientation", "vertical", kwargs
                    ),
                    "title_switch_nodes": self._get_with_default(
                        "title_switch_nodes", None, kwargs
                    ),
                    "page_number_printing": self._get_with_default(
                        "page_number_printing", False, kwargs
                    ),
                    "page_number_start_page": self._get_with_default(
                        "page_number_start_page", 1, kwargs
                    ),
                    "page_number_end_page": self._get_with_default(
                        "page_number_end_page", None, kwargs
                    ),
                    "page_number_base": self._get_with_default(
                        "page_number_base", 0, kwargs
                    ),
                    "page_number_font_size": self._get_with_default(
                        "page_number_font_size", 18, kwargs
                    ),
                    "page_number_color": self._get_with_default(
                        "page_number_color", "0,0,0", kwargs
                    ),
                    "page_number_position": self._get_with_default(
                        "page_number_position", "bottom", kwargs
                    ),
                    "page_number_orientation": self._get_with_default(
                        "page_number_orientation", "vertical", kwargs
                    ),
                    "skip_pages": self._get_with_default("skip_pages", None, kwargs),
                }
            )

        # 其他命令（如 help）不处理

    def validate(self) -> None:
        """
        参数语义校验；全部来源(命令行/config json)统一校验。
        校验不通过抛出 ValueError，上层捕获并退出程序。
        不做IO写操作，不创建目录。
        """
        cmd = self.command
        if cmd is None:
            raise ValueError("未指定子命令")

        input_p: Path = self.get("input")
        workers = self.get("workers")

        # 通用校验
        if workers is not None and workers <= 0:
            raise ValueError(f"workers 必须大于0，当前={workers}")

        if not isinstance(input_p, Path):
            raise ValueError(f"input 必须为路径对象，得到 {type(input_p)}")

        if not input_p.exists():
            raise FileNotFoundError(f"输入路径不存在：{input_p.resolve()}")

        # -------- extract --------
        if cmd == "extract":
            zoom = self.get("zoom")
            batch_size = self.get("batch_size")
            ext = self.get("ext")
            if zoom < 1:
                raise ValueError(f"zoom 缩放因子必须 >=1，当前={zoom}")
            if batch_size < 1:
                raise ValueError(f"batch‑size 必须 >=1，当前={batch_size}")
            if ext not in ("jpg", "png"):
                raise ValueError(f"ext 仅支持 jpg/png，当前={ext}")
            start = self.get("start")
            end = self.get("end")
            if start is not None and start < 1:
                raise ValueError(f"start 页码必须 >=1，当前={start}")
            if end is not None and end < 1:
                raise ValueError(f"end 页码必须 >=1，当前={end}")
            if start is not None and end is not None and start > end:
                raise ValueError(f"start({start}) 不能大于 end({end})")
            pages = self.get("pages")
            if pages is not None:
                allowed_chars = set("0123456789,-")
                if any(ch not in allowed_chars for ch in str(pages)):
                    raise ValueError(f"pages 包含非法字符，示例：1,2,5‑7；输入:{pages}")

        # -------- crop --------
        elif cmd == "crop":
            area = self.get("area")
            ext = self.get("ext")
            border = self.get("border")
            if area not in (1, 2, 3):
                raise ValueError(f"area 仅允许 1/2/3，当前={area}")
            if ext not in ("jpg", "png"):
                raise ValueError(f"ext 仅支持 jpg/png，当前={ext}")
            self._validate_border(border)

        # -------- rembg --------
        elif cmd == "rembg":
            type_val = self.get("type")
            offset = self.get("offset")
            sealarea = self.get("sealarea")
            sealmin_sat = self.get("sealmin_sat")
            if type_val not in (1, 2, 3):
                raise ValueError(f"type 仅允许1/2/3，当前={type_val}")
            if sealarea < 1:
                raise ValueError(f"sealarea 印章面积阈值必须 >=1，当前={sealarea}")
            if not (0 <= sealmin_sat <= 255):
                raise ValueError(f"sealmin_sat 取值范围0‑255，当前={sealmin_sat}")

        # -------- cropremove --------
        elif cmd == "cropremove":
            area = self.get("area")
            type_val = self.get("type")
            border = self.get("border")
            sealarea = self.get("sealarea")
            sealmin_sat = self.get("sealmin_sat")

            if area not in (1, 2, 3):
                raise ValueError(f"area 仅允许 1/2/3，当前={area}")
            if type_val not in (1, 2, 3):
                raise ValueError(f"type 仅允许1/2/3，当前={type_val}")
            if sealarea < 1:
                raise ValueError(f"sealarea 印章面积阈值必须 >=1，当前={sealarea}")
            if not (0 <= sealmin_sat <= 255):
                raise ValueError(f"sealmin_sat 取值范围0‑255，当前={sealmin_sat}")
            self._validate_border(border)

        # -------- print --------
        elif cmd == "print":
            paper_size = self.get("paper_size")
            if not isinstance(paper_size, str) or paper_size.strip().upper() not in (
                "A3",
                "A4",
                "A5",
                "B5",
            ):
                raise ValueError(f"paper_size 仅支持 A3、A4、A5、B5，当前={paper_size}")
            orientation = self.get("orientation")
            if orientation not in ("landscape", "portrait"):
                raise ValueError(
                    f"orientation 仅支持 landscape/portrait，当前={orientation}"
                )

            # pdf_name 若提供，应为字符串
            pdf_name = self.get("pdf_name")
            if pdf_name is not None and not isinstance(pdf_name, str):
                raise ValueError("pdf_name 必须为字符串")

            # 边距参数已在 _build_args 中标准化，这里只需检查非负数（已保证为数字列表）
            for key in ("page_margins", "left_page_margins", "right_page_margins"):
                val = self.get(key)
                if val is not None:
                    if not isinstance(val, list) or len(val) != 4:
                        # 理论上不会发生，但保留防御
                        raise ValueError(f"{key} 应为四元素列表")
                    for v in val:
                        if v < 0:
                            raise ValueError(f"{key} 中的值不能为负数")

            # 位置仅允许 top / bottom
            pos = self.get("title_position")
            if pos not in ("top", "bottom"):
                raise ValueError(f"title_position 仅支持 top/bottom，当前={pos}")
            pos_num = self.get("page_number_position")
            if pos_num not in ("top", "bottom"):
                raise ValueError(
                    f"page_number_position 仅支持 top/bottom，当前={pos_num}"
                )

            # 文字方向
            for orient_key in ("title_orientation", "page_number_orientation"):
                orient_val = self.get(orient_key)
                if orient_val not in ("vertical", "horizontal"):
                    raise ValueError(
                        f"{orient_key} 仅支持 vertical/horizontal，当前={orient_val}"
                    )

            # 页码范围
            start = self.get("page_number_start_page")
            end = self.get("page_number_end_page")
            if start is not None and (not isinstance(start, int) or start < 1):
                raise ValueError(
                    f"page_number_start_page 必须为 >=1 的整数，当前={start}"
                )
            if end is not None and (not isinstance(end, int) or end < 1):
                raise ValueError(f"page_number_end_page 必须为 >=1 的整数，当前={end}")
            if start is not None and end is not None and start > end:
                raise ValueError(f"start({start}) 不能大于 end({end})")

            # title_switch_nodes 结构校验（可选）
            nodes = self.get("title_switch_nodes")
            if nodes is not None:
                if not isinstance(nodes, list):
                    raise ValueError("title_switch_nodes 必须为列表")
                for item in nodes:
                    if not isinstance(item, (list, tuple)) or len(item) < 2:
                        raise ValueError(
                            "title_switch_nodes 每项必须为 [页码, 标题] 或 [页码, 标题, side]"
                        )
                    try:
                        int(item[0])
                    except (ValueError, TypeError):
                        raise ValueError("标题切换节点页码必须为整数")
                    if len(item) > 3:
                        raise ValueError("每项最多3个元素")
                    if len(item) == 3 and item[2] not in ("left", "right", "both"):
                        raise ValueError("side 仅允许 left/right/both")

        else:
            raise ValueError(f"不支持的命令 {cmd}")

    @staticmethod
    def _validate_border(border: Any):
        """校验 border 参数格式；支持 None / "0" / "30" / "20,30" / "20,30,25" / "20,30,20,25" """
        if border is None:
            return
        s = str(border).strip()
        parts = s.split(",")
        if len(parts) not in (1, 2, 3, 4):
            raise ValueError(
                f"border 格式错误，支持1/2/3/4个数字；示例：30｜20,30｜20,30,25｜20,30,20,25；输入:{border}"
            )
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            raise ValueError(f"border 必须为数字，输入:{border}")
        for n in nums:
            if n < 0:
                raise ValueError(f"border 边距不能为负数，输入值 {n}")
