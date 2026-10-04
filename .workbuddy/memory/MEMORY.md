# gujitools 记忆

古籍重製 PDF→提图→检测框→去底色→生成PDF。双入口共用算法：`cli.py`(打包`guji`)/`desktop.py`(PySide6+qfluentwidgets)。分层`utils←core←{cli,functions,desktop}`**严格单向**。分支`stitch`。⚠`docs/**`基准 main，本分支**以代码为准**。会话过程见`2026-10-0*.md`。
（本文件有体积上限，曾被截断——**新增内容请先删旧的**，别一路堆。）

## 提交纪律
⚠️**长期有大量未提交在制品**（曾积 60+ 文件）。⚠️**AI 禁止自动 `git commit`**，等用户说「提交」。提交前必做：①`git diff > /tmp/b.patch` **加**逐个`cp`未跟踪文件（patch 不含新文件）——**备份放`/tmp`别放仓库内**；②先跑相关自测；③`git add -A` 后用`git diff --cached --name-only | grep -E "_out/|\.png$|\.log$"`兜临时产物（`--list`输出重定向的`_list.txt`不受`_*/`规则保护）。⚠️自测退出码 **127 是伪错误**（末段`QThread: Destroyed`）且**会吃掉收尾一批模块**⇒光看 PASS/FAIL 计数会误判全绿，**必须比对 `--list` 计划数 vs 日志`==标题==`数**再用 `--only` 补跑。⚠️要**部分**提交时（纯净版+在制品共存）才有"锚点脚本重放/行级diflib判归属/纯净版不挂靠制品字段"那套（见`2026-10-03.md`）；**全量入库时不适用**。

## 进度显示（2026-10-03 补齐独立页）
独立功能页进度用 `desktop/components/progress_row.py::ProgressRow`（条+计数**同行**），四方法 `start/update/succeed/fail`+`reset`；条在 `StepControl` 内（执行按钮上方）⇒ 四步骤页白拿。**拼版页自备**（不继承`StepModulePage`）；**detect 导出标注图是并行第二执行线⇒单配 `export_progress`**。⚠`ProgressLine`上限0走滑动态（定时器**仅可见时**启动，点亮要显式`refresh_animation()`）。⚠单位取`StepSpec.progress_noun`（页/张，**≠`input_noun`**的PDF/图片）。⚠`progress_total`被**两个**reporter都归一化成`done=0`progress（常量`core.reporter.PROGRESS_TOTAL_EVENT`）——改协议要同步改`tests/reporter_cli_parity.py`的契约。⚠job的`report`可能是`None`（`module_edit_sync`直传None），汇报处必判。

## 事实来源（别另写一份，漂移必出 bug）
- CLI参数`core/command_spec.py`｜桌面默认值`components/panels/params_spec.py`｜色距字号`ui/theme.py`｜JSON`store/json_io.py`(临时文件+`os.replace`原子落盘)。
- 框几何`utils/box_geometry.py`：半幅恒2槽[左,右]/整幅恒1槽[整幅]，**下游靠槽数辨形态**(勿按"剩几个框"推)；绘制`box_draw.py`（⚠**标注统一走`draw_slots(img,page.slots())`**，名/色按槽位给，CLI `--save` 与 GUI「导出标注图」共用，别再手写颜色表）｜排版`page_layout.py`｜页序`sort_utils.pdf_custom_sort_key`。
- 步骤`desktop/steps/spec.py::SPECS`唯一(STAGES/MODULES/PANEL_CLASSES全派生，`role`⊥`nav`；文案按界面面分字段，别合并)。详情页形态也是spec字段；页面内一律查`ports.spec_for_stage(stage)`，⚠别用`spec_by_key`(`rembg_submit`→None)。**连线只改`ports.SUPPLIERS`**；`inputs/outputs`是唯一真源、须与事实一致(漏写=假边)。
- 连线`steps/ports.py`：`SUPPLIERS`=BPM的边(换序只改它)；端口只在`StepSpec.inputs/outputs`声明且**须与事实一致**(漏写=假边)；取路径只走`store.artifact()/stage_input()`；运行阶段≠步骤key，看`STAGE_STEPS`。
- 独立页左栏=缩略图条+大图(2026-10-03定)→`modules/thumb_source.py::ThumbSourceMixin`(`show_source/show_pdf/show_images`)；⚠别自起`PreviewWorker`/`ImageThumbCacheWorker`；拼图页**不继承**(左栏是拼版页清单)，只复用`singletask_dir`。缓存`files.image_thumb_cache_path`=`singletask/<子任务>/thumbs/<边长>/<键>.jpg`，键=`book_key`**含文件大小**⇒编辑换尺寸即换键；边长须进目录名。
- 普通步骤页外设`modules/base.py::StepModulePage`(`_build_preview`/`on_result`；钩子`source_summary/source_images/on_failed/edit_effect_note`)；拼版页**有意**不继承。

## 关键契约
- ⚠**singletask≠taskdetail**(用户2026-10-04强调"不是一回事")：组件/worker共用但**缓存根各归各**——独立页缓存`singletask/<子任务>/`；任务流程缓存`tasks/<id>/thumbnails/{source,print,imposition}`(拼板左列缩略图=`imposition`)，**禁止借道**；taskdetail缓存随`delete_task`整体rmtree一并清理。
- 第四步取图=第三步「提交本次任务」成品图(2026-10-01定)：改去底色结果/area/border⇒**必须重新提交**才进PDF。detect页交付`<输出目录>/boxes.json`与`tasks/<id>/boxes.json`逐字段一致。日志区`LogPanel`(`log()`=append)。
- `ImageViewerWidget`两形态：图片模式(`set_images`/`set_thumb_source`)、PDF页模式(`set_pdf_source`+`begin_pdf_pages`+`set_pdf_thumb`，大图按需`PreviewWorker(pdf,page=idx)`渲高清，**不是**放大256px小图)。⚠`set_images`须先`_clear_page_source()`；`gen`代际号防旧书串页。
- print页：未生成=源图缩略图，生成后=产物PDF页缩略图。`RembgPreviewWidget.set_images(paths, rembg_dir)`**第二参是结果目录**，换源传None；缓存就绪用`set_cached_thumbs({path:cache})`(整体替换)/`set_cached_thumb`(单条)。
- **编辑生效链**(2026-10-03补齐，五独立页全对齐)：`ZoomPopupMixin`(双击/右键预览·编辑)→`ImageEditorDialog(save_back=True)`→`overwrite_image_file`→`image_saved`信号；独立页由`ThumbSourceMixin._wire_source_edit()`接(`base.StepModulePage.__init__`末尾duck-type调，保持base不import thumb_source)：`_show_edited_image`(优先`apply_edited_image`)+`_reload_edited_thumb`(**先pop`_thumb_cache_ready[path]`再`refresh_page`**)＋各页`edit_effect_note()`提示何时生效。拼图页四条信号`item/spread_{preview,edit}_requested`由`imposition/page.py`接线：单张覆盖源图(+`canvas.invalidate_image`)；整页组合→全分辨率合成→编辑器→`singletask/拼图/edited/<页>.png`，由`_compose_job`按页盖回；版面一改即作废(`_page_overrides`口径须同`compose_doc`)。任务侧`TaskDetailPage._on_page_image_saved`。
- **「完成」覆盖确认**(2026-10-04)：`ImageEditorDialog._confirm_overwrite()`在**任何烘焙前**问一句，选「返回继续编辑」则弹窗不关、编辑全留。⚠`_finishing`须**先于**确认框置位(`MessageBox.exec()`自带事件循环,双击会叠框)。四个短路`return True`：`not save_back`(虚拟预览不写盘)/`not target_exists`(整页组合首次编辑写的是新建文件)/`_image==_original`(没改动)/`MessageBox`抛异常(自测替身)。⚠`editor.target_name`(点名文件)**只能做属性、不能加进`_open_editor`/`__init__`**——自测替身`_StubEditor(parent,image,save_back)`按死签名覆盖，加kwarg即`TypeError`；**给自测会替身化的函数加参数前先grep替身签名**。
- **落地口径：独立任务 vs 任务流程**(2026-10-04核实，**现状已对、勿"修"**)：独立任务页「应用」**一律落地实体文件**(`edit_current_image`走`overwrite_image_file`原子覆盖)；任务流程**看目标**——有`ZoomTarget.edit_path`才落地(区域合成/打印效果等**派生显示**改的仍是它派生的真实文件)，PDF矢量页无可回写文件、右键菜单不给「编辑图片」。判据是`edit_path`，**不是"在哪个页面"**。

## 硬规则
- **绝对导入**；根`desktop.utils.files.project_root()`。跨层白名单`tests/selftests/layering.py`；⚠`desktop→functions`违规(函数内延迟导入合规)。
- ⚠GUI主进程不许进重依赖(`functions.detect`→cv2)：主进程用的纯规则须放 utils 且不 import functions(`box_geometry`有AST守卫)。检测只有`functions.detect.detect_page_content`。
- 中文路径勿直用`cv2.imread/imwrite`，走`utils.image_io`。
- 界面：控件`paintEvent`自绘不引样式表；下拉`widgets.combo_box()`；窗口尺寸`ui/window_size.apply_window_size`。
- 跨线程用`desktop.workers.connect_queued`(`connect(lambda)`不可靠)。
- ⚠**`QThread.run()`必须 try/except**(“点了没反应”根因)：异常逃出run不杀进程，`result=None`+`cancelled=False`⇒上层当“用户取消”静默弹撤销点。存`self.error`再raise；`run_with_progress`收尾须在**读cancelled/result之后**并 try/finally。
- `StepKernel.event`/`StepControl.event`透传非 progress/log 事件(detect的`page_boxes`走它)。
- ⚠**「点空白处」不弹两选项小菜单**(2026-10-03「底部不设置选择图片或目录的弹窗」=指锚在控件**底部**的`RoundMenu`)：已删`_ask_kind`/`_anchor_point`，点空白**直接**开选文件对话框。⚠⚠**"资源管理器"要分清"浏览窗口"vs"选择对话框"**：用户要**选择对话框**(`QFileDialog` **原生**，**不设**`DontUseNativeDialog`)，不是`explorer.exe`浏览窗口——曾误做成"弹浏览窗口+子线程轮询监听选中项"被否，`shell_pick.py`/`explorer_pick.py`已删除。⚠留档(别再试UIA)：Win10+文件列表是`DirectUIHWND`无`SysListView32`(`LVM_*`全废)，`CoCreateInstance(CLSID_CUIAutomation,IUIAutomation)`返`E_NOINTERFACE`。
- ⚠**回滚/二分未提交在制品禁用`git checkout HEAD -- <文件|目录>`**(本仓库长期有大量未提交在制品，会连在制品一起抹)：用Python按**标记字符串切片替换**(`s.index(起始标记)`→`s.index(下一标记)`)，只动自己那段；必须先`Copy-Item`备份。勿用`git show <sha>:<path>|Out-File -NoNewline`(换行会丢)；掉stash：`git stash pop`→`git fsck --unreachable`→`git checkout <sha> -- <路径>`。
- ⚠`SourceZone`内有**真按钮子控件**：几何靠`_relayout_buttons()`，改paintEvent须避开按钮区(`EMPTY_HEIGHT`=168含按钮行)；`accepts_dir=False`不摆目录按钮；**入口是主路径就必须画成按钮**；`_open_dialog`须try/except转`rejected`(内部调`_pick`弹原生`QFileDialog`)；测点击用`QTest.mouseClick`且控件须在已显示窗口。
- ⚠按页号命名的缓存不能跨书共用(→`files.singletask_thumbnails_dir`分层)。⚠自测判子控件可见用`isHidden()`(**不是**`isVisible()`/`isVisibleTo(parent)`——前者对未挂到已显示窗口的子树恒False，独立页则因初始只显示输入区、整个分栏都藏着而两者都假红)。
- ⚠“重跑同一个源”不是“冲突”：收尾“已存在就跳过”须先`filecmp.cmp(shallow=False)`比内容，只判存在⇒产物永久翻倍；显示侧再去重一道。
- ⚠自测勿手写 JPEG/PNG 十六进制字节，用 Qt 现场编码。
- ⚠**传路径的公开API须在边界`Path()`收口**(viewer `set_images`+worker `__init__`两道)：鸭子异常发生在子线程`run()`里，只经`failed`显示、无堆栈。
- ⚠**同一输出目录只准一个写入者**：`stages/imposition`有两条合成路径(后台防抖worker+`runner.py`的`_compose_imposition_now`)，`compose_doc`整轮持`_COMPOSE_LOCK`+`_save_page_atomic`(两道各挡一类故障，缺一不可)。新增写入路径自己带锁，别直接`compose_page()`落盘。
- ⚠**自我续期的`QTimer.singleShot(0)`＝CPU 风暴**：0间隔=事件循环一空闲就接下一批。分批解码必须带间隔(`picker.THUMB_GAP_MS=150`)。⚠"首批立刻开始"的`singleShot(0)`是对的，别一起改。
- ⚠`HEIGHT_UNLIMITED`必须`(1<<24)-1`(Qt硬上限)，写`1<<24`每次进独占页刷stderr警告。

## 测试
`QT_QPA_PLATFORM=offscreen KMP_DUPLICATE_LIB_OK=TRUE <py> -u tests/gui_selftest.py`。⚠必带`-u`(否则偶发退出码127伪错误+0字节stdout)；勿用`--only`循环跑全量(会重跑依赖链)，一次全量+`--skip`；`--skip`只接**逗号串**；用例=`tests/selftests/*.py`(`NAME`/`DEPENDS`/`TEARDOWN`自动发现)。
- ⚠运行器遇模块异常**re-raise终止整轮**⇒`DEPENDS=[]`的模块即使依赖被skip也照跑。本机**环境性红**(改前就红；可直接复制的跳过串见`2026-10-03.md`)：缺`static/guji.yaml`、缺**fpdf2**(整个print链，含`DEPENDS=[]`的`print_rect_pdf_e2e`/`print_stream`)、缺`guji.spec`、缺ultralytics、QProcess FailedToStart、`empty_input`/`input_robustness`/`failure_visibility`/`reporter_cli_parity`/`reporter_worker_e2e`/`resume`；`image_editor*`/`resource_lifecycle`红是**未提交遗留改动**。
- ⚠长跑末`QThread: Destroyed`硬中止(时序flake，**退出码127是伪错误**)：它**会吃掉排在其后的模块**⇒**看`[PASS]`/`[FAIL]`计数 + 核对模块清单**，被挡的用`--only "<那批>"`补跑。
- ⚠跨模块残留异步回调会打后一模块monkeypatch(`worker_thread_affinity`偶发6/9)：单跑即绿⇒非回归。⚠分批调度交`ThumbsMixin._load_thumbs_chunked`。⚠离屏`QGraphicsScene`(拼版画布)不渲染，截图空白非缺陷。
- 改`functions/`|`utils/`必跑`tests/reporter_cli_parity.py`|`reporter_worker_e2e.py`|`cli_print_smoke.py`(GUI全绿≠CLI没坏)。文档`tools/gen_api_docs.py --check`+`tools/check_docs.py`；视觉自查`tests/gui_shot.py`(只覆盖任务流程页，独立页需自写探针且**出图后删**)。解释器`C:\Users\zunkun\anaconda3\python.exe`(managed 3.13无PySide6)。

## 进程/存储
- 主进程不载cv2/torch/PyMuPDF；每阶段一worker子进程，stdout=**JSON Lines**(started/progress/log/page_boxes/page_size/finished/error/cancelled)，坐标由`core.reporter.Reporter`结构化上报，**不解析中文提示**。数据根`~/Documents/guji`纯JSON无库：`tasks.json`/`ui.json`/`tasks/<0001>/{pages,runs,boxes,sizes,print,drafts,thumbnails,stages/*}`/`singletask/<子任务>/{thumbnails,thumbs,edited}`(独立区**只放缓存不放产物**)。拼版合成`desktop/services/imposition.py`。

## 踩坑
- `--clean`：CLI默认False但`FunctionBase.execute()`兜底**True**⇒自建参数字典须显式给`clean`。
- `rembg`输出固定PNG；第三步「提交产物」是**白底透明PNG**，透明须在合成之后加。⚠**JPG缩略图不能直存带alpha的图**(透明固化全黑)：`thumb_cache_worker`产出前必过`flatten_on_white`(`is_all_black`体检自愈旧黑缓存)——2026-10-04修「拼板左列全黑」，同类新渲染路径照此办理。
- `print`只能`guji run print`；页序以`files`清单为准，空才回退文件名排序。
- 整幅页`fullcontent`：框原样下传，area=1/2/3结果一致，**只有area=4保留框外内容**。
- 高分屏绝不手`painter.scale(dpr,dpr)`；dpr改动须用`QT_SCALE_FACTOR=1.5`**真进程**验。
- 手册页`os.startfile`只传原生路径；手册HTML不加`<base>`。
- 校验import用AST(`tests/selftests/_context.py::imported_modules`)，勿文本匹配。
- `.gitignore`裸模式`guji.yaml`会**误伤模板**`static/guji.yaml`(**从未进git**)，而`functions/init.py`读它当模板；应改`/guji.yaml`(**未改**)。
- `python build.py`(11~15min，开头直删`dist/`/`build/`)；往`requirements.txt`加包须同步加进`install_build_dependencies()`开头探针，否则yolobuild永不重装；勿往`excludes`加`torch.*`(会让`guji crop` ModuleNotFoundError)；手册`--manual-only`(~2.5min)；打包后`tools/check_bloat.py`/`smoke_frozen.py`。

## 文档地图
`docs/guide/*`用法｜`docs/dev/gui/gui-architecture.md`架构/进程模型｜`gui-technical-spec.md`Worker协议/JSON/area｜`gui-ui-system.md`**改界面必读**｜`docs/dev/io_path_rules.md`路径｜`docs/dev/utils.md`算法｜`docs/functions/*.md`命令手册(**位置固定不可移动**)｜`docs/api/*.md`签名(**自动生成禁手改**)。
