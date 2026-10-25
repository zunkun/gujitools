# WebP 格式可行性评估报告：extract / 检测提交 / 去底色

> 日期：2026-10-25
> 范围：`stages/extract`、`stages/detect`（检测提交裁图）、`stages/rembg`
> 三类产物的编码格式能不能从 JPG/PNG 换成 WebP，换完页面能不能正确渲染。
> **测量阶段未改任何生产代码**；2026-10-25 已按第 9 节落地：检测提交裁图改为
> **JPEG q95（4:4:4）**，extract 的导出路径保持 JPEG q95，rembg 保持 PNG。
> 探针见 [probe_webp_benchmark.py](../../tests/probe_webp_benchmark.py)。

## 结论摘要

1. **技术上完全可用**：本机 OpenCV 4.13、Pillow 12.2、PySide6 6.11 都能
   **读写** WebP；Qt 的 `QImageReader`（含 `setScaledSize` 缩放解码）和
   `QImageWriter` 都支持 WebP，页面渲染像素与 PIL 解码一致（PSNR 与编码侧
   完全吻合）。真实 PDF 走 `extract_single_page(ext="webp")` 也能落盘并被
   cv2/PIL/Qt 三端正确读取。
2. **但「能不能用」和「该不该用」是两件事**：
   - **检测提交裁图是唯一明确划算的一步**：现状 PNG **8.58 MB/张**
     （任务 0015）→ WebP q90 **1.19 MB/张（0.14×）**；全量 370.2 →
     51.3 MB。cv2 编码 828 ms/张，与现状 PNG 编码 893 ms/张**基本持平**；
     经 `utils.rembg_page` 二值化后与原图只有 **0.1% 像素差异**，去底色
     产物 PNG 体积几乎不变（101.4 → 100.8 KB）。任务 0021 同样成立：
     2.64 MB → 0.47 MB（0.19×），377.0 → 69.9 MB。若更看重速度/改动面，
     同一步用 JPG q95 只省 66%（8.58 → 2.94 MB），但编码快 14.5 倍、
     解码快 2.2 倍，见 3.2.1。
   - **extract 不建议换**：现在 JPEG 扫描页走 quick 路径是**原码流直拷**
     （体积就是扫描件自己的 JPEG 质量）。换成 WebP 必须解码再编码：
     - 源 JPEG 质量高时（任务 0015，4.1 MB/页）webp q90 约 1.80 MB（0.43×），
       但单页编码从 ~0.1 s 涨到 2.9 s（PIL）/ 1.44 s（cv2）；
     - 源 JPEG 已经压得很紧时（任务 0021，0.97 MB/页）webp q90 反而
       **1.09 MB（1.16×，更大）**。
     - 结论：省不省空间取决于源文件，**不可能稳定赢过直拷**，还要放弃
       零解码零重编码的快通道。
   - **rembg 产物保持 PNG**：1 位调色板 PNG 已是最省形态，webp 无损只小
     约 26%（112.8 → 83.4 KB），有损反而更大（123.6 KB）且编码慢 5 倍；
     而 Pillow 解码 WebP 的峰值内存约为 PNG 的 2 倍，绝对收益不值得。
3. **CPU 代价集中在编码**：PIL 编码 WebP 比 JPEG 慢 **20~30 倍**、比 PNG
   慢约 **2 倍**；**cv2 编码器比 PIL 快约 2 倍**，检测裁图换 WebP 必须用
   cv2 才能做到「不增加编码耗时」。
4. **内存风险在 Qt 缩放解码**：Qt 对 WebP **不做按需缩放解码**，256px
   缩略图也要先整幅解码——3506×5089 页峰值增量 83.8 MB（JPEG 14.2 MB，
   **5.9 倍**），无损 WebP 156.6 MB（11 倍）。若 extract 改 WebP，任务列表
   缩略图生成会明显变慢、吃内存；检测裁图只在后端处理，不走 Qt 缩略图，
   风险可控。
5. **画质/检测框**：WebP q90 与「无损源」的 YOLO 框差 0~10 px，而当前
   JPEG q95 与无损源差到 50 px——**webp q90 不劣于现状**。检测框本身就不
   是跨编码逐位稳定的，不能拿「与 jpg 框不完全相同」当成 WebP 的问题。
6. **落地前提**：现在直接换 webp 会**静默坏链路**（页面清单看不到、print
   漏页、缩略图回落失效、编辑器写回失败）。必须同步改第 8 节列出的 8 处
   后缀清单，否则「页面正确渲染」不成立。

## 1. 测试环境与素材

| 项 | 值 |
| --- | --- |
| 机器 | Windows 11，AMD Ryzen 5 3600（6 核 12 线程），16 GB 内存 |
| 运行时 | Python 3.10.20，Pillow 12.2.0，OpenCV 4.13.0，PySide6 6.11.1，PyMuPDF |
| 主素材 | 任务 0015：extract 168 页（3506×5089）、detect 40 张、rembg 10 张 |
| 交叉验证 | 任务 0021：extract 73 页（2400×2380）、detect 144 张、rembg 144 张 |
| 抽样 | 每类均匀抽 4 张；单线程计时，取**真中位数**（偶数个取中间两值平均） |
| WebP 参数 | Pillow `method=4`；LOSSLESS 用 `lossless=True`；有损用 `quality=95/90/80` |
| JPEG 参数 | `quality=95, subsampling=0`（与 `utils/pdf_extract._save_pil` 同口径） |
| 体积投影 | 逐图「变体字节 / 该页现状文件字节」的中位数 × 现状总量（避免抽样偏差） |

> 素材全部从 `~/Documents/guji/tasks/` **只读**取用，产物只写
> `tests/tmp/`。任务 0015 的 extract 页是高质量扫描（≈4.1 MB/页），
> 任务 0021 的 extract 页是较紧的 JPEG（≈0.97 MB/页），两者刚好覆盖
> 「重新编码有收益 / 无收益」两种极端。

## 2. 三端读写能力

| 能力 | 结论 | 证据 |
| --- | --- | --- |
| cv2 解码 WebP | 支持 | `utils.image_io.imread` 实测返回 `(H, W, 3)` |
| cv2 编码 WebP | 支持 | `imwrite` / `imencode(".webp")` 均成功 |
| Pillow 解码/编码 WebP | 支持 | `PIL.features.check("webp") == True` |
| Qt 解码 WebP（整幅） | 支持 | `QImageReader.canRead() == True`，像素与 PIL 一致 |
| Qt 缩放解码 WebP | 能出图，但**不省内存/时间** | `setScaledSize` 仍先整幅解码（见第 6 节） |
| Qt 编码 WebP | 支持 | `QImageWriter.supportedImageFormats()` 含 `webp` |
| **WebP2 编解码** | **不支持** | cv2 `imencode(".webp2")` 无 encoder；Qt 读写格式表无 `webp2`；无 `webp2`/`libwebp2` 模块 |
| AVIF 编解码 | 仅 Pillow 支持 | Pillow `features.check("avif") == True`，但 cv2/Qt 均不支持 |
| 输入图片收集 | 已含 webp | `utils/file_utils.IMAGE_EXTS`、`desktop/modules/extract/page.py` |
| CLI/GUI 输出格式枚举 | **不含 webp** | `OUTPUT_IMAGE_EXTS = ("jpg", "png", "tiff")` |

> ⚠️ 本报告测的是**标准 WebP（libwebp，VP8 有损 / VP8L 无损）**，不是
> **WebP2**。WebP2 的官方 README 明确写着 “WebP 2 will not be released as
> an image format but is used as a playground for image compression
> experiments”（[libwebp2](https://chromium.googlesource.com/codecs/libwebp2/)）：
> 它只有实验仓库、没有标准化发布，OpenCV/Pillow/Qt 也都没有集成，本机三端
> 无法读写。README 同时给出它的有损编码比 WebP 慢约 5 倍、解码慢约 3 倍
> （2020-11 口径），与本项目“提速/省盘”的目标相悖。因此**本项目不可用**。
> AVIF 只有 Pillow 支持，同样过不了 Qt 渲染这一关。

## 3. 编码体积与耗时

### 3.1 提取页（任务 0015，3506×5089，4 张抽样）

| 变体 | KB/页 | 编码 ms | 解码 ms | PSNR dB | SSIM |
| --- | ---: | ---: | ---: | ---: | ---: |
| **jpeg_q95（现状口径）** | **4165.7** | **110.2** | **167.3** | **60.5** | 1.000 |
| jpeg_q90 | 3112.6 | 101.8 | 161.4 | 44.9 | 1.000 |
| webp_q95（PIL） | 2529.8 | 2975.6 | 385.5 | 45.8 | 1.000 |
| webp_q90（PIL） | 1802.9 | 2901.7 | 421.1 | 43.6 | 1.000 |
| webp_q80（PIL） | 1154.9 | 2689.9 | 390.5 | 40.1 | 1.000 |
| webp_q90（cv2） | 1802.9 | 1440.8 | 423.3 | 43.6 | 1.000 |
| webp_lossless | 8323.8 | 9611.2 | 430.6 | inf | 1.000 |
| png_l6（对照） | 13237.5 | 1357.1 | 334.2 | inf | 1.000 |

要点：

- **无损 WebP 比 JPEG q95 大一倍**（8.32 MB vs 4.17 MB），扫描页的噪声让
  无损压缩毫无优势；只考虑有损。
- webp q90 体积是 jpeg_q95 的 **0.43×**，但编码慢 **26 倍**（PIL）/
  **13 倍**（cv2）。
- 解码也慢：PIL 421 ms vs 167 ms（2.5 倍），cv2 423 ms vs 167 ms。

任务 0021（2400×2380）交叉验证：

| 变体 | KB/页 | 编码 ms | PSNR dB |
| --- | ---: | ---: | ---: |
| jpeg_q95 | 2050.1 | 40.5 | 51.5 |
| webp_q90（cv2） | 1092.5 | 623.4 | 41.9 |
| webp_q80（PIL） | 665.3 | 1059.3 | 37.6 |
| webp_lossless | 4431.0 | 3437.6 | inf |
| png_l6 | 7109.9 | 588.7 | inf |

⚠️ **关键差别**：任务 0021 磁盘上实际的 extract 页平均只有 **0.97 MB**
（源 JPEG 已经是较紧的质量），而 webp q90 重编码是 **1.09 MB**——**换格式
反而更大**。任务 0015 的源页是 4.1 MB（≈q95），webp q90 才有 0.43× 的
收益。**extract 换 WebP 的收益完全取决于上游 JPEG 的质量，不能作为默认**。

### 3.2 检测提交裁图（体积大头）

任务 0015（2400~2713 × 3316~4417，4 张抽样）：

| 变体 | KB/张 | 编码 ms | 解码 ms | PSNR dB | 二值化差异 % | 二值产物 KB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **png_compact（现状）** | **8583.5** | **892.8** | **202.0** | inf | 0.0 | 101.4 |
| webp_lossless | 5304.2 | 5361.7 | 250.0 | inf | 0.0 | 101.4 |
| webp_q95（PIL） | 1753.7 | 1771.6 | 245.4 | 45.6 | 0.0 | 101.1 |
| webp_q90（PIL） | 1188.4 | 1625.0 | 232.1 | 43.1 | 0.1 | 100.8 |
| webp_q80（PIL） | 716.3 | 1487.7 | 220.3 | 39.9 | 0.1 | 99.8 |
| webp_q90（cv2） | 1188.4 | 828.0 | 238.0 | 43.1 | 0.1 | 100.8 |
| jpeg_q95 | 2935.9 | 61.6 | 90.1 | 47.8 | 0.0 | 101.2 |
| png_l6（对照） | 8583.5 | 779.6 | 201.0 | inf | 0.0 | 101.4 |

任务 0021（1100×1520 左右，4 张抽样）：

| 变体 | KB/张 | 编码 ms | 二值化差异 % |
| --- | ---: | ---: | ---: |
| png_compact（现状） | 2635.3 | 191.3 | 0.0 |
| webp_q90（PIL） | 465.6 | 400.4 | 0.2 |
| webp_q80（PIL） | 286.9 | 358.2 | 0.3 |
| webp_q90（cv2） | 465.6 | 209.3 | 0.2 |
| jpeg_q95 | 913.5 | 14.2 | 0.1 |
| webp_lossless | 1660.6 | 1040.5 | 0.0 |

要点：

- 这是**唯一量级明显的收益**：PNG 是「无损中间态」，而裁图只是 rembg 的
  输入，根本不需要无损。webp q90 体积 **0.14×（0015）/ 0.19×（0021）**。
- **二值化几乎不变**：0.0%~0.2% 的像素差异落在文字边缘；去底色产物 PNG
  体积 101.4 → 100.8 KB（0015）、52.1 → 51.9 KB（0021），成品观感不受影响。
- **编码耗时**：PIL 慢（1625 ms vs 893 ms），但 **cv2 编码 828 ms 与现状
  PNG 893 ms 持平**；任务 0021 上 209 ms vs 191 ms（+9%），仍属同一量级。
- 若不想引入 WebP，**JPEG q95 也能省 66%（8.58 → 2.94 MB）且编码仅
  62 ms**；但体积仍是 WebP q90 的 2.5 倍，二值化差异与 WebP 同级。

### 3.2.1 备选对比：JPG q95 vs WebP q90（检测裁图）

| 指标 | 任务 0015 PNG（现状） | 0015 JPG q95 | 0015 WebP q90（cv2） |
| --- | ---: | ---: | ---: |
| 体积 KB/张 | 8583.5 | 2935.9（0.34×） | 1188.4（0.14×） |
| 编码 ms | 892.8 | **61.6（快 14.5×）** | 828.0 |
| 解码 ms（PIL） | 202.0 | **90.1** | 238.0 |
| PSNR dB | inf | **47.8** | 43.1 |
| 二值化差异 % | 0.0 | 0.0 | 0.1 |
| 去底色产物 KB | 101.4 | 101.2 | 100.8 |

| 指标 | 任务 0021 PNG（现状） | 0021 JPG q95 | 0021 WebP q90（cv2） |
| --- | ---: | ---: | ---: |
| 体积 KB/张 | 2635.3 | 913.5（0.35×） | 465.6（0.19×） |
| 编码 ms | 191.3 | **14.2（快 13.5×）** | 209.3 |
| 解码 ms（PIL） | 44.8 | **20.6** | 58.6 |
| PSNR dB | inf | **43.2** | 40.6 |
| 二值化差异 % | 0.0 | 0.1 | 0.2 |
| 去底色产物 KB | 52.1 | 52.2 | 51.9 |

**怎么选**：

- **优先速度 / 内存 / 改动面 → JPG q95**。编码比现状 PNG 快 14 倍、比
  WebP（cv2）快 13 倍；解码快 2.2~2.6 倍；Pillow 解码内存与 PNG 同级
  （WebP 约 2 倍）；PSNR 更高、二值化差异同级；而且 jpg 已经在所有后缀
  清单/编辑器/print 扫描/缩略图回落里，唯一要改的是「检测提交」的落盘
  编码与命名，改动面远小于 WebP。
- **优先极致省盘 → WebP q90（cv2）**。比 JPG q95 再小 2.5 倍：任务 0015
  的 detect 全量 125.0 MB（JPG）vs 51.3 MB（WebP）；任务 0021 为
  131.5 MB vs 69.9 MB。代价是编码慢 13 倍、需要第 8 节的 8 处后缀改造。
- **不要选 WebP2**：本机没有可用编解码器（见第 2 节），Qt 渲染和 rembg
  读取都会直接断链；即使将来支持，编码器通常比 WebP 更慢，收益主要是
  体积，不是速度。
- **注意有损的长期代价**：JPG q95 与 WebP q90 都是有损。检测裁图是
  rembg 的中间输入，正常流程不回写，风险低；但如果用户会在预览里编辑
  裁图并保存，每次保存都会重新编码（编辑器 JPEG 走 q95，WebP 需另加
  写回支持），反复编辑会逐渐累积损失。PNG 没有这个问题。

### 3.3 去底色产物（白底透明）

任务 0015（现状 1 位调色板 PNG，112.8 KB/张）：

| 变体 | KB/张 | 编码 ms | 解码 ms | alpha 逐位一致 | 白底合成 PSNR |
| --- | ---: | ---: | ---: | ---: | ---: |
| **现状 PNG** | **112.8** | **206.7** | **108.5** | 100% | inf |
| webp_lossless | 83.4 | 176.9 | 105.5 | 100% | inf |
| webp_q90 | 123.6 | 1014.6 | 149.6 | 100% | inf |
| webp_q80 | 122.3 | 967.6 | 146.9 | 100% | inf |
| png_rgba_l6（对照，非现状） | 210.0 | 206.7 | 108.5 | 100% | inf |

任务 0021：现状 52.1 KB → webp_lossless 41.9 KB → 有损 52.5~53.0 KB。

要点：

- 1 位调色板 PNG 已经把「稀疏黑白 + 透明」压到极致，**无损 WebP 只小
  26%**；有损 WebP 反而**更大**（二进制图像对 DCT/VP8 不友好）。
- 绝对量也小（0015 全量 1.2 MB、0021 全量 7.9 MB），省 26% 只有 0.3~1.6 MB。
- **不建议换**：收益可以忽略，却把 Pillow 解码内存翻倍（见第 6 节），还让
  下游失去「1 位调色板」这个稳定形态。

### 3.4 全量体积投影

| 阶段 | 任务 | 现状 | 推荐变体 | 投影后 | 相对现状 |
| --- | --- | ---: | --- | ---: | ---: |
| extract | 0015 | 674.4 MB | webp_q90（cv2） | 292.7 MB | 0.43× |
| extract | 0021 | 69.1 MB | webp_q90（cv2） | 80.3 MB | **1.16×（更大）** |
| detect | 0015 | 370.2 MB | webp_q90（cv2） | 51.3 MB | 0.14× |
| detect | 0021 | 377.0 MB | webp_q90（cv2） | 69.9 MB | 0.19× |
| rembg | 0015 | 1.2 MB | webp_lossless | 0.8 MB | 0.68× |
| rembg | 0021 | 7.9 MB | webp_lossless | 6.3 MB | 0.80× |

- **只改检测裁图**：任务 0021 总占用 454.0 → 146.9 MB（**−68%**）；
  任务 0015 总占用 1045.8 → 726.9 MB（−30%，因为 extract 占大头且不动）。
- 若连 extract 也换：任务 0015 可到 ≈345 MB（−67%），但任务 0021 反而
  变大，且提取耗时涨一个数量级。**不建议作为默认**。

## 4. 画质：PSNR、SSIM 与二值稳定性

- SSIM 在所有变体上都显示 1.000（保留两位小数）：扫描页是大面积同色底 +
  细笔画，全局 SSIM 对局部边缘损伤不敏感，**不能只看 SSIM**。
- 更有判据是「经生产同一条 `utils.rembg_page` 二值化后的像素差异」：
  - 检测裁图 webp q90：**0.1%（0015）/ 0.2%（0021）**；
  - webp q80：0.1%（0015）/ 0.3%（0021）；
  - jpeg q95：0.0%（0015）/ 0.1%（0021）。
- 二值化差异只落在笔画边缘，且最终透明 PNG 体积几乎不变（±1 KB）。
  检测裁图换 webp q90 **不会改变去底色成品的观感**。
- 有损 WebP 的 alpha 通道是**无损**的（alpha 逐位一致 100%）；只有 RGB
  会被有损压缩。rembg 产物是纯黑文字 + 透明底，RGB 误差只落在透明区，
  白底合成后的 PSNR 仍是 inf（逐像素一致）。

## 5. 页面渲染（Qt）

任务 0015，取每种格式的第一张（3506×5089）：

| 变体 | 整幅可读 | 整幅 PSNR | 整幅 ms | 256px 可读 | 缩放 ms |
| --- | --- | ---: | ---: | --- | ---: |
| jpeg_q95（现状） | True | 62.0 | 165.8 | True | 80.9 |
| webp_q90（PIL） | True | 44.9 | 182.0 | True | 186.8 |
| webp_lossless | True | inf | 224.8 | True | 213.2 |
| png_l6（对照） | True | inf | 289.9 | True | 299.4 |

- **渲染正确性没有疑问**：Qt 解出的整幅 PSNR 与 PIL 解码侧的 PSNR 完全
  一致（44.9 / inf / 62.0），说明 Qt 的 WebP 解码没有偏色或通道错位。
- 缩放解码（256px）也正确，但 **WebP 不做按需缩放**：187~213 ms，是 JPEG
  81 ms 的 2.3~2.6 倍。任务 0021 上同样是 66 ms vs 47 ms。
- 结论：单张预览可用；**批量缩略图（任务列表、查看器条目）会变慢**，
  如果 extract 改 WebP，影响面比检测裁图大得多。

## 6. 内存与 CPU

任务 0015，单页 3506×5089，每种组合独立子进程、连续解码 5 次：

| 变体 | 解码路径 | 峰值增量 MB | 峰值 MB | 中位耗时 ms |
| --- | --- | ---: | ---: | ---: |
| jpeg_q95（现状） | PIL 全量 | 136.9 | 168.4 | 115.7 |
| jpeg_q95（现状） | cv2 全量 | 113.3 | 144.8 | 87.6 |
| jpeg_q95（现状） | Qt 全量 | 80.0 | 111.6 | 157.0 |
| jpeg_q95（现状） | **Qt 缩放 256** | **14.2** | **45.7** | **45.3** |
| webp_q90（PIL） | PIL 全量 | 275.4 | 306.9 | 340.7 |
| webp_q90（PIL） | cv2 全量 | 111.1 | 142.6 | 186.5 |
| webp_q90（PIL） | Qt 全量 | 82.1 | 113.6 | 195.0 |
| webp_q90（PIL） | **Qt 缩放 256** | **83.8** | **115.1** | **183.9** |
| webp_lossless | PIL 全量 | 279.9 | 311.5 | 397.8 |
| webp_lossless | cv2 全量 | 133.6 | 165.1 | 196.7 |
| webp_lossless | Qt 全量 | 155.4 | 186.9 | 205.8 |
| webp_lossless | Qt 缩放 256 | 156.6 | 188.2 | 213.9 |
| png_l6（对照） | PIL 全量 | 137.1 | 168.5 | 287.5 |
| png_l6（对照） | cv2 全量 | 120.8 | 152.3 | 257.8 |
| png_l6（对照） | Qt 全量 | 80.0 | 111.6 | 288.8 |
| png_l6（对照） | Qt 缩放 256 | 81.3 | 112.9 | 302.2 |

结论：

- **Pillow 解 WebP 内存约 2 倍**（275 MB vs 137 MB）：rembg / print 都走
  Pillow 读图，检测裁图换 WebP 后这两步的单张峰值会上升；裁图只有
  2400×3400 左右，绝对增量约 30~60 MB/张，可接受。
- **cv2 解 WebP 内存与 JPEG 持平**（111 vs 113 MB），detect 走
  `utils.image_io.imread`，不受影响；代价是解码慢约 2 倍（187 vs 88 ms）。
- **Qt 缩放解码是最大风险**：WebP 83.8 MB vs JPEG 14.2 MB（5.9×），
  无损 WebP 156.6 MB（11×）。任务列表/缩略图 worker 用
  `QImageReader.setScaledSize`，若源图是 WebP，每个 worker 会多占几十到
  上百 MB，并行时很容易把内存打满。
- **CPU**：编码是最贵的一步。PIL WebP 编码约为 JPEG 的 20~30 倍、PNG 的
  **约 2 倍**；**cv2 编码约为 PIL 的 1/2**。检测裁图必须用 cv2 才能保持
  现状耗时。

## 7. 真实提取链路与检测一致性

### 7.1 `extract_single_page(ext="webp")`

任务 0015，真实 PDF 3 页：

| 页 | jpg KB | jpg ms | webp KB | webp ms | PIL | cv2 | Qt | Qt 缩放 | webp↔jpg PSNR | webp q90 KB |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- | ---: | ---: |
| 1 | 3984.8 | 771.2 | 996.1 | 3680.5 | True | True | True | True | 41.4 | 1651.1 |
| 57 | 4064.7 | 663.6 | 1096.3 | 3122.4 | True | True | True | True | 40.2 | 1729.4 |
| 113 | 4159.2 | 646.8 | 1157.7 | 3093.4 | True | True | True | True | 39.7 | 1800.8 |

- `jpg` 是 quick 直拷（PDF 内嵌 JPEG 原字节），`webp` 是解码后
  `Image.save(..., "WEBP")`——**PIL 默认 quality=80**，不是 q90。这是当前
  代码的隐藏行为（见第 8 节），体积 1.0~1.16 MB 是 q80 的结果；q90 约
  1.65~1.80 MB。
- 三端读取全部成功，页面渲染正确；但单页耗时从 0.65~0.77 s 涨到
  3.1~3.7 s（含 PDF 打开，编码本身占大头）。任务 0021 因为源 JPEG 小、
  直拷更快，单页从 18 ms 涨到 745 ms（约 40 倍）。

### 7.2 YOLO 检测框一致性

同一页用三种编码喂给真实 YOLO（`bookcontent.pt`）：

| 页 | jpg_q95 框 | webp_q90 框 | webp 无损框 | q90 vs 无损最大差 | jpg vs 无损最大差 |
| --- | --- | --- | --- | ---: | ---: |
| 1 | 267,370,2979,4787 | 266,366,2979,4747 | 266,367,2976,4737 | 10 px | **50 px** |
| 57 | 149,1077,2610,4506 | 149,1077,2610,4506 | 149,1077,2610,4506 | 0 px | 0 px |
| 113 | 164,1095,2580,4500 | 165,1095,2580,4499 | 164,1095,2581,4499 | 1 px | 1 px |

- 检测框**不是跨编码逐位稳定的**：jpg_q95 与「无损源」在第 1 页差了 50 px，
  而 webp_q90 只差 10 px。也就是说 **webp q90 并不比当前 JPEG q95 更差**，
  反而更接近源像素。
- 因此不能把「webp 的框与 jpg 的框不完全相同」当作回归；真正的判据是
  「与无损源的偏差在可接受范围」，实测为 0~10 px（页面尺寸 3506×5089，
  ≈0.3%）。
- 检测耗时：cv2 解 webp 比 jpg 多 90~110 ms/页，推理本身 50~330 ms。

## 8. 代码改造面（不改会怎样）

现在直接把产物后缀改成 `.webp`，以下位置会**静默漏图/写坏文件**：

| 位置 | 现状 | 后果 |
| --- | --- | --- |
| [core/command_spec.py](../../core/command_spec.py#L59) | `OUTPUT_IMAGE_EXTS = ("jpg","png","tiff")` | CLI/GUI 无法选择 webp；`CommandArgs.validate()` 拒绝 |
| [utils/pdf_extract.py](../../utils/pdf_extract.py#L247-L256) | webp 落 `Image.save(path, ext.upper())`，**默认 q80、无参数** | 实际切换后画质/体积不可控（第 7.1 节就是 q80 的结果） |
| [utils/pdf_extract.py](../../utils/pdf_extract.py#L393-L404) | quick 直拷只认 jpg/jpeg/png | ext=webp 永远无法直拷，必须整页解码重编码 |
| [functions/print.py](../../functions/print.py#L225) | 目录兜底扫描只认 png/jpg/jpeg/bmp/gif | 第四步按目录取图时**漏掉全部 webp 页**，PDF 少页 |
| [pdf_render_service.py](../../desktop/workers/pdf_render_service.py#L295-L305) | `_thumb_from_page_image` 只找 `.jpg/.jpeg/.png` | 缩略图回落失效（实测返回 0 字节），只能退回 PDF 渲染 |
| [files.py](../../desktop/utils/files.py#L16) + [pages.py](../../desktop/store/pages.py#L71) | `IMAGE_SUFFIXES` 不含 webp | 任务页清单/阶段图像列表**看不到 webp**，界面显示 0 页 |
| [io.py](../../desktop/components/viewers/image_zoom_dialog/io.py#L38-L44) + [consts.py](../../desktop/components/viewers/image_zoom_dialog/consts.py#L45-L48) | 覆盖写回只认 jpg/png/bmp/tiff | 编辑器对 `.webp` 目标会按 PNG 写内容（文件损坏） |
| [imposition.py](../../desktop/services/imposition.py#L52-L54) | 成品后缀集合只有 png/jpg/jpeg | 若拼版改成 webp 成品，清理旧成品时漏掉 webp，换格式后旧页会残留；当前 rembg 仍出 PNG，暂不受影响 |

已确认**不用改**的入口：`utils/file_utils.IMAGE_EXTS`（含 webp）、
`desktop/modules/extract/page.py` 的 `_IMAGE_EXTS`（含 webp）、
`desktop/steps/spec.py` 的文件对话框过滤（含 webp）、`utils.image_io`
（cv2 可读写 webp）。

## 9. 建议

按「收益 / 风险 / 改动面」排序：

1. **「检测提交」裁图换格式是唯一明确划算的改动**，两个选项按优先级选：
   - **已落地：JPG q95（低风险、最快）**。省 66%，编码 62 ms（比现状
     PNG 快 14.5×、比 WebP 快 13×），解码快 2.2~2.6×，二值化差异
     0.0~0.1%，且 jpg 已经在全部后缀清单/编辑器/print 扫描/缩略图里；
     只需改检测提交的落盘编码与命名，并清理旧的 `.png`（避免同页两个
     后缀并存被当成两页）。
   - **磁盘优先选 WebP q90（cv2 编码）**：体积 0.14~0.19×（比 JPG 再小
     2.5×），编码耗时与现状 PNG 持平；二值化差异 0.1~0.2%，成品 PNG 体积
     几乎不变；需要同步改第 8 节的 8 处后缀清单，且 Qt 对 webp 的缩放
     解码内存/耗时更高。
2. **extract 保持 JPG，不纳入默认切换**。
   - 直拷快通道是现有提取速度的基础，WebP 会把它变成「每页解码 + 重编码」；
   - 源 JPEG 已经较紧的书（任务 0021）换 webp 会**变大**；
   - 若确实要给「高码率扫描件」提供省空间选项，建议做成**显式可选**：
     `ext=q90-webp` + cv2 编码 + 明确提示「编码本身 1.4 s/页、提取会慢
     一个数量级」，不要改默认值。
3. **rembg 保持 PNG**。无损 WebP 只小 26%，绝对量小，还会让 Pillow 解码
   内存翻倍、Qt 缩放缩略图内存涨 11 倍，不值得。
4. **不要用 WebP 无损替代 PNG**：扫描页噪声大，无损 WebP 比 JPEG 大一倍，
   检测裁图无损 WebP 也只到 PNG 的 0.62×，且编码 5~10 秒/张。
5. **Qt 侧要提前评估缩略图**：只要产物可能是 webp，`QImageReader` 的缩放
   解码就不再省内存。若将来 extract 支持 webp，建议任务列表缩略图在提取
   阶段顺手生成（现有 rembg 阶段已有 256px JPEG 缩略图的做法），不要依赖
   Qt 对 webp 的缩放解码。

## 10. 复现方式

```bash
# 全量（编码矩阵 + Qt 渲染 + 内存 + 真实提取链路 + YOLO）
C:\Users\liuzu\anaconda3\envs\py310\python.exe tests\probe_webp_benchmark.py

# 只跑编码/渲染（快）
C:\Users\liuzu\anaconda3\envs\py310\python.exe tests\probe_webp_benchmark.py \
    --samples 4 --skip-memory --skip-yolo --skip-integration

# 指定另一份素材
C:\Users\liuzu\anaconda3\envs\py310\python.exe tests\probe_webp_benchmark.py \
    --task C:\Users\liuzu\Documents\guji\tasks\0021 --samples 4
```

产物落 `tests/tmp/webp_probe_*/`（`results.json` 是原始数据）；探针**只读**
用户任务目录，不写回。
