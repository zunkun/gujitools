# Linux 包体积分析：为什么 500 MB 而 Windows 只有 200 MB+

> 2026-11-27 Debian 13 实测。本文记录分析过程与数据，供后续决定是否优化推理引擎时参考。
> **当前结论：已用 CPU 版 torch，包内无 CUDA 库；剩余体积基本是不可避免的硬成本，
> 低风险优化最多省 20%，要质变必须动推理引擎。**

## 1. 现象与结论摘要

同一版本 `2.1.5`、同样 CPU 版 PyTorch：

| 产物 | 体积 | 压缩方式 |
| --- | --- | --- |
| Windows 安装包（Inno Setup） | 约 200 MB+ | `lzma2` + `SolidCompression=yes` |
| Linux tar.gz / deb | 各约 498 MB | gzip level 6，逐文件流式压缩 |

**不是 CUDA 版 torch 导致的**：`dpkg-deb --contents` 中查不到任何 `nvidia/cudnn/cublas/cufft/libcudart/nccl`
的 `.so`；PyInstaller 日志显示 `inferred hidden imports for CUDA libraries: []`。
`build.py::_assert_cpu_torch()` 已加硬校验（`GUJI_ALLOW_CUDA_TORCH=1` 可显式放行）。

## 2. 体积拆解

`dist/guji/` 未压缩 **1624.5 MB / 2756 个文件**（`tools/check_bloat.py` 输出）。
下表为逐文件 `gzip.compress(level=6)` 估算的压缩后贡献，与实际 tar.gz 总量吻合：

| 目录 | 原始 | 压缩后 |
| --- | ---: | ---: |
| `torch/` | 591 MB | 164 MB |
| `_guji_vendor/`（PySide6 拆分包） | 93 MB | 37 MB |
| `cv2/` | 78 MB | 30 MB |
| `opencv_python_headless.libs/` | 93 MB | 30 MB |
| `pymupdf/`（含 `libmupdf.so` 34 MB） | 87 MB | 43 MB |
| `static/`（模型权重 + 手册） | 22 MB | 20 MB |
| `scipy/` + `scipy.libs/` | 82 MB | 26 MB |
| `numpy/` + `numpy.libs/` | 41 MB | 15 MB |
| `pandas/` + `matplotlib/` | 35 MB | 14 MB |
| 其他（Python 运行时、Qt 库等） | — | 余量 |

## 3. 为什么 Linux 比 Windows 大

### 3.1 压缩方式不对等（次要因素）

Windows 安装包用 Inno Setup 的 **lzma2 固实压缩**：把整个约 650 MB 的目录当
**一个数据流**压缩，跨文件共享字典。Linux 的 tar.gz 用 gzip level 6，
逐文件流式压缩、无跨文件字典。内容相同的情况下后者天然大 10~20%。

### 3.2 Linux 的 torch 二进制本身就大 43%（主要因素）

两个平台安装的是**同一版本** `torch 2.14.1+cpu`（CPU 源最新），但官方 wheel 体积差异明显：

| 项目 | Windows | Linux |
| --- | ---: | ---: |
| CPU wheel（cp310） | 118 MB | 187 MB |
| 解压后核心库 | `torch_cpu.dll` ~292 MB | `libtorch_cpu.so` 418 MB |

这是 PyTorch 官方 wheel 的平台差异，不是打包配置问题。`libtorch_cpu.so` 是
`not stripped`（含完整 `.symtab`），`strip --strip-all` 可降到 332 MB，
但 gzip 后只省约 8 MB（符号表压缩率本来就高）。

> **实测验证**：临时把 `libtorch_cpu.so` 换成 strip 后的版本，`import torch`、
> 矩阵乘法、`import torchvision` 均正常。该操作安全，但收益有限。

### 3.3 Linux 瘦身漏掉了 torch 的测试/构建工具（可修复）

`prune_bloat()` 的 Windows 分支会删 `protoc.exe`、ffmpeg dll、软件 OpenGL 回退等；
Linux 分支没有对应清理，导致打包产物里仍有：

| 位置 | 原始 | 压缩后 | 内容 |
| --- | ---: | ---: | --- |
| `torch/test/` | 85 MB | 28 MB | 112 个 C++ 单元测试二进制 |
| `torch/bin/` | 51 MB | 16 MB | `test_api`、`test_jit`、`protoc` 等 40 个构建工具 |

合计 **136 MB 原始 / 44 MB 压缩后**，运行时完全用不到。

### 3.4 版本错配：项目根本不用 torchaudio

`grep torchaudio` 只命中 `build.py` 和 `docs/dev/build.md`，项目代码无任何引用，
但 `build.py` 一直把它塞进构建环境。CPU 源上 torchaudio 已停更在 **2.11.1**，
而 torch 是 **2.14.1**——版本对不上。去掉它不影响功能。

## 4. 哪些不能砍

| 内容 | 原因 |
| --- | --- |
| `torch` 的 Python 子模块（`_dynamo`、`_inductor`、`distributed`、`onnx`…） | `import torch` 时顶层就会引用；实测加进 `excludes` 会让 `guji crop` 直接 `ModuleNotFoundError`。详见 `tools/probe_excludes.py`。 |
| OpenCV 的视频/编解码 `.so` | `ldd cv2.abi3.so` 显示 `libavcodec`、`libavformat`、`libavutil`、`libswscale`、`libopenblas`、`libaom`、`libgfortran` 全是 **DT_NEEDED 硬依赖**，删了 `import cv2` 直接失败。与 Windows 可删的 `opencv_videoio_ffmpeg500_64.dll`（可选插件）性质不同。 |
| `libmupdf.so` | PDF 渲染核心，项目主功能。 |
| PySide6/Qt | 桌面端必需。 |

**OpenCV headless 已经是最轻的官方发行版**：它去掉的是 Qt/GTK 图形依赖，
项目只用 `imread/imwrite/cvtColor/boxFilter` 等图像 API，选型正确，无额外空间。

## 5. 优化收益评估

| 措施 | 收益 | 风险 | 状态 |
| --- | ---: | --- | --- |
| 删 `torch/test` + `torch/bin` | −44 MB | 低 | 未实施 |
| 去掉 `torchaudio` | 少量 | 低 | 未实施 |
| `strip --strip-all` 处理 `.so` | −8 MB | 已验证安全 | 未实施 |
| tar.gz / deb 改用 xz（类 lzma2） | −30~50 MB | 低，仅影响解压速度 | 未实施 |
| **合计** | **498 → 约 400 MB（−20%）** | | |

### 理论下限

不可压缩的核心成本约 **317 MB**（压缩后）：

- torch 核心（去掉 test/bin）约 120 MB
- OpenCV 约 61 MB
- MuPDF 约 43 MB
- PySide6/Qt 约 37 MB
- numpy/scipy/pandas 约 56 MB

加上模型权重、手册、Python 运行时等，理论下限在 **350~400 MB**。
所以上面那 20% 已经接近“不动架构就能拿到的全部收益”。

### 要降到 200 MB 级别只有两条路

1. **换推理引擎**：YOLO 从 PyTorch 迁到 ONNX Runtime（约 30 MB）或 OpenCV DNN，
   能整个砍掉 torch。代价：重做模型导出、验证检测精度一致性，等同动核心算法。
2. **算子级裁剪 / 重新编译 PyTorch**：只保留 YOLO 前向路径所需算子。
   代价：定制编译，每次版本升级都要重来。

两者都是产品/架构决策，不是打包参数能解决的。当前建议：**接受 498 MB**；
上述低风险优化可顺手做，但不要预期质变。

## 6. 复现命令

```bash
# 未压缩体积与文件数
python tools/check_bloat.py dist/guji

# 各目录原始体积
du -sh dist/guji/_internal/* | sort -hr | head -25

# 大文件 TOP
find dist/guji/_internal -type f -printf '%s %p\n' | sort -rn | head -30

# CUDA 库检查（应为空）
dpkg-deb --contents dist/gujitools_2.1.5_amd64.deb | grep -Ei 'nvidia|cudnn|cublas|cufft|libcudart'

# 两平台 wheel 体积
curl -sIL 'https://download-r2.pytorch.org/whl/cpu/torch-2.14.1%2Bcpu-cp310-cp310-win_amd64.whl' | grep -i content-length
curl -sIL 'https://download-r2.pytorch.org/whl/cpu/torch-2.14.1%2Bcpu-cp310-cp310-manylinux_2_28_x86_64.whl' | grep -i content-length

# headless 版硬依赖确认
ldd dist/guji/_internal/cv2/cv2.abi3.so | grep -iE 'avcodec|avformat|openblas|aom'
```
