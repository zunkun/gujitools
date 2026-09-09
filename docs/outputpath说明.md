# 输出路径（Output Path）说明文档

本文档详细介绍 `gujitools` 各命令的输出目录计算规则，帮助用户理解命令参数 `-o/--output` 的行为，并为开发者提供维护参考。

## 1. 通用路径工具函数

所有命令的路径计算均依赖 `utils/path_utils.py` 中定义的两个核心函数：

- **`resolve_final_output_dir(input_path, output_arg, is_file, default_subdir)`**  
  用于 `crop`、`rembg`、`cropremove` 等**单级输出**命令，返回最终输出目录（已包含默认子目录）。

- **`get_extract_output_root(input_path, output_arg, is_file)`**  
  专用于 `extract` 命令，返回**输出根目录**（不包含 PDF 子目录和图片子目录），后续由 `run_on_input_directory` 根据 PDF 文件名和 `subdir_name` 补全完整路径。

这两个函数均从 `utils` 包导出，使用时可通过 `from utils import resolve_final_output_dir, get_extract_output_root` 导入。

---

## 2. `extract` 命令

### 2.1 路径构成

```
<根目录> / <PDF文件名(无后缀)> / <图片子目录名> / 页码.扩展名
```

其中：

- **根目录**：由 `get_extract_output_root` 计算。
- **图片子目录名**：默认为 `images`（由 `ExtractFunction.default_temp_name` 控制），可通过修改类属性调整，或通过 `run_on_input_directory` 的 `subdir_name` 参数覆盖。

### 2.2 根目录计算规则

| 情况           | `--output` 参数               | 根目录                   |
| -------------- | ----------------------------- | ------------------------ |
| 输入为**文件** | 未指定                        | `文件所在父目录`         |
| 输入为**文件** | 简单名称（如 `out`）          | `文件所在父目录/out`     |
| 输入为**文件** | 绝对/相对路径（如 `D:\data`） | 解析后的路径（绝对路径） |
| 输入为**目录** | 未指定                        | `输入目录本身`           |
| 输入为**目录** | 简单名称（如 `out`）          | `输入目录/out`           |
| 输入为**目录** | 绝对/相对路径（如 `D:\data`） | 解析后的路径（绝对路径） |

> 注意：`get_extract_output_root` 对于**文件输入**且未指定 `-o` 时，根目录为文件所在父目录；对于**目录输入**且未指定 `-o` 时，根目录即为输入目录本身。

### 2.3 示例

```bash
# 输入为单个 PDF，未指定 -o
python main.py extract -i /path/to/file.pdf
# 输出: /path/to/file_stem/images/1.jpg ...

# 输入为单个 PDF，指定 -o preview
python main.py extract -i /path/to/file.pdf -o preview
# 输出: /path/to/preview/file_stem/images/1.jpg ...

# 输入为目录，未指定 -o
python main.py extract -i /path/to/pdfs/
# 输出: /path/to/pdfs/pdf1_stem/images/..., /path/to/pdfs/pdf2_stem/images/...

# 输入为目录，指定 -o myoutput
python main.py extract -i /path/to/pdfs/ -o myoutput
# 输出: /path/to/pdfs/myoutput/pdf1_stem/images/...
```

---

## 3. `crop`、`rembg`、`cropremove` 命令

这三个命令采用统一的路径计算方式，由 `resolve_final_output_dir` 实现。其核心规则是：

**最终输出目录 = 根目录 + `/` + `default_subdir`**

其中：

- **`default_subdir`**：由各命令类属性 `default_temp_name` 控制，分别为 `crop`、`rembg`、`rembg`（cropremove 复用 rembg）。
- **根目录**：根据 `--output` 参数计算。

### 3.1 根目录计算规则（`resolve_final_output_dir` 逻辑）

| 情况     | `--output` 参数               | 根目录                   |
| -------- | ----------------------------- | ------------------------ |
| 任意输入 | 未指定                        | `输入路径的父目录`       |
| 任意输入 | 简单名称（如 `out`）          | `输入路径的父目录/out`   |
| 任意输入 | 绝对/相对路径（如 `D:\data`） | 解析后的路径（绝对路径） |

> 关键点：**无论输入是文件还是目录，未指定 `-o` 时根目录均为输入路径的父目录**，这意味着对于目录输入，输出目录与输入目录**并列**（而非在输入目录内部），这符合多数用户预期。

### 3.2 各命令的最终输出目录

| 命令         | `default_temp_name` | 最终输出目录     |
| ------------ | ------------------- | ---------------- |
| `crop`       | `crop`              | `<根目录>/crop`  |
| `rembg`      | `rembg`             | `<根目录>/rembg` |
| `cropremove` | `rembg`             | `<根目录>/rembg` |

### 3.3 示例

```bash
# 输入为目录，未指定 -o
python main.py crop -i /path/to/images/
# 输出: /path/to/crop/          （与 images 目录并列）

# 输入为目录，指定 -o out
python main.py crop -i /path/to/images/ -o out
# 输出: /path/to/out/crop/      （out 与 images 并列，其下再建 crop）

# 输入为文件，指定 -o out
python main.py crop -i /path/to/file.jpg -o out
# 输出: /path/to/out/crop/      （file.jpg 所在目录下的 out/crop）

# 输入为目录，指定绝对路径
python main.py rembg -i /path/to/images/ -o D:\output
# 输出: D:\output/rembg/
```

---

## 4. 模块实现位置

| 功能类               | 文件路径                   | 使用的工具函数                                                        | 默认子目录名 |
| -------------------- | -------------------------- | --------------------------------------------------------------------- | ------------ |
| `ExtractFunction`    | `functions/extract.py`     | `get_extract_output_root` + `run_on_input_directory` 的 `subdir_name` | `images`     |
| `CropFunction`       | `functions/crop.py`        | `resolve_final_output_dir`                                            | `crop`       |
| `RembgFunction`      | `functions/rembg.py`       | `resolve_final_output_dir`                                            | `rembg`      |
| `CropRemoveFunction` | `functions/crop_remove.py` | `resolve_final_output_dir`                                            | `rembg`      |

---

## 5. 开发者注意事项

- **扩展新命令**：若新增命令需要类似的路径逻辑，建议直接调用 `resolve_final_output_dir` 或 `get_extract_output_root`，避免重复实现。
- **自定义子目录名**：对于使用 `resolve_final_output_dir` 的命令，只需设置类属性 `default_temp_name` 即可。
- **`extract` 的特殊性**：由于需要为每个 PDF 创建独立目录，其路径结构较复杂，务必通过 `run_on_input_directory` 的 `subdir_name` 传递子目录名，不要硬编码。
- **测试**：确保覆盖文件/目录输入、有无 `-o`、简单名称/路径等场景，路径解析结果与文档一致。

---

## 6. 历史变更

- **v2.0**：统一 `crop`/`rembg`/`cropremove` 路径规则，引入 `resolve_final_output_dir`，使目录输入时输出与输入并列。
- **v1.x**：旧版 `rembg` 在目录输入且未指定 `-o` 时，输出在输入目录内部（`input/rembg`），现已修正。

---

本说明文档随代码同步更新，如有疑问请查阅 `utils/path_utils.py` 中的详细注释。
