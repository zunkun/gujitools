# gujitools 记忆

古籍重製：PDF→提图→检测框→去底色→生成PDF。双入口 `cli.py`/`desktop.py`(PySide6+qfluentwidgets)。分层 `utils←core←{cli,functions,desktop}` 严格单向。

> ⚠只放"高频必守"判据；全部判据在 `MEMORY-details.md`，理由与量化在当日日志。改某子系统前先检索这两处。⚠新增先删旧的。

## 记忆规范

- MEMORY.md 不要过大，大则压缩到合理范围。
- 日志只保留最近 2 天；当天日志过大则删前一天、只保留当天 1 天。

## 纪律

- AI 禁止自动 git commit：只汇报 status/diff，等用户说"提交"。"撤回"＝`git reset --soft HEAD~N`（绝不 --hard/checkout --/restore/stash）。
- 用例只进 `tests/selftests/<名>.py`；禁仓库根新建脚本；临时数据落 `tests/tmp/`（`tmpdir.py::temp_dir()`，先 `install()`）；临时脚本放 `_scratch/` 收工删净；别往 .gitignore 补 `_*.py`。

## 自测

- `QT_QPA_PLATFORM=offscreen KMP_DUPLICATE_LIB_OK=TRUE python -u tests/gui_selftest.py --only <mod>`（必带 -u）。解释器＝`C:/Users/liuzu/anaconda3/python.exe`。判"新断言跑了没"＝grep 断言文本。127＝伪错误吃掉其后模块 ⇒ 核对 --list 补跑；--skip 连坐依赖。
- ⚠本会话：QProcess worker 模块必红；steps_components/thumb_cache 本会话跑不了，留用户本机。
- ⚠离屏：绝不真弹模态；判"能点"✅QTest.mouseClick，❌childAt()；双向验证＝子进程注入、cp 备份还原。
- ⚠CRLF/LF：按 `\n` 匹配、写回保留原行尾。文档 `gen_api_docs.py --check`＋`check_docs.py`。

## 事实来源

CLI参数`core/command_spec.py`｜桌面默认值`panels/params_spec.py`｜步骤`steps/spec.py::SPECS`唯一（5张表全派生）；中文名`ports.stage_label()`。框几何：半幅2槽/整幅1槽；页序`sort_utils.pdf_custom_sort_key`。

## 图片预览/编辑（详见 MEMORY-details.md）

- ⚠编辑开关：`image_editable` 构造参数＝"是否可编辑图片"，与清单管理 editable 是两件事。去底色两处宿主传 False；门在入口层，运行期改＝`set_image_editable()`。
- ⚠统一变换一条数学 `geometry.compose_transform`；绝不用 QPainter.setTransform+drawImage(rect,region)；尺寸闸门＝`geometry.mapped_bounds()`。预览矩阵 A\*B＝先A后B。两档预览不可混用；整幅烘焙异步；纯翻转走 mirrored。空处填色唯一口径 `_empty_fill`（源图真 alpha⇒透明否则白）；透明 fillRect 是 no-op，擦旧内容必须切 Clear。
- ⚠grow 档透明档**内容收紧**＝`_trim_transparent_edges`（裁到 alpha>0 真实外框，原点平移跟进）：外框按画布四角算，不收紧则"旋转保存再旋转"每轮 √2 滚大、内容占比缩水（2026-10-10）。**只在透明档裁**——不透明扫描件白边可能是纸的内容。
- ⚠编辑器**入口内容提取**：`dialog.py::__init__` 装图先 `_trim_transparent_edges`——透明图带空白边一律先裁到内容外框（编辑主体永远是内容，"PA1 里编辑 PANew"）；不透明图不裁。⚠️提取后实心内容＝全不透明图→落白档不收紧，是既定扫描件语义，别当 bug 修。
- ⚠内容四角节点 sidecar（`content_quad.py`，`<file>.quad.json` 存 (rect0,V)）：二次编辑进变换工具→反变换回 upright→`begin_restored_transform(seed, upright)` 挂未触摸待定。⚠️**画布不换图**（用户 2026-10-10 终版口径：PB1 作画布、PA1 作可操作区域）：upright 只是浮层源+烘焙源（`_xf_restore_region`/`_ensure` 分支/纸面纯透明），种子矩阵＝画布系 `V·T(-(o+t))`（o=quad_frame、t=入口收紧偏移；`upright_image(origin_shift=t)`，rect 传 rect0）；烘焙输入恒＝upright（`_bake_transform_async(original=)` 别漏）、V=总量矩阵（单次代次）；crop/flip/clip/undo ⇒ `_content_clear`（宁可不恢复不能错恢复）；未拖就离开 ⇒ `_content_exit_restore` 落标志即可。宿主回填 `editor.source_path` 属性（**__init__ 签名不许加参数**——替身编辑器死签名）+ `sync_content_quad`。⚠️反变换矩阵＝`shift*inverse`（**先平移后逆旋转**，与 `placed=T*xf` 同款；写反＝内容位移 o−V⁻¹(o)、"顶部被削一段"且框仍对，2026-10-10 报障）；反变换/恢复回归**必须打色块断言"内容原位"**，只查尺寸查不出位移。
- ⚠变换松手只挂起（`_xf_pending`）：烘焙时机只有两处且都须 `force=True`——`_set_tool` 切走工具、`_finish`「完成」；不带 force 会被"挂起跳过"分支吞掉（2026-10-10 报障）。`_confirm_overwrite` 须把挂起变换当"改过"。
- ⚠子包拆分：Mixin 不许同名成员；`_host.py` 四条不变量；`preview_zoom.py` 有源码文本守卫，改调用形态要同步。

## 拼版缩略图＝实体落盘

- `components/imposition/page_thumb.py`＋worker；目录任务/独立区各归各。retain(0)＝暂态不当"全删"；memo 命中但映射不符照样排队补实体；回填只贴那一条；签名带文件指纹自动失效。
- ⚠编辑覆盖源图后必须 `refresh_rects_for_edited_source`（rect 按旧尺寸记着，compose_page 会把新图硬 resize 回旧宽高 ⇒ 压扁变形）＋`invalidate_size`（尺寸缓存只进不出）；三个编辑入口都接线了（2026-10-10）。

## Qt 通用坑

- clicked 顺手喂 checked ⇒ 接线一律套 lambda；qfluentwidgets Dialog 放不下面板 ⇒ `shell_dialog`；面板关弹窗 `self.window().close()`。
- Card 自带 layout（card.box）；判状态用 isHidden()；跨线程 connect_queued；QThread.run() 必须 try/except；GUI 主进程不进重依赖；同一输出目录只准一个写入者。

## BPM（详见 MEMORY-details.md）

- 图必须压过静态连线表；`stage_order()`＝Kahn 拓扑序；只有 task 节点映射阶段；三套下标（bar/stack/current）别混。
- 「是否拼版」＝`imposition_effective()`，界面与执行同一判据；缺输入唯一判据 `_missing_input_kind()`（PDF 优先）；`Path("")` 是 "." 且 exists() 为真。

## 进程/存储 · 文档

- 每阶段一 worker 子进程，stdout＝JSON Lines。数据根 `~/Documents/guji` 纯 JSON。`TaskDetailPage.set_task` 必须返 True。
- 文档：docs/guide/_用法｜dev/architecture.md｜gui-technical-spec.md Worker协议｜gui-ui-system.md 改界面必读｜io_path_rules.md 路径｜api/_.md 禁手改。
