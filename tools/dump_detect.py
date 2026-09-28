# -*- coding: utf-8 -*-
"""诊断 detect 的类别判定：把**模型原话 + 消解结果**打出来，定位问题在哪一层。

排查「明明是双栏(两个 harfcontent) 却被识别成一个 fullcontent」这类问题时，
先别改代码——先看模型到底输出了什么、后处理又做了什么。本工具对每张图打印：

    模型原始:  <类别> conf=<置信度> [x1,y1,x2,y2] 宽占页% 中心占页%
    消解结果:  left=… right=… full=…  → slots=…   （= 生产代码真正会用的框）
    规则说明:  哪条互斥规则真的触发了（没触发则打「无」）

消解规则（与 `gujitrain/test/predict_bookcontent.py` 同规则，实现见
`utils.yolo_utils.resolve_content_boxes`）：

1. **窄整幅剔除**：整幅框宽必须 > 页宽 70%，否则视为失败检测丢弃
   （训练集里真整幅框宽 p5=88%，被误判出来的「窄整幅」只有 ~45%）；
2. **双半幅压制整幅**：半幅 ≥2 个 → 整幅框一律删；
3. **单半幅比置信度**：半幅恰好 1 个 → 与置信度最高的整幅比，整幅**严格更高**
   才留整幅（平局留半幅）；没有半幅时整幅原样保留。

由此**互斥被强制成立**，不会出现「两类并存」。

用法（本机用 anaconda python，见项目记忆）::

    python tools/dump_detect.py 某页.jpg
    python tools/dump_detect.py 某目录 --imgsz 1280        # 试不同推理尺寸
    python tools/dump_detect.py 某页.jpg --save out/       # 另存标注图

⚠️ ``--imgsz`` 只影响**模型原始**那一栏；`消解结果` 永远走生产设置（640，
= 训练 `train_common.IMGSZ`）。实测把 imgsz 调大更容易让模型判错，别拿它当修复手段。

⚠️ 本工具**只读**：不改任何配置、不写除 ``--save`` 以外的文件。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 图片扩展名（与 utils.file_utils.IMAGE_EXTS 同口径，这里只用于目录遍历）
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")


def _iter_images(target: Path):
    if target.is_file():
        yield target
        return
    for path in sorted(target.iterdir()):
        if path.suffix.lower() in IMAGE_EXTS:
            yield path


def _fmt(box, width: float) -> str:
    x1, y1, x2, y2 = box
    return (
        f"[{int(x1)},{int(y1)},{int(x2)},{int(y2)}]"
        f" 宽{(x2 - x1) / width * 100:5.1f}% 中心{(x1 + x2) / 2 / width * 100:5.1f}%"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="打印 detect 的模型原始输出与消解结果（只读）")
    parser.add_argument("target", help="图片文件或目录")
    parser.add_argument("--conf", type=float, default=0.25,
                        help="置信度阈值（默认 0.25，与项目一致）")
    parser.add_argument("--imgsz", type=int, default=640,
                        help="**模型原始**那一栏的推理尺寸（默认 640 = 生产/训练设置）")
    parser.add_argument("--save", default=None, help="把标注图另存到该目录（可选）")
    args = parser.parse_args()

    import utils
    from functions.detect import detect_page_content
    from ultralytics import YOLO

    weights = utils.model_path()
    model = YOLO(str(weights))
    names = model.names
    print(f"权重: {weights}\n类别: {names}\nconf={args.conf}  imgsz={args.imgsz}\n" + "=" * 80)
    if args.imgsz != 640:
        print("⚠️ --imgsz 不是生产设置：`模型原始:` 是本设置下的输出，"
              "`消解结果:` 仍是生产设置（640），两者不可直接比。\n")

    save_dir = Path(args.save) if args.save else None
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    for path in _iter_images(Path(args.target)):
        img = utils.imread(path)
        if img is None:
            print(f"❌ {path.name}: 读取失败")
            exit_code = 1
            continue
        h, w = img.shape[:2]
        boxes = model(img, conf=args.conf, imgsz=args.imgsz, verbose=False)[0].boxes
        raw = []
        for i in range(len(boxes)):
            raw.append((
                int(boxes.cls[i].cpu().numpy()),
                float(boxes.conf[i].cpu().numpy()),
                [float(v) for v in boxes.xyxy[i].cpu().numpy()],
            ))

        # 生产代码的完整链路：检测 → 互斥消解 → 取最大框 → 槽位
        page = detect_page_content(img, model)

        print(f"\n{path.name}  {w}x{h}")
        if not raw:
            print("  模型原始: 未检出任何框")
        for cls, conf, box in raw:
            print(f"  模型原始: {names.get(cls, cls):12s} conf={conf:.2f}  {_fmt(box, w)}")
        print(f"  消解结果: left={page.left} right={page.right} full={page.full}")
        print(f"            slots={page.slots()}")
        print(f"  规则说明: {'; '.join(page.notes) if page.notes else '无（未触发任何消解规则）'}")
        if page.notes:
            print("            ↳ 触发了互斥消解：模型原判被后处理改写，属**预期**行为")

        if save_dir:
            annotated = utils.draw_boxes(
                img, [page.left, page.right, page.full],
                names=["左框", "右框", "整幅"],
            )
            out = save_dir / f"{path.stem}-detect{path.suffix}"
            utils.imwrite(out, annotated)
            print(f"  标注图: {out}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
