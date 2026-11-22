# -*- coding: utf-8 -*-
"""菜单文案、URL 与顶栏配色常量（自 ``desktop/ui/menu.py`` 拆出）。"""

from __future__ import annotations

from desktop.ui import theme as T

#: 项目主页（「关于」显示 / 「检查更新」失败时的兜底指引）。
#: ⚠️ 与 ``desktop/workers/update_worker.py::RELEASE_API`` 指同一仓库，
#: 换仓库/组织时两处要一起改。
PROJECT_URL = "https://github.com/zunkun/gujitools"

#: 去底色数据包（YOLO 权重）所在的**另一个仓库**的 release 页（失败时的兜底指引）。
#: ⚠️ 与 ``utils/data_package.py::RELEASE_DOWNLOAD_BASE`` 指同一仓库/同一 tag。
DATA_PACKAGE_URL = "https://github.com/zunkun/gujitrain/releases/tag/database"


#: 顶级菜单与各动作文案。**含 ``&`` 助记符**（显示成下划线，``Alt`` 可唤起）；
#: 集中在这里，自测按这些常量断言（改文案只动一处）。
MENU_FILE = "文件(&F)"
MENU_EDIT = "编辑(&E)"
MENU_MODULES = "独立功能(&S)"
MENU_HELP = "帮助(&H)"
#: 「编辑」菜单的四项动作（用户 2026-11-01）：删除选中 / 插入图片 / 下载图片 /
#: 打印图片。菜单层**零业务**：可点性与动作全问当前页的同名方法
#: （``can_edit_delete_selected`` / ``edit_delete_selected`` …，见
#: ``build_edit_menu``），这样别的页面有同类动作也照这套接，不必 import 具体页面。
ACTION_DELETE_SELECTED = "删除选中(&D)"
ACTION_INSERT_IMAGES = "插入图片(&I)"
ACTION_DOWNLOAD_IMAGE = "下载图片(&X)"
ACTION_PRINT_IMAGE = "打印图片(&P)"
#: 四项能力 → 菜单项文案/提示（顺序即菜单顺序）。
EDIT_MENU_ITEMS = (
    ("delete_selected", ACTION_DELETE_SELECTED,
     "删除当前页面里选中的图片；不能删除的页面会自动置灰"),
    ("insert_images", ACTION_INSERT_IMAGES,
     "向当前页面插入图片（PDF排版可恢复已删除的图片）"),
    ("download_image", ACTION_DOWNLOAD_IMAGE,
     "把当前显示的图片另存到磁盘"),
    ("print_image", ACTION_PRINT_IMAGE,
     "把当前显示的图片送到打印机"),
)

ACTION_CREATE_TASK = "新建任务(&N)"
#: 「快速任务」（用户 2026-10-16）：选 PDF **直接建任务**，不经过创建任务页、
#: 不问名称/流程（**任务名 = PDF 文件名**，流程用默认模板）。
#: 助记符取 ``Q`` 而不是 ``K``：``K`` 在「文件」里没有别的含义，但 ``Q`` 更贴
#: 中文"快速"的拼音首字母（quick），也不与其它助记符冲突。
ACTION_QUICK_TASK = "快速任务(&Q)"
#: 「快速任务」选文件时的对话框标题（与创建页那个「选择 PDF/DjVu」区分开，用户
#: 一眼能看出是从菜单直接走的路）。
QUICK_TASK_PICK_TITLE = "选择 PDF/DjVu（快速任务）"
ACTION_QUIT = "退出(&X)"
ACTION_MANUAL = "帮助文档(&D)"
ACTION_UPDATE = "检查更新(&U)"
#: 「检查更新」菜单项在**发现有新版本**时追加的提示后缀（用户 2026-10-15：启动时
#: 后台自动查，有新版本就在菜单上提示）。版本号放 tooltip 里——菜单项宽度有限，
#: 塞一长串会把「帮助」菜单撑得很宽。
NEW_VERSION_SUFFIX = "　·　有新版本"
#: 「检查更新」的悬停提示（无新版本时的默认文案）
ACTION_UPDATE_TOOLTIP = "联网检查最新版本（直连 + 三个镜像，自动选最快的那条）"
#: 检查/下载期间菜单项的临时文案
ACTION_UPDATE_BUSY = "正在检查更新…"
ACTION_UPDATE_DOWNLOADING = "正在下载更新…"
#: 「检查数据包」菜单项（帮助菜单里，紧跟「检查更新」）。它检查的是**权重仓库**
#: （``zunkun/gujitrain``）``database`` release 里的 ``data.json``，与程序自身
#: 更新是两码事——所以单独一项、单独的控制器（用户 2026-10-16）。
ACTION_DATA_PACKAGE = "更新数据包(&M)"
#: 数据包菜单项的悬停提示（无新版时的默认文案）
ACTION_DATA_PACKAGE_TOOLTIP = (
    "联网检查去底色模型（bookcontent）是否有新版本，可直接下载并在本机启用"
)
#: 检查/下载期间菜单项的临时文案
ACTION_DATA_PACKAGE_BUSY = "正在检查数据包…"
ACTION_DATA_PACKAGE_DOWNLOADING = "正在下载数据包…"
ACTION_ABOUT = "关于(&A)"

#: 弹窗按钮文案。⚠️ 主按钮「下载」= **应用内下载**（用户 2026-10-16：不要再跳浏览器
#: 让用户自己下）；「前往下载页」降级为**备用**次按钮（开浏览器，同样这条要求）。
BUTTON_OK = "好的"
BUTTON_DOWNLOAD = "下载"
BUTTON_BROWSER = "前往下载页"
#: 下载进度弹窗的按钮：取消下载
BUTTON_CANCEL = "取消"
#: 安装包下好后的收尾（用户：下好后提示重启，软件装更新）
BUTTON_INSTALL = "立即重启安装"
BUTTON_LATER = "稍后"
#: 下载失败后的重试（会自动换下一条可用线路）
BUTTON_RETRY = "换条线路重试"

#: 「检查更新」成功分支的两种结论
RESULT_LATEST = "latest"  # 本机已是最新
RESULT_NEWER = "newer"  # 有更新版本

#: 失败分类 → 中文原因。⚠️ 词表与 ``update_worker.kind`` **一一对应**（别各写一份）。
FAILURE_REASONS = {
    "network": "连不上更新服务器（可能是断网，或网络策略拦了 api.github.com）。",
    "not_found": "没找到发布记录（仓库或发布可能已调整）。",
    "rate_limited": "请求过于频繁，被 GitHub 限流了。",
    "bad_json": "服务器返回的内容无法解析。",
}


#: 顶部标题栏（图标 / 标题 / 菜单那一整条）的底色。
#:
#: 用户 2026-10-15：「'文件' 等这些菜单有白色背景色，跟原本颜色不一致，因此顶部
#: 区域背景色建议改成一致的，区别于系统其他地方的灰色」——所以整条顶栏统一到这
#: 一个色（菜单栏自身改透明，见 ``install_menu_bar``），并取**白**：白色是"窗口装饰"
#: 那一档（左侧导航栏也是白），与正文区的灰底 ``T.CANVAS`` 一眼分得开；标题栏若跟
#: 正文同灰，看上去就像正文的一部分、没有"标题栏"的样子。
TITLE_BAR_BG = T.SURFACE

#: 顶栏与菜单栏共用的字号（用户 2026-10-15：标题「古籍重製」与菜单字大小不一致，
#: 要求"改成一样大小、文字对齐"）。
#: ⚠️ 光字号一样还不够——两边控件的**行高**也要一样，否则各自垂直居中后基线会错开
#: 一两像素（用户口径："即使不一致，也要底部对齐"）。所以再钉一个统一行高。
TITLE_BAR_FONT_SIZE = T.SIZE_BODY
TITLE_BAR_ROW_HEIGHT = 24
