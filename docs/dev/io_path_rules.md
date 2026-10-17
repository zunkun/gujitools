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
- `print`：额外支持可选参数 `files`（图片绝对路径列表），**该列表顺序即最终 PDF 页序**。
  - 传入时：按列表顺序加载图片（仅过滤不存在的路径），完全**不读目录、不解析文件名**——因此拖拽重排 / 删除条目无需改动任何物理文件；
  - 不传时：回退为遍历 `input` 目录并按 `natural_sort_key`（`utils/sort_utils.py`）排序，保持 CLI 独立用法不变；
  - `skip_pages` 与 `title_switch_nodes` 中的纯页码按**清单序号**（1 起）匹配，与文件名无关。

---

## 三、Output 通用基础规则（所有命令共用）

1. 命令行参数：`-o / --output`，可选传参，不传为 `None`，原始值存储为字符串 `self.output_raw`。
2. 最终输出字段：`self.outpath: Path`，是程序最终需要创建的业务目录，所有文件输出到此目录。
3. **所有命令的最终输出目录均包含一个固定的默认子目录名**，该名称由各命令类的 `default_temp_name` 类属性控制：
   - `extract`：`images`（不可覆盖）
   - `detect`：`detect`（**仅落盘时**才计算，命令行必须给 `--save`；
     不落盘时 `outpath = None`，无输出目录——这种用法只允许代码调用与 GUI）
   - `crop`：`crop`
   - `rembg`：`rembg`
   - `cropremove`：`rembg`（复用 rembg 的默认子目录名）
   - `print`：`pdf`
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

### 2. detect（检测文本框功能，非必要步骤）

**输出结构**：`<根目录>/detect/标注图`

- **默认子目录名**：`detect`（`DetectFunction.default_temp_name = "detect"`）。
- **根目录计算**：与 `crop` **完全同源**——`DetectFunction._resolve_outpath()`
  直接调用 `resolve_final_output_dir`，因此 detect 与 crop 是同级步骤，
  输出都落在输入目录**旁边**。

**⚠️ 只有落盘时才计算路径**：`outpath` 的取值取决于 `save`。

- `save=True`（命令行必给 `--save`）→ 按上表计算输出目录；
- `save=False` → `outpath = None`，程序**不计算路径、不创建目录、不写任何文件**，
  只上报坐标。**命令行下这种用法会被直接拒绝**（见 `cli.__main__._reject_dry_run`），
  因为没有任何产出去处；只有**代码调用**（中间步骤）与 **GUI detect 阶段**
  才允许不落盘。

**示例**（输入为 `/a/images/` 目录）：

| 命令                                      | 输出目录                            |
| ----------------------------------------- | ----------------------------------- |
| `detect -i /a/images/`                    | ❌ 命令行拒绝（代码调用可无输出）   |
| `detect -i /a/images/ --save`             | `/a/detect/`（与 images 并列）      |
| `detect -i /a/images/ --save -o out`      | `/a/out/detect/`                    |
| `detect -i /a/images/ --save -o /abs/out` | `/abs/out/detect/`                  |
| `detect -i /a/photo.jpg --save`           | `/a/detect/`（与 photo.jpg 同目录） |

---

### 3. crop（裁剪功能）

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

### 4. rembg（去底色功能）

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

### 5. cropremove（裁剪 + 去底色复合流程）

**输出结构**：`<根目录>/rembg/图片文件`

- **默认子目录名**：`rembg`（`CropRemoveFunction.default_temp_name = "rembg"`）。
- **根目录计算**：与 `crop`、`rembg` 相同，调用 `resolve_final_output_dir`，`default_subdir="rembg"`。

**规则**：与 `rembg` 输出结构相同，但处理流程为裁剪后去底色。

---

### 6. 实现位置与默认子目录对照

| 功能类               | 文件                       | 使用的工具函数                                                        | 默认子目录名 |
| -------------------- | -------------------------- | --------------------------------------------------------------------- | ------------ |
| `ExtractFunction`    | `functions/extract.py`     | `get_extract_output_root` + `run_on_input_directory` 的 `subdir_name` | `images`     |
| `DetectFunction`     | `functions/detect.py`      | `resolve_final_output_dir`（**仅落盘时**，命令行强制 `--save`）       | `detect`     |
| `CropFunction`       | `functions/crop.py`        | `resolve_final_output_dir`                                            | `crop`       |
| `RembgFunction`      | `functions/rembg.py`       | `resolve_final_output_dir`                                            | `rembg`      |
| `CropRemoveFunction` | `functions/crop_remove.py` | `resolve_final_output_dir`                                            | `rembg`      |

子目录名来自 `functions/base.py` 的 `DEFAULT_TEMP_NAME_MAP`（键为命令名），
`FunctionBase.__init__` 把它取到实例属性 `self.default_temp_name`。
**新增命令时只需在这个映射里加一行**，路径层不需要改。

### 7. 常见调用示例

```bash
# 输入为单个 PDF，未指定 -o → 输出在 PDF 同目录
python cli.py extract -i /path/to/file.pdf
#   → /path/to/file_stem/images/1.jpg ...

# 输入为单个 PDF，-o 为纯名称
python cli.py extract -i /path/to/file.pdf -o preview
#   → /path/to/preview/file_stem/images/1.jpg ...

# 输入为目录，未指定 -o → 每个 PDF 一个子目录，输出与输入目录并列
python cli.py extract -i /path/to/pdfs/
#   → /path/to/pdfs/pdf1_stem/images/... , /path/to/pdfs/pdf2_stem/images/...

# crop / rembg / cropremove：目录输入时输出与输入目录并列
python cli.py crop -i /path/to/images/
#   → /path/to/crop/

python cli.py crop -i /path/to/images/ -o out
#   → /path/to/out/crop/

python cli.py rembg -i /path/to/images/ -o D:\output
#   → D:\output\rembg\
```

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

## 八、任务目录布局与「同类型多节点」（桌面端任务流程）

CLI 的路径规则（上文）只回答"命令把产物放哪"；任务流程另有一层**任务目录内**的
布局，唯一真源是 `desktop/steps/ports.py::STAGE_LOCATIONS`（加一步 = 加一行表）。

```
tasks/<任务号>/
├── flow.bpmn                 流程图（节点 + 连线，含坐标）
├── pages.json                当前参与处理的页清单
├── boxes.json                检测框坐标（端口 boxes）
├── sizes.json                页面图片原始尺寸（框坐标的缩放基准）
├── print.json                待打印列表 + 页序 + 逐页版面
├── runs.json                 每个阶段的执行历史（最新在前）
├── ui.json                   界面状态（上次停留的步骤/节点、YOLO 导出记忆）
├── drafts/<阶段>.json         用户改过但还没执行的参数暂存
├── drafts/imposition.json    拼版版面（选择态 enabled + 逐页 items）
└── stages/
    ├── input/                入口图片（用户直接放进来的图）
    ├── extract/              提取出的页面图
    ├── rembgpreview/         「生成预览」的整页去底图（中间产物）
    ├── rembg/                「提交本次任务」的定稿成品（print 的取图来源）
    ├── imposition/           拼版合成出的成品整页图
    └── print/                生成的 PDF
```

### 1. 同类型多节点：主节点沿用旧路径（零迁移）

「图片拼版 / 检测文本框 / 图片去底色 / PDF排版」这几个步骤在流程图里**可以有多个
节点**，它们彼此独立（各自输入、各自产物、各自参数）。为不惊动任何现存任务，
落点规则是**主节点沿用旧路径、副本节点加后缀**：

| 文件/目录        | 主节点（同阶段第一个节点） | 副本节点（第二个及之后）        |
| ---------------- | -------------------------- | ------------------------------- |
| 阶段产物目录     | `stages/extract`           | `stages/extract~Node_3`         |
| 检测框           | `boxes.json`               | `boxes~Node_2.json`             |
| 页面尺寸         | `sizes.json`               | `sizes~Node_2.json`             |
| 页清单           | `pages.json`               | `pages~Node_2.json`             |
| 待打印列表       | `print.json`               | `print~Node_2.json`             |
| 参数暂存         | `drafts/rembg.json`        | `drafts/rembg~Node_2.json`      |
| 拼版版面         | `drafts/imposition.json`   | `drafts/imposition~Node_3.json` |
| PDF 排版输出目录 | `stages/print`             | `stages/print~Node_2`           |

- **后缀规则只有一份实现**：`ports.scoped_name`（目录名加在结尾、文件名加在扩展名
  前）；节点 id 先过 `ports.sanitize_node_id`（只留字母数字与 `._-`），防止用户在
  bpmn.io 里把 id 改成带 `/` 的串把产物引到任务目录之外。
- **"谁是主节点"由图决定**：`FlowDiagram.primary_of(stage)` = 该阶段在**文件声明
  顺序**里第一个节点（声明顺序比拓扑序稳定——改连线不会让主节点漂移）。
- **一切读写走 store 的入口**，别自己拼 `~<节点>`：
  `store.node_or_stage_output(task, node, stage, port)`（产物落点）、
  `store.node_input(task, node, port)`（按图回溯供给方，含入口图片回落）、
  `store.scoped_file_scope(task, node)` → 直接展开进
  `load_pages / save_draft / boxes_path / load_imposition_doc / save_print_doc`
  这类读写。
- **运行状态也按节点记**：`runs.json` 的每条记录带 `node` 字段，
  `store.node_states(task)` 给界面用（`stage_states` 保持旧口径兼容）；
  没有 `node` 的老记录归属该阶段的主节点。

### 2. 「图片去底色」有两个动作（同格），别混

`rembg`（生成预览）产 `stages/rembgpreview`，`rembg_submit`（提交本次任务）产
`stages/rembg`。**消费方要成品**，所以按图解析产出方时统一走
`ports.fold_forward(stage, port)` 折到同格里最靠后的那个动作；而"节点自己往哪写"
仍取它本阶段的落点。

### 3. runs.json 记录结构

`{阶段: [record, …]}`，`record` 含 `run_id / status / node / parameters / done /
total / started_at / finished_at / output_path / error`。`output_path` 记的是本次
执行的产物落点（按**跑的那个节点**算）。

---

## 九、历史变更与版本记录

- **v2.3**（当前）：补「任务目录布局与同类型多节点」一节——主节点沿用旧路径、
  副本节点加 `~<节点>` 后缀（B 方案，2026-10-17）。
- **v2.2**：`print` 新增可选入参 `files`（图片路径有序清单），页序由数据层
  决定，彻底移除 GUI 侧为「顺序物化」而建的 `workset` 目录；不传 `files` 时保持
  原有文件名排序行为。
- **v2.1**：把原 `docs/outputpath说明.md` 的内容并入本文（该文件与本文重复，
  已删除），补充「实现位置与默认子目录对照」与常见调用示例。
- **v2.0**：统一 `crop`/`rembg`/`cropremove` 路径规则，引入 `resolve_final_output_dir`，目录输入时输出与输入并列；`extract` 增加 `images` 子目录层，`-o` 对目录输入生效。
- **v1.x**：旧版 `rembg` 在目录输入且未指定 `-o` 时，输出在输入目录内部（`input/rembg`），现已修正。

---

文档维护：`docs/dev/io_path_rules.md`，随代码同步更新。
