"""
File: functions/base.py
Function 基类与并行执行引擎。

本模块提供 `FunctionBase`，它封装了：
- 输入路径解析（文件/目录）与输出路径计算辅助方法；
- 并发处理流水线：从 `collect_input_files` 获取待处理文件并使用线程池并行处理；
- 日志记录与失败重试机制（默认最多重试 max_retries 次）。

子类只需实现 `_process_single_image()`，返回包含 `status` 与 `file` 字段的字典。
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
import utils

from cli.command_args import CommandArgs

# 图片处理默认路径 Map
DEFAULT_TEMP_NAME_MAP = {
    "extract": "images",
    "crop": "crop",
    "rembg": "rembg",
    "cropremove": "rembg",
    "print": "pdf",
}


class FunctionBase:
    """抽象基类，提供通用执行引擎。

    关键约定：
    - `_process_single_image(path)`：子类实现单张图片处理逻辑，返回 `{'status': ..., 'file': filename, ...}`；
    - `_collect_input_files()`：默认从 `utils.collect_image_files` 获取输入文件列表，子类可以覆盖；
    - `execute()`：负责并发调度、重试、日志写入与最终统计。
    """

    def __init__(self, command_args: CommandArgs):
        self.command_args = command_args
        self.cmd = command_args.get("command")
        self.default_temp_name = DEFAULT_TEMP_NAME_MAP.get(self.cmd, "temp")

        # 原始输入（CommandArgs 已将 input 标准化为 Path）
        self.input_raw = command_args.get("input", ".")
        self.input: Path = self.input_raw

        # 判断输入是文件还是目录
        self.is_file = self.input.is_file() or bool(self.input.suffix)
        if self.is_file:
            self.parent_path = self.input.parent
        else:
            self.parent_path = self.input

        if not self.input.exists():
            raise FileNotFoundError(f"输入路径不存在: {self.input}")

        # 输出路径相关占位（子类在初始化时通常会计算 self.outpath）
        self.output_raw: Optional[str] = command_args.get("output")
        self.base_output: Path = self.parent_path / self.default_temp_name
        self.outpath: Optional[Path] = None

        # 日志路径（由 execute 设置）
        self.log_path: Optional[Path] = None
        self.fail_log_path: Optional[Path] = None

    def _parse_path(self, path_str: str) -> Path:
        return Path(path_str).expanduser().resolve()

    def parse_user_output(self, raw_out: Optional[str], file_stem: str = None) -> Path:
        """统一解析用户传入的 `--output` 参数。

        规则：
        - 若未指定，文件输入默认使用父目录下以文件名为名的目录；目录输入使用 parent/temp 作为默认输出；
        - 若只传入单个名称（无路径分隔符），则相对于输入目录创建；
        - 若传入包含路径分隔符，则按绝对/相对路径解析为最终 Path。
        """
        if raw_out is None or str(raw_out).strip() == "":
            if self.is_file and file_stem is not None:
                return self.parent_path / file_stem
            else:
                return self.base_output
        out_str = raw_out.strip()
        if "/" not in out_str and "\\" not in out_str:
            return self.parent_path / out_str
        return self._parse_path(out_str)

    def make_out_dir(self):
        if self.outpath is None:
            raise RuntimeError("未计算最终输出路径 self.outpath")
        self.outpath.mkdir(parents=True, exist_ok=True)

    # ---------- 子类需要实现的方法 ----------
    def _process_single_image(self, image_path: Path) -> dict:
        """处理单张图片，返回结果字典。子类必须实现。"""
        raise NotImplementedError

    def _collect_input_files(self) -> List[Path]:
        """收集输入文件，默认使用 utils.collect_image_files。子类可覆盖以实现自定义行为。"""
        return utils.collect_image_files(self.input, self.is_file)

    # ---------- 通用执行引擎 ----------
    def execute(self) -> dict:
        """执行入口：并行处理所有输入图片，支持多轮重试与日志记录。

        实现细节：
        - 使用 ThreadPoolExecutor 并发调用 `_process_single_image()`；
        - 对出错的文件会记录到失败日志，并在可重试次数内再次尝试；
        - 最终按文件名排序导出统计信息与输出路径。
        """
        print(f"输入路径：{self.input}")
        print(f"输出目录：{self.outpath}")

        image_files = self._collect_input_files()
        if not image_files:
            print("未找到图片文件")
            return {"processed": 0, "output": str(self.outpath)}

        # 清理输出目录（如果用户指定 clean）
        clean = self.command_args.get("clean", True)
        if clean and self.outpath.exists():
            shutil.rmtree(self.outpath)
        self.outpath.mkdir(parents=True, exist_ok=True)

        # 并发与重试策略
        workers = max(
            1, int(self.command_args.get("workers", max(1, min(8, len(image_files)))))
        )
        max_retries = 2
        results_by_file = {}
        self.log_path = self.outpath / f"{self.cmd}_process.log"
        self.fail_log_path = self.outpath / f"{self.cmd}_failures.log"

        # 基本运行参数写入日志
        self._write_log(f"输入路径: {self.input}")
        self._write_log(f"输出目录: {self.outpath}")
        self._write_log(f"线程数: {workers}")
        self._write_log(f"图片总数: {len(image_files)}")

        def _run_round(current_files):
            """对一轮文件集合并行处理，返回每文件的结果列表。"""
            if not current_files:
                return []
            round_results = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_map = {
                    executor.submit(self._process_single_image, p): p
                    for p in current_files
                }
                for future in as_completed(future_map):
                    p = future_map[future]
                    try:
                        result = future.result()
                        round_results.append(result)
                        print(f"处理完成: {p.name} -> {result['status']}")
                        self._write_log(f"[完成] {p.name} -> {result['status']}")
                    except Exception as exc:
                        # 记录失败，并把失败信息写入失败日志，便于离线排查
                        print(f"处理失败: {p.name} -> {exc}")
                        round_results.append(
                            {"status": "error", "file": p.name, "reason": str(exc)}
                        )
                        self._write_log(f"[失败] {p.name} -> {exc}")
                        self._write_fail_log(f"{p.name}: {exc}")
            return round_results

        pending_files = list(image_files)
        for attempt in range(1, max_retries + 2):
            if not pending_files:
                break
            round_results = _run_round(pending_files)
            self._write_log(f"===== 第 {attempt} 轮结束 =====")
            next_pending = []
            for item in round_results:
                file_name = item.get("file")
                if item.get("status") == "error" and attempt <= max_retries:
                    # 在重试时尝试重建原始路径（针对目录输入时）
                    origin = self.input / file_name if not self.is_file else self.input
                    if origin.exists():
                        next_pending.append(origin)
                    else:
                        results_by_file[file_name] = item
                        self._write_log(f"无法重试，文件丢失: {file_name}")
                else:
                    results_by_file[file_name] = item
            pending_files = next_pending

        # 按文件名排序输出结果并统计状态分布
        results = [results_by_file[f] for f in sorted(results_by_file)]
        status_counts = {}
        for item in results:
            status = item.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        self._write_log(f"===== 最终统计 =====")
        for status, count in status_counts.items():
            self._write_log(f"{status}: {count}")
        self._write_log(f"日志文件: {self.log_path}")
        self._write_log(f"失败清单文件: {self.fail_log_path}")

        return {
            "processed": len(results),
            **status_counts,
            "output": str(self.outpath),
        }

    def _write_log(self, msg: str):
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")

    def _write_fail_log(self, msg: str):
        if self.fail_log_path:
            with open(self.fail_log_path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
