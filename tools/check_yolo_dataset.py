# -*- coding: utf-8 -*-
"""校验「导出YOLO标注」导出的数据集切片**真的对不对**（用户 2026-10-16）。

## 为什么不能拿「导出标注图」当校验

那张核对图与 ``labels/*.txt`` 是**同一份内存坐标**的两个出口——分母算错、
左右写反、序号错位，两边会一起错，摆在一起看永远是"一致的"。

所以本工具**只从落地文件反推**：读切片里的 ``images/`` 与 ``labels/``，
把归一化坐标反算回像素，再与基准逐框比。四层：

1. **配对**：``images/`` 与 ``labels/`` 逐编号配对（含空标签 = 负样本）；
2. **格式**：每行 5 个字段、类别号 ∈ {0,1}、``cx,cy,w,h ∈ (0,1]``、面积 > 0；
3. **几何**：反算出的像素框 ↔ 基准 ``boxes.json`` 的槽位逐框比对（±``--tol``
   px）。这一层才抓得到"归一化分母用错""cx/cy 或 w/h 写反""图与标签序号错位"；
4. **视觉**：把标签反画回图，写到 ``<切片>/_check/`` 供人眼翻页核对（
   看"左右框错边""整幅被标成半幅"这类只有眼睛能判的错）。

## 基准怎么给

- **自动**（推荐）：切片自带的 ``data.json``（导出时写的凭据，含**任务号**）
  会指明基准在哪。所以任务流程导出的切片直接跑就行：

      python tools/check_yolo_dataset.py C:/Users/liuzu/Documents/b8

- **显式给任务号**：``--task 0020``（自动那条不生效时用，如切片是老版本导的）；
- **独立「检测文本框」导出的切片没有任务号**（它不属任何任务）：``data.json``
  里只有源名，此时给 ``--pages <源图片目录> --boxes <输出目录>/boxes.json``。

省略基准也能跑（只做 ①②③ 里的自洽部分 + ④），只是抓不到"整体偏移"这类错。

## 用法

    python tools/check_yolo_dataset.py D:/ds/bookcontent/b1              # 自动读 data.json
    python tools/check_yolo_dataset.py D:/ds/bookcontent/b1 --task 0020  # 显式指定任务
    python tools/check_yolo_dataset.py D:/ds/bookcontent/b1 --pages 某批图/ --boxes 输出目录/boxes.json
    python tools/check_yolo_dataset.py D:/ds/bookcontent/b1 --no-overlay

退出码：``0`` 全部通过；``1`` 有错误（``[FAIL]`` 那些）；``2`` 用法/输入问题。
⚠️ 本工具**只读**输入，只写 ``--overlay-dir``（默认 ``<切片>/_check``）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.box_geometry import (  # noqa: E402
    YOLO_CLASS_NAMES,
    is_full_content,
    present_boxes,
)
from utils.box_draw import BOX_COLORS_BGR  # noqa: E402
from utils.sort_utils import natural_sort_key  # noqa: E402

#: 切片自带的凭据文件名（导出时写的，含任务号）。⚠️ 与
#: ``desktop.services.detect_export.SLICE_META_NAME`` 是**同一个约定**——
#: 这里不 import desktop（工具要能在没装 GUI 依赖时跑），所以字面量写死，
#: 并由 ``tests/selftests/dev_yolo.py`` 钉住两者一致。
SLICE_META_NAME = "data.json"

#: 「导出YOLO标注」写出的文件名形状：``<名称>-<页序>.<后缀>``（见
#: ``desktop.services.detect_export`` 的 ``export_yolo``）。
_NAME_RE = re.compile(r"^(?P<prefix>.+)-(?P<number>\d+)$")

#: 类别号 → 中文说明（只用于打印）
_CLASS_LABEL = {
    0: f"0 {YOLO_CLASS_NAMES[0]}（左框/右框）",
    1: f"1 {YOLO_CLASS_NAMES[1]}（整幅）",
}

#: 图像后缀（切片里认这些；与 utils.file_utils.IMAGE_EXTS 同口径）
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")


class Report:
    """收集/打印 ``[OK]/[WARN]/[FAIL]`` 三类结论，最后给退出码。"""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def ok(self, text: str) -> None:
        print(f"  [OK]   {text}")

    def warn(self, text: str) -> None:
        self.warnings.append(text)
        print(f"  [WARN] {text}")

    def fail(self, text: str) -> None:
        self.errors.append(text)
        print(f"  [FAIL] {text}")

    def section(self, title: str) -> None:
        print(f"\n{title}")

    def exit_code(self) -> int:
        print()
        if self.errors:
            print(f"结论：**没通过**（{len(self.errors)} 个错误 / "
                  f"{len(self.warnings)} 个警告）")
            return 1
        if self.warnings:
            print(f"结论：通过（0 个错误 / {len(self.warnings)} 个警告，"
                  "警告项建议人工看一眼）")
            return 0
        print("结论：全部通过")
        return 0


# ------------------------------------------------------------------ 切片解析
def scan_slice(slice_dir: Path, report: Report):
    """扫切片目录 → ``{编号: (图片路径, 标签路径)}`` 与前缀。

    只认 ``images/`` 与 ``labels/`` 两个子目录（与 ultralytics 的默认布局一致）。
    """
    images_dir = slice_dir / "images"
    labels_dir = slice_dir / "labels"
    if not images_dir.is_dir() or not labels_dir.is_dir():
        raise SystemExit(
            f"切片目录里没有 images/ 与 labels/：{slice_dir}\n"
            "（传的应该是「导出目录/名称」那一层）"
        )

    def collect(directory: Path, suffixes: tuple[str, ...]) -> dict[int, Path]:
        found: dict[int, Path] = {}
        prefixes: set[str] = set()
        for path in sorted(directory.iterdir(), key=lambda p: natural_sort_key(p.name)):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            match = _NAME_RE.match(path.stem)
            if match is None:
                report.fail(f"{directory.name}/{path.name}：名字不是「名称-编号」形状")
                continue
            prefixes.add(match.group("prefix"))
            number = int(match.group("number"))
            if number in found:
                report.fail(f"{directory.name}：编号 {number} 出现两次"
                            f"（{found[number].name} 与 {path.name}）")
                continue
            found[number] = path
        if len(prefixes) > 1:
            report.fail(f"{directory.name}：同一批里出现了多个名称前缀 "
                        f"{sorted(prefixes)}——不是同一次导出")
        return found

    images = collect(images_dir, _IMAGE_EXTS)
    labels = collect(labels_dir, (".txt",))
    prefix = ""
    for path in list(images.values()) + list(labels.values()):
        match = _NAME_RE.match(path.stem)
        if match is not None:
            prefix = match.group("prefix")
            break
    return images, labels, prefix


def image_size(path: Path):
    """图片原始尺寸 ``(宽, 高)``；读不出来返回 ``None``。

    ⚠️ 取的是**切片里那张复制过来的图**，不是源目录的图——训练时 ultralytics
    读的正是它，所以标签必须按它的尺寸能反算回原框。
    """
    try:
        from PIL import Image
        with Image.open(path) as image:
            return image.size
    except Exception:  # noqa: BLE001 - 读不出来由调用方报成 [FAIL]
        return None


def parse_label(path: Path):
    """标签文件 → ``[(类别, [cx, cy, w, h]), …]``；同时回传格式错误列表。"""
    rows: list[tuple[int, list[float]]] = []
    problems: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [], [f"{path.name}：读不出来（{exc}）"]
    for index, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue  # 空行无害（null 标签文件就是全空）
        parts = line.split()
        if len(parts) != 5:
            problems.append(f"{path.name}:{index} 应为 5 个字段，实际 {len(parts)}：{line!r}")
            continue
        try:
            cls = int(parts[0])
            values = [float(v) for v in parts[1:]]
        except ValueError:
            problems.append(f"{path.name}:{index} 字段不是数字：{line!r}")
            continue
        if cls not in _CLASS_LABEL:
            problems.append(f"{path.name}:{index} 类别号 {cls} 不在 {sorted(_CLASS_LABEL)}")
            continue
        rows.append((cls, values))
    return rows, problems


# ------------------------------------------------------------------ 基准
def default_data_dir() -> Path:
    """任务数据根：``~/Documents/guji``（与 ``desktop.utils.files.guji_data_dir`` 同）。"""
    return Path.home() / "Documents" / "guji"


def load_slice_meta(slice_dir: Path) -> dict:
    """切片自带的 ``data.json``（导出时写的凭据）；没有/坏了都给 ``{}``。

    形状见 ``desktop.services.detect_export._write_slice_meta``。
    """
    import json

    path = slice_dir / SLICE_META_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def try_baseline(task_id: str, data_dir: Path) -> tuple[list[Path], dict | None]:
    """按任务号找基准 → ``(pages, boxes)``；找不到返回 ``([], None)``。

    找不到（任务被删、清单写坏）**不抛异常**：切片本身还能做自洽校验，而
    "任务已经删了"是完全正常的状态——不该让整个工具没法用。
    """
    try:
        return pages_for_task(task_id, data_dir), load_boxes(
            data_dir / "tasks" / task_id / "boxes.json"
        )
    except SystemExit as exc:
        print(f"  [WARN] 按任务号 {task_id} 找不到基准：{exc}（跳过逐框比对）")
        return [], None


def pages_for_task(task_id: str, data_dir: Path) -> list[Path]:
    """任务页面清单里的页面路径（**清单顺序 = 页序**）。

    ⚠️ 与 ``taskdetail._manifest_paths()`` 同一口径：只取**还存在**的文件——
    导出就是按这个过滤后的顺序编的号，这里少算/多算一页，后面全部错位。
    """
    import json

    manifest = data_dir / "tasks" / task_id / "pages.json"
    if not manifest.is_file():
        raise SystemExit(f"读不到页面清单：{manifest}")
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise SystemExit(f"页面清单格式不对：{manifest}")
    return [Path(e["file"]) for e in entries if e.get("file") and Path(e["file"]).exists()]


def pages_for_dir(directory: Path) -> list[Path]:
    """目录里的图片，按**页序自然排序**（``utils.sort_utils``，与导出同一把键）。"""
    return sorted(
        (p for p in directory.iterdir() if p.suffix.lower() in _IMAGE_EXTS),
        key=lambda p: natural_sort_key(p.name),
    )


def load_boxes(boxes_path: Path) -> dict:
    """``boxes.json`` → ``{stem: 槽位}``（只取槽位，不看 origin）。

    ⚠️ 形状对不上就**当场退出**（而不是当成"一页有框都没有"）：把一份别的
    JSON 喂进来时，若静默算出"基准 0 页有框"，后面每一页都会报"框数对不上"
    ——满屏假错误，真正的原因（拿错文件）反而被埋掉。
    """
    import json

    if not boxes_path.is_file():
        raise SystemExit(f"读不到基准 boxes.json：{boxes_path}")
    data = json.loads(boxes_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"基准不是「页名 → 记录」的对象：{boxes_path}")
    odd = [key for key, entry in data.items()
           if not isinstance(entry, dict) or "boxes" not in entry]
    if odd:
        raise SystemExit(
            f"基准形状不对（应该有 boxes/origin 字段）：{boxes_path}\n"
            f"可疑条目：{odd[:5]}"
        )
    return {
        key: list(entry.get("boxes") or [])
        for key, entry in data.items()
    }


def expected_rows(slots) -> list[tuple[int, list[int]]]:
    """槽位 → 导出时**本该写出**的 ``[(类别, [x1,y1,x2,y2]), …]``。

    规则与 ``detect_export.yolo_label_lines`` 完全一致（那是唯一实现，这里只是
    把它反着用：拿框当期望值）——左/右都算 0 号，整幅才是 1 号；半幅两个框按
    槽位顺序（左在前）。
    """
    present = present_boxes(slots)
    if not present:
        return []
    cls = 1 if is_full_content(slots) else 0
    return [(cls, [int(v) for v in box[:4]]) for box in present]


# ------------------------------------------------------------------ 逐项校验
def check_pairs(numbers, images, labels, report: Report) -> None:
    """① 配对：每张图都要有同名标签，反过来也一样。"""
    report.section("① 配对（images/ ↔ labels/）")
    image_only = sorted(set(images) - set(labels))
    label_only = sorted(set(labels) - set(images))
    for number in image_only:
        report.fail(f"编号 {number}：只有图片 {images[number].name}，缺同名标签")
    for number in label_only:
        report.fail(f"编号 {number}：只有标签 {labels[number].name}，缺同名图片")
    if numbers:
        missing = [n for n in range(1, max(numbers) + 1) if n not in images]
        if missing:
            report.warn(
                f"编号不连续：1..{max(numbers)} 里缺 {len(missing)} 个"
                f"（{'、'.join(str(n) for n in missing[:8])}"
                f"{'…' if len(missing) > 8 else ''}）"
                "——导出时源图读不出来的页会被跳过，留空号属预期；"
                "但若你没删过图，就要查一查。"
            )
    if not image_only and not label_only:
        report.ok(f"编号两端齐备：{len(images)} 张图 / {len(labels)} 个标签")


def check_format(numbers, labels, report: Report) -> dict[int, list]:
    """② 格式 + 取值范围；返回 ``{编号: [(类别, [cx,cy,w,h]), …]}``。"""
    report.section("② 格式（每行 5 字段、类别号、归一化范围）")
    parsed: dict[int, list] = {}
    problems: list[str] = []
    bad_range: list[str] = []
    classes: dict[int, int] = {}
    empty = 0
    total_rows = 0
    for number in numbers:
        if number not in labels:
            # 缺文件由 ① 报错，这里不算"空标签"——两者含义完全不同：
            # 空标签是**负样本**（合法、是训练要的），缺文件是**漏写**。
            parsed[number] = []
            continue
        rows, issues = parse_label(labels[number])
        parsed[number] = rows
        problems.extend(issues)
        if not rows:
            empty += 1
        total_rows += len(rows)
        for cls, (cx, cy, w, h) in rows:
            classes[cls] = classes.get(cls, 0) + 1
            if not (0 < cx <= 1 and 0 < cy <= 1 and 0 < w <= 1 and 0 < h <= 1):
                bad_range.append(f"{labels[number].name}：cx={cx} cy={cy} w={w} h={h}")
            if cx - w / 2 < -1e-6 or cx + w / 2 > 1 + 1e-6 \
                    or cy - h / 2 < -1e-6 or cy + h / 2 > 1 + 1e-6:
                report.warn(
                    f"{labels[number].name}：框越出图外"
                    f"（cx±w/2={cx - w / 2:.4f}..{cx + w / 2:.4f}）"
                    "——训练时会被裁掉，多半是框坐标本身不对"
                )
    for issue in problems[:20]:
        report.fail(issue)
    if len(problems) > 20:
        report.fail(f"…另有 {len(problems) - 20} 处格式问题（略）")
    for issue in bad_range[:20]:
        report.fail(issue)
    if len(bad_range) > 20:
        report.fail(f"…另有 {len(bad_range) - 20} 处取值问题（略）")
    if not problems and not bad_range:
        report.ok(f"{total_rows} 行标签全部合法（{empty} 个空标签 = 负样本）")
    if classes:
        detail = "、".join(
            f"{_CLASS_LABEL.get(cls, cls)} × {count}"
            for cls, count in sorted(classes.items())
        )
        report.ok(f"类别号分布：{detail}")
        if 1 not in classes and total_rows:
            report.warn("一个整幅（1 号）都没有——若这批书里确实有整幅页，就是类别号写错了")
    return parsed


def check_geometry(numbers, labels, parsed, sizes, pages, boxes, tol, report: Report):
    """③ 几何：标签反算回像素 ↔ 基准槽位逐框比。

    ``pages`` / ``boxes`` 任一为空就只做"与自身自洽"的部分（尺寸能不能反算）。
    """
    report.section("③ 几何（反归一化 ↔ 基准 boxes.json）")
    compared = 0
    bad: list[str] = []
    if not pages or boxes is None:
        report.warn(
            "没给基准（--task 或 --pages + --boxes）：只查了尺寸能否反算，"
            "没查「标签与检测框是否一致」"
        )
    for number in numbers:
        if number not in labels:
            continue
        size = sizes.get(number)
        if size is None:
            report.fail(f"{labels[number].name}：读不到图片尺寸，无法验证几何")
            continue
        width, height = size
        page = pages[number - 1] if pages and 0 < number <= len(pages) else None
        if page is None or boxes is None:
            continue
        key = page.stem
        slots = boxes.get(key, [])
        want = expected_rows(slots)
        got = parsed.get(number, [])
        if len(want) != len(got):
            bad.append(
                f"{labels[number].name}（页 {key}）：框数对不上——"
                f"标签 {len(got)} 个 / 基准 {len(want)} 个"
            )
            continue
        for (want_cls, want_box), (got_cls, values) in zip(want, got):
            compared += 1
            cx, cy, w, h = values
            x1 = (cx - w / 2) * width
            y1 = (cy - h / 2) * height
            x2 = (cx + w / 2) * width
            y2 = (cy + h / 2) * height
            if got_cls != want_cls:
                bad.append(
                    f"{labels[number].name}（页 {key}）：类别号应为 "
                    f"{want_cls}（{YOLO_CLASS_NAMES[want_cls]}），实际 {got_cls}"
                )
            drift = max(
                abs(x1 - want_box[0]), abs(y1 - want_box[1]),
                abs(x2 - want_box[2]), abs(y2 - want_box[3]),
            )
            if drift > tol:
                bad.append(
                    f"{labels[number].name}（页 {key}）：反算框偏离 {drift:.1f}px "
                    f"（容差 {tol}）——标签 [{x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}] "
                    f"vs 基准 {want_box}"
                )
    for issue in bad[:20]:
        report.fail(issue)
    if len(bad) > 20:
        report.fail(f"…另有 {len(bad) - 20} 处几何不一致（略）")
    if not bad and compared:
        report.ok(f"{compared} 个框与基准逐框一致（容差 {tol}px）")
    elif not compared and boxes is not None:
        report.warn("没有一个框参与比对（页面清单/基准对不上编号？）")


def write_overlays(numbers, labels, parsed, images, sizes, out_dir: Path, report: Report) -> int:
    """④ 把标签反画回图，供人眼核对；返回画出的张数。"""
    report.section("④ 视觉核对图（把 labels 反画回图）")
    import utils

    drawn_boxes = 0
    written = 0
    out_dir.mkdir(parents=True, exist_ok=True)
    for number in numbers:
        if number not in labels or number not in images:
            continue
        size = sizes.get(number)
        if size is None:
            continue
        image = utils.imread(images[number])
        if image is None:
            report.warn(f"{images[number].name}：读不出来，跳过核对图")
            continue
        width, height = size
        boxes: list[list[int]] = []
        names: list[str] = []
        colors: list[tuple[int, int, int]] = []
        for cls, (cx, cy, w, h) in parsed.get(number, []):
            boxes.append([
                int(round((cx - w / 2) * width)), int(round((cy - h / 2) * height)),
                int(round((cx + w / 2) * width)), int(round((cy + h / 2) * height)),
            ])
            names.append(YOLO_CLASS_NAMES[cls])
            # 半幅用左框色（绿）、整幅用靛蓝——与界面里那套配色同源
            colors.append(BOX_COLORS_BGR[3 if cls == 1 else 0])
        target = out_dir / f"{labels[number].stem}.jpg"
        utils.imwrite(target, utils.draw_boxes(image, boxes, names=names, colors=colors))
        drawn_boxes += len(boxes)
        written += 1
    if written:
        report.ok(f"{written} 张核对图（{drawn_boxes} 个框）→ {out_dir}")
    else:
        report.warn("一张核对图都没画出来")
    return written


# ------------------------------------------------------------------ 入口
def main() -> int:
    parser = argparse.ArgumentParser(
        description="校验「导出YOLO标注」导出的数据集切片（只读输入）",
    )
    parser.add_argument("slice_dir", help="切片目录（含 images/ 与 labels/，即 <导出目录>/<名称>）")
    parser.add_argument("--task", default=None,
                        help="任务号（如 0020）：显式指定基准任务；不给则读切片自带的 data.json")
    parser.add_argument("--data-dir", default=None,
                        help="数据根目录（默认 ~/Documents/guji，仅按任务找基准时用）")
    parser.add_argument("--pages", default=None,
                        help="原始页面图片目录（按自然排序 = 页序）；独立任务那条链用")
    parser.add_argument("--boxes", default=None,
                        help="基准 boxes.json（与 --pages 搭配）")
    parser.add_argument("--tol", type=float, default=2.0,
                        help="几何比对容差（像素，默认 2）")
    parser.add_argument("--overlay-dir", default=None,
                        help="核对图输出目录（默认 <切片>/_check）")
    parser.add_argument("--no-overlay", action="store_true", help="不画核对图")
    args = parser.parse_args()

    slice_dir = Path(args.slice_dir)
    report = Report()

    # ---- 切片自带的凭据（导出时写的 data.json）----
    meta = load_slice_meta(slice_dir)
    if meta:
        task_in_meta = str(meta.get("task_id") or "")
        print(f"切片凭据: {meta.get('name') or '（无名）'}   "
              f"任务 {task_in_meta or '（独立任务导出，没有任务号）'}"
              f"   源 {meta.get('source') or '（未记）'}")
        names = meta.get("class_names")
        if names and list(names) != list(YOLO_CLASS_NAMES):
            report.fail(
                f"data.json 记的类别顺序 {list(names)} 与当前代码 "
                f"{list(YOLO_CLASS_NAMES)} 不一致——按老顺序训练会让两类互换"
            )
        if args.task and task_in_meta and args.task != task_in_meta:
            report.warn(f"--task {args.task} 与 data.json 里的 {task_in_meta} 不一致，"
                        "以 --task 为准")

    data_dir = Path(args.data_dir) if args.data_dir else default_data_dir()
    pages: list[Path] = []
    boxes: dict | None = None
    if args.task:
        pages, boxes = try_baseline(args.task, data_dir)
    elif args.pages and args.boxes:
        pages = pages_for_dir(Path(args.pages))
        boxes = load_boxes(Path(args.boxes))
    elif args.pages or args.boxes:
        raise SystemExit("--pages 与 --boxes 必须一起给（只给一个没法把编号对回页面）")
    else:
        # 没显式给基准：看切片自己的凭据里有没有任务号（任务流程导出的一定有）
        task_in_meta = str(meta.get("task_id") or "")
        if task_in_meta:
            print(f"（按 data.json 里的任务号 {task_in_meta} 找基准）")
            pages, boxes = try_baseline(task_in_meta, data_dir)
        else:
            print("（切片里没有任务号，也没有 --task/--pages：只做自洽校验）")

    print(f"切片目录: {slice_dir}")
    if pages and boxes is not None:
        print(f"页序基准: {len(pages)} 页（{pages[0].parent}）")
        print(f"框基准:   {sum(1 for v in boxes.values() if any(v))} 页有框")

    images, labels, prefix = scan_slice(slice_dir, report)
    numbers = sorted(set(images) | set(labels))
    if not numbers:
        raise SystemExit(f"切片里一张图/一个标签都没有：{slice_dir}")
    print(f"名称前缀: {prefix or '（读不出来）'}    "
          f"编号 {min(numbers)}..{max(numbers)}（{len(numbers)} 个）")
    if pages and max(numbers) > len(pages):
        report.fail(f"编号最大到 {max(numbers)}，但页面清单只有 {len(pages)} 页"
                    "——切片与这个任务对不上（是不是拿错了 --task？）")

    # 尺寸一律取切片里那张图（训练读的就是它）
    sizes: dict[int, tuple[int, int]] = {}
    for number in numbers:
        if number not in images:
            continue
        size = image_size(images[number])
        if size is None:
            report.fail(f"{images[number].name}：读不出图片尺寸（文件坏了？）")
            continue
        sizes[number] = size

    check_pairs(numbers, images, labels, report)
    parsed = check_format(numbers, labels, report)
    check_geometry(numbers, labels, parsed, sizes, pages, boxes, args.tol, report)

    if not args.no_overlay:
        out_dir = Path(args.overlay_dir) if args.overlay_dir else slice_dir / "_check"
        write_overlays(numbers, labels, parsed, images, sizes, out_dir, report)
    return report.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
