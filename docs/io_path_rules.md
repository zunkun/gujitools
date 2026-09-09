# Input & Output 路径规则（供大模型开发使用）

## 一、通用前置说明

1. **工具入口**：`guji` 多命令行工具，包含 `extract`、`crop`、`rembg`、`cropremove` 四个命令。
2. **路径统一标准**：所有路径内部使用 `pathlib.Path`，自动执行 `.expanduser()` 解析 `~` 用户目录符号、`.resolve()` 转为绝对路径；禁止混用 `os.path` 原生接口做判断。
3. **分层职责划分**
   - CLI层：仅解析原始字符串参数，`input` 自动转为标准化 `Path` 对象，`output` 保留原始字符串（区分纯名称/完整路径）。
   - `CommandArgs`：纯参数容器，仅存储原始入参，可保留 `build_args` 做参数聚合，**不做文件校验、不计算输出路径、不创建文件夹**。
   - `FunctionBase`（基类）：统一解析 `input`，生成公共字段 `parent_path`、`is_file`、`input`，提供通用输出路径解析工具。
   - 各命令子类：实现命令专属校验、专属输出规则、最终目录创建。
4. **路径工具函数**：所有命令使用 `utils/path_utils.py` 中定义的 `resolve_final_output_dir` 和 `get_extract_output_root` 函数，确保规则统一。

---

## 二、Input 统一规则（全局通用）

### 1. 参数定义

- 命令行参数：`-i / --input`
- 默认值：`.`（当前目录）
- 支持输入类型：**单个文件 / 文件夹目录**

### 2. 公共字段自动计算（FunctionBase 统一生成）

输入标准化后得到 `self.input: Path`

1. `self.is_file: bool`
   - `True`：输入是独立文件（如 `xxx.pdf`、`xxx.jpg`）
   - `False`：输入是文件夹目录
2. `self.parent_path: Path`（待处理文件/目录的根父目录）
   - 若 `self.is_file = True`：`parent_path = self.input.parent`（文件所在文件夹）
   - 若 `self.is_file = False`：`parent_path = self.input`（输入目录本身）

### 3. 命令专属输入限制

- `extract`：强制要求 `input` 为 **PDF 文件或包含 PDF 的目录**；若输入为单个文件，则必须为 PDF；若输入为目录，则遍历目录下所有 `.pdf` 文件。
- `crop`、`rembg`、`cropremove`：支持输入为图片文件或目录（目录下可包含多种图片格式），无强制文件类型限制。

---

## 三、Output 通用基础规则（所有命令共用）

1. 命令行参数：`-o / --output`，可选传参，不传为 `None`，原始值存储为字符串 `self.output_raw`。
2. 最终输出字段：`self.outpath: Path`，是程序最终需要创建的业务目录，所有文件输出到此目录。
3. **所有命令的最终输出目录均包含一个固定的默认子目录名**，该名称由各命令类的 `default_temp_name` 类属性控制：
   - `extract`：`images`（不可覆盖）
   - `crop`：`crop`
   - `rembg`：`rembg`
   - `cropremove`：`rembg`（复用 rembg 的默认子目录名）
4. `-o` 参数的含义：**指定输出根目录**，实际最终目录会在根目录下追加默认子目录（`extract` 略有不同，详见分命令说明）。
5. `output` 输入分两类：
   - **纯名称字符串**：无 `/ \` 路径分隔符，如 `out`。输出根目录 = `输入路径的父目录 / 名称`（`extract` 对目录输入有特殊处理，见下文）。
   - **完整路径字符串**：包含路径分隔符，如 `D:/data` 或 `/home/user/out`。输出根目录 = 解析后的绝对路径（相对路径基于当前工作目录解析）。

---

## 四、分命令 Output 细分规则

### 1. extract（PDF提取图片）

**输出结构**：`<根目录>/<PDF文件名(无后缀)>/<图片子目录名>/页码.扩展名`

- **图片子目录名**：固定为 `images`（由 `ExtractFunction.default_temp_name = "images"` 控制）。
- **根目录计算**：调用 `get_extract_output_root(input_path, output_arg, is_file)`。

**规则**：

- 未传 `-o`（`output_raw = None`）：
  - 若输入为**文件**（`is_file=True`）：根目录 = `input.parent`（文件所在父目录）。
  - 若输入为**目录**（`is_file=False`）：根目录 = `input`（输入目录本身）。
- 传纯名称（如 `-o out`）：
  - 若输入为文件：根目录 = `input.parent / out`。
  - 若输入为目录：根目录 = `input / out`。
- 传完整路径（如 `-o /abs/path` 或 `-o D:\data`）：根目录 = 解析后的绝对路径（相对路径基于 CWD 解析）。

**示例**（假设输入文件为 `/a/b.pdf`，输入目录为 `/a/` 且内含 `b.pdf`、`c.pdf`）：

| 命令                              | 输出目录                                                  |
| --------------------------------- | --------------------------------------------------------- |
| `extract -i /a/b.pdf`             | `/a/b_stem/images/1.jpg ...`                              |
| `extract -i /a/b.pdf -o out`      | `/a/out/b_stem/images/1.jpg ...`                          |
| `extract -i /a/b.pdf -o /abs/out` | `/abs/out/b_stem/images/1.jpg ...`                        |
| `extract -i /a/`                  | `/a/b_stem/images/... , /a/c_stem/images/...`             |
| `extract -i /a/ -o out`           | `/a/out/b_stem/images/... , /a/out/c_stem/images/...`     |
| `extract -i /a/ -o /abs/out`      | `/abs/out/b_stem/images/... , /abs/out/c_stem/images/...` |

---

### 2. crop（裁剪功能）

**输出结构**：`<根目录>/crop/图片文件`

- **默认子目录名**：`crop`（`CropFunction.default_temp_name = "crop"`）。
- **根目录计算**：调用 `resolve_final_output_dir(input_path, output_arg, is_file, default_subdir="crop")`。

**规则**（`resolve_final_output_dir` 逻辑）：

- 未传 `-o`：根目录 = `input.parent`（输入路径的父目录）。
- 传纯名称（如 `-o out`）：根目录 = `input.parent / out`。
- 传完整路径（如 `-o /abs/path`）：根目录 = 解析后的绝对路径。

**最终输出目录** = 根目录 / `crop`

**示例**（输入为 `/a/images/` 目录，内含图片；或输入为 `/a/photo.jpg` 文件）：

| 命令                             | 输出目录                          |
| -------------------------------- | --------------------------------- |
| `crop -i /a/images/`             | `/a/crop/`（与 images 并列）      |
| `crop -i /a/images/ -o out`      | `/a/out/crop/`                    |
| `crop -i /a/images/ -o /abs/out` | `/abs/out/crop/`                  |
| `crop -i /a/photo.jpg`           | `/a/crop/`（与 photo.jpg 同目录） |
| `crop -i /a/photo.jpg -o out`    | `/a/out/crop/`                    |

---

### 3. rembg（去底色功能）

**输出结构**：`<根目录>/rembg/图片文件`

- **默认子目录名**：`rembg`（`RembgFunction.default_temp_name = "rembg"`）。
- **根目录计算**：调用 `resolve_final_output_dir(input_path, output_arg, is_file, default_subdir="rembg")`。

**规则**：与 `crop` 完全一致，仅默认子目录名不同。

**示例**（输入为 `/a/images/` 目录）：

| 命令                              | 输出目录          |
| --------------------------------- | ----------------- |
| `rembg -i /a/images/`             | `/a/rembg/`       |
| `rembg -i /a/images/ -o out`      | `/a/out/rembg/`   |
| `rembg -i /a/images/ -o /abs/out` | `/abs/out/rembg/` |

---

### 4. cropremove（裁剪 + 去底色复合流程）

**输出结构**：`<根目录>/rembg/图片文件`

- **默认子目录名**：`rembg`（`CropRemoveFunction.default_temp_name = "rembg"`）。
- **根目录计算**：与 `crop`、`rembg` 相同，调用 `resolve_final_output_dir`，`default_subdir="rembg"`。

**规则**：与 `rembg` 输出结构相同，但处理流程为裁剪后去底色。

---

## 五、执行时序约束（关键，避免报错）

1. **`CommandArgs` 参数容器阶段**：**禁止任何文件存在性校验、禁止计算 `outpath`、禁止调用 `mkdir` 创建目录**。
2. 文件校验、输出路径计算、目录创建全部下沉至 `FunctionBase` 子类 `__init__` 或 `execute`。
3. 目录创建时机：仅在 `execute()` 业务执行函数内调用 `make_out_dir()` 创建 `self.outpath`，初始化阶段不生成文件夹。
4. 波浪号 `~` 处理：CLI 参数解析阶段统一 `expanduser`，全链路路径判断使用标准化绝对路径，防止 MINGW、Windows 路径识别失败。

---

## 六、关键字段对照表（固定命名，全局统一）

| 字段名                   | 类型       | 作用                                                     |
| ------------------------ | ---------- | -------------------------------------------------------- |
| `self.input`             | `Path`     | 标准化后绝对输入路径                                     |
| `self.is_file`           | `bool`     | 标记输入是否为单个文件                                   |
| `self.parent_path`       | `Path`     | 输入对应的父目录（文件输入时为父目录，目录输入时为自己） |
| `self.output_raw`        | `str/None` | 命令行原始 `-o` 输入字符串                               |
| `self.outpath`           | `Path`     | 最终业务输出目录（需创建）                               |
| `self.default_temp_name` | `str`      | 类属性，命令默认子目录名                                 |

---

## 七、开发者注意事项

1. 新增命令时，建议直接调用 `resolve_final_output_dir` 或 `get_extract_output_root`，避免重复实现路径计算逻辑。
2. 若命令需要类似 `extract` 的多级目录结构，参考 `ExtractFunction`，使用 `get_extract_output_root` 并配合 `run_on_input_directory` 的 `subdir_name` 参数。
3. 所有路径工具函数均位于 `utils/path_utils.py`，通过 `utils` 包暴露（`from utils import resolve_final_output_dir, get_extract_output_root`）。
4. 修改 `default_temp_name` 后，无需改动其他代码，路径计算自动生效。
5. 测试时应覆盖：文件/目录输入、有无 `-o`、纯名称/完整路径，确保输出目录符合预期。

---

## 八、历史变更与版本记录

- **v2.0**（当前）：统一 `crop`/`rembg`/`cropremove` 路径规则，引入 `resolve_final_output_dir`，目录输入时输出与输入并列；`extract` 增加 `images` 子目录层，`-o` 对目录输入生效。
- **v1.x**：旧版 `rembg` 在目录输入且未指定 `-o` 时，输出在输入目录内部（`input/rembg`），现已修正。

---

文档维护：`docs/io_path_rules.md`，随代码同步更新。
