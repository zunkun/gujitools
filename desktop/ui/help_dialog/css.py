# -*- coding: utf-8 -*-
"""手册页的内嵌 CSS 模板（自 ``desktop/ui/help_dialog.py`` 拆出）。"""

from __future__ import annotations

from string import Template

from desktop.ui import theme as T

# --------------------------------------------------------------------------- CSS
# ⚠️ 用 string.Template（``$NAME`` 占位）而不是 f-string：CSS 里花括号极多，
#    f-string 要把每个 { } 都写成 {{ }}，可读性直接报废。
#    颜色一律取 desktop/ui/theme.py 的设计令牌，不在这里重复硬编码色值。
#
# 版式（从外到内）：吸顶栏（品牌 + 分段开关 + 打印）→ 1200px 版心 →
# 左侧「纸面」卡片（正文，最大 900px 行宽，长文档才读得下去）+ 右侧吸顶目录。
_CSS_TEMPLATE = Template("""
:root {
  --ink: $INK;
  --ink-soft: $INK_SOFT;
  --ink-faint: $INK_FAINT;
  --bg: $CANVAS;
  --surface: $SURFACE;
  --surface-soft: $SURFACE_SOFT;
  --surface-hover: $SURFACE_HOVER;
  --surface-sunken: $SURFACE_SUNKEN;
  --border: $BORDER;
  --border-soft: $BORDER_SOFT;
  --border-strong: $BORDER_STRONG;
  --accent: $ACCENT;
  --accent-hover: $ACCENT_HOVER;
  --accent-soft: $ACCENT_SOFT;
  --danger: $DANGER;
  --danger-soft: $DANGER_SOFT;
  --radius: ${RADIUS_MD}px;
  --radius-sm: ${RADIUS_SM}px;
  --radius-lg: ${RADIUS_LG}px;
  --toc-w: 272px;
  --shell-w: 1200px;
  --shadow-1: 0 1px 2px rgba(16, 24, 32, 0.05);
  --shadow-2: 0 18px 40px -26px rgba(16, 24, 32, 0.30);
  --shadow-3: 0 10px 26px -16px rgba(16, 24, 32, 0.35);
}

* { box-sizing: border-box; }

html { scroll-behavior: smooth; }

body {
  font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
               "Noto Sans CJK SC", "WenQuanYi Zen Hei", "SimHei", sans-serif;
  font-size: 14.5px;
  line-height: 1.8;
  color: var(--ink);
  background: var(--bg);
  margin: 0;
  padding: 0;
  -webkit-font-smoothing: antialiased;
}

/* ---- 顶栏（吸顶）：品牌 + 分段开关 + 打印 ---- */
.topbar {
  position: sticky;
  top: 0;
  z-index: 60;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(10px) saturate(1.4);
  border-bottom: 1px solid var(--border);
}

.topbar-inner {
  display: flex;
  align-items: center;
  gap: 16px;
  max-width: var(--shell-w);
  margin: 0 auto;
  padding: 11px 32px;
}

.brand { display: flex; align-items: baseline; gap: 9px; white-space: nowrap; }
.brand-mark { font-size: 15px; font-weight: 700; letter-spacing: 0.04em; color: var(--accent); }
.brand-sub { font-size: 12.5px; color: var(--ink-faint); }

.tab-bar {
  display: flex;
  gap: 2px;
  padding: 3px;
  margin-left: 8px;
  border-radius: 999px;
  background: var(--surface-sunken);
}

.tab {
  padding: 6px 18px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--ink-soft);
  font-family: inherit;
  font-size: 13.5px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, box-shadow 0.15s;
}

.tab:hover { color: var(--ink); }
.tab.active {
  background: var(--surface);
  color: var(--accent);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(16, 24, 32, 0.14);
}

.topbar-actions { margin-left: auto; display: flex; gap: 8px; }

.ghost-btn {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  color: var(--ink-soft);
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}

.ghost-btn:hover { border-color: var(--border-strong); color: var(--accent); }

/* ---- 版心：纸面 + 目录 ---- */
.page { max-width: var(--shell-w); margin: 0 auto; padding: 26px 32px 56px; }

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--toc-w);
  gap: 32px;
  align-items: start;
}

.paper {
  min-width: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-1);
  padding: 38px 46px 52px;
}

.tab-content { display: none; }
.tab-content.active { display: block; }

.toc {
  position: sticky;
  top: 84px;
  max-height: calc(100vh - 118px);
  overflow-y: auto;
  padding-right: 4px;
}

/* 标题右侧拉一条渐隐细线，把「本页目录」与下面的条目分开 */
.toc-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 12px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.16em;
  color: var(--ink-faint);
  white-space: nowrap;
}

.toc-title::after {
  content: "";
  flex: 1;
  height: 1px;
  background: linear-gradient(to right, var(--border), transparent);
}

/* 整列一条引导线：读起来像大纲，而不是一堆孤零零的文字 */
#toc-nav { position: relative; padding-left: 12px; }

#toc-nav::before {
  content: "";
  position: absolute;
  left: 0;
  top: 5px;
  bottom: 5px;
  width: 2px;
  border-radius: 1px;
  background: var(--border-soft);
}

.toc a {
  position: relative;
  display: block;
  padding: 6px 8px 6px 10px;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.45;
  text-decoration: none;
  transition: color 0.15s, background 0.15s;
}

/* 当前小节：在引导线上叠一段主色（left 负值压回 #toc-nav 的 padding） */
.toc a::before {
  content: "";
  position: absolute;
  left: -12px;
  top: 5px;
  bottom: 5px;
  width: 2px;
  border-radius: 1px;
  background: transparent;
}

.toc a:hover { color: var(--accent); background: var(--surface-soft); }
.toc a.active { color: var(--accent); font-weight: 600; }
.toc a.active::before { background: var(--accent); }

/* 二级（h3）：缩进更多、字号更小、前面加一小段短横，层级一眼分得开 */
.toc a.lv3 {
  padding-left: 22px;
  font-size: 12.5px;
  color: var(--ink-faint);
}

.toc a.lv3::after {
  content: "";
  position: absolute;
  left: 10px;
  top: 50%;
  width: 6px;
  height: 1px;
  background: var(--border-strong);
}

.toc a.lv3.active { color: var(--accent); }

/* ---- 标题 ---- */
h1 {
  font-size: 27px;
  font-weight: 700;
  line-height: 1.4;
  letter-spacing: 0.01em;
  margin: 0 0 14px;
}

h2 {
  position: relative;
  font-size: 20px;
  font-weight: 700;
  margin: 46px 0 16px;
  padding: 0 0 11px 14px;
  border-bottom: 1px solid var(--border-soft);
  scroll-margin-top: 84px;
}

h2::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.36em;
  width: 4px;
  height: 15px;
  border-radius: 2px;
  background: var(--accent);
}

h3 {
  font-size: 16.5px;
  font-weight: 600;
  margin: 30px 0 10px;
  scroll-margin-top: 84px;
}

h4 { font-size: 14.5px; font-weight: 600; margin: 22px 0 8px; color: var(--ink-soft); }

.h-anchor {
  margin-left: 8px;
  color: var(--border-strong);
  font-weight: 400;
  text-decoration: none;
  opacity: 0;
  transition: opacity 0.15s;
}

h2:hover .h-anchor, h3:hover .h-anchor { opacity: 1; }

p { margin: 11px 0; }
.paper > :first-child { margin-top: 0; }

/* ---- 表格 ---- */
table {
  border-collapse: separate;
  border-spacing: 0;
  width: 100%;
  margin: 20px 0;
  font-size: 13.5px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

th, td {
  padding: 10px 14px;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--border-soft);
}

thead th {
  background: var(--surface-soft);
  font-weight: 600;
  border-bottom: 1px solid var(--border);
}

tbody tr:last-child td { border-bottom: none; }
tbody tr:nth-child(even) td { background: var(--surface-soft); }
tbody tr:hover td { background: var(--surface-hover); }

/* ---- 代码 ---- */
pre {
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 14px 18px;
  margin: 16px 0;
  overflow-x: auto;
  line-height: 1.6;
}

code {
  font-family: "Cascadia Code", "Cascadia Mono", "Consolas",
               "Courier New", monospace;
  font-size: 12.5px;
}

p code, li code, td code, th code {
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 5px;
}

pre code { background: none; border: none; padding: 0; }

/* ---- 截图：可点开看原图（1500px 截图在 900px 行宽里必然被压缩）---- */
img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 20px auto;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface);
  box-shadow: var(--shadow-3);
  cursor: zoom-in;
  transition: box-shadow 0.18s, transform 0.18s;
}

img:hover {
  box-shadow: var(--shadow-2);
  transform: translateY(-1px);
}

/* ---- 引用块 ---- */
blockquote {
  margin: 18px 0;
  padding: 12px 20px;
  background: var(--accent-soft);
  border-left: 4px solid var(--accent);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  color: var(--ink-soft);
}

blockquote p { margin: 5px 0; }

/* ---- 列表 ---- */
ul, ol { padding-left: 26px; margin: 11px 0; }
li { margin: 5px 0; }
li > ul, li > ol { margin: 5px 0; }

/* ---- 其他 ---- */
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

hr { border: none; border-top: 1px solid var(--border-soft); margin: 34px 0; }

strong { font-weight: 600; }

.foot {
  margin-top: 24px;
  padding-top: 14px;
  border-top: 1px solid var(--border-soft);
  color: var(--ink-faint);
  font-size: 12.5px;
}

/* 回到顶部 */
.to-top {
  position: fixed;
  right: 30px;
  bottom: 30px;
  width: 40px;
  height: 40px;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--surface);
  color: var(--ink-soft);
  font-size: 16px;
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  box-shadow: var(--shadow-3);
  transition: opacity 0.2s, color 0.2s;
}

.to-top.show { opacity: 1; pointer-events: auto; }
.to-top:hover { color: var(--accent); }

/* 点击截图后的放大浮层 */
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: none;
  align-items: center;
  justify-content: center;
  padding: 28px;
  background: rgba(14, 22, 28, 0.84);
  cursor: zoom-out;
}

.lightbox.open { display: flex; }
.lightbox img {
  max-width: 100%;
  max-height: 100%;
  margin: 0;
  border: none;
  border-radius: var(--radius-sm);
  box-shadow: 0 30px 70px rgba(0, 0, 0, 0.45);
  cursor: zoom-out;
  transform: none;
}

/* 手册文件缺失 / markdown 库缺失时的提示 */
.missing {
  color: var(--danger);
  background: var(--danger-soft);
  padding: 12px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(201, 58, 58, 0.22);
}

/* ---- 窄屏：目录收掉，纸面铺满 ---- */
/* 目录加宽到 272px 后，1260px 以下放不下「纸面 + 目录」两栏（正文会被压到 800px 内） */
@media (max-width: 1260px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .toc { display: none; }
}

@media (max-width: 720px) {
  .topbar-inner { flex-wrap: wrap; gap: 10px; padding: 10px 18px; }
  .topbar-actions { margin-left: 0; }
  .page { padding: 18px 16px 40px; }
  .paper { padding: 24px 20px 36px; border-radius: var(--radius); }
  h1 { font-size: 23px; }
  h2 { font-size: 18px; }
}

/* ---- 打印：去掉chrome，只留正文 ---- */
@media print {
  .topbar, .toc, .to-top, .lightbox { display: none !important; }
  body { background: #FFFFFF; }
  .page { max-width: none; padding: 0; }
  .layout { display: block; }
  .paper { border: none; border-radius: 0; box-shadow: none; padding: 0; }
  img { box-shadow: none; transform: none; }
}
""")


def _css() -> str:
    """把 CSS 模板里的 ``$TOKEN`` 换成 theme.py 的设计令牌。"""
    return _CSS_TEMPLATE.substitute(
        INK=T.INK,
        INK_SOFT=T.INK_SOFT,
        INK_FAINT=T.INK_FAINT,
        CANVAS=T.CANVAS,
        SURFACE=T.SURFACE,
        SURFACE_SOFT=T.SURFACE_SOFT,
        SURFACE_HOVER=T.SURFACE_HOVER,
        SURFACE_SUNKEN=T.SURFACE_SUNKEN,
        BORDER=T.BORDER,
        BORDER_SOFT=T.BORDER_SOFT,
        BORDER_STRONG=T.BORDER_STRONG,
        ACCENT=T.ACCENT,
        ACCENT_HOVER=T.ACCENT_HOVER,
        ACCENT_SOFT=T.ACCENT_SOFT,
        DANGER=T.DANGER,
        DANGER_SOFT=T.DANGER_SOFT,
        RADIUS_MD=T.RADIUS_MD,
        RADIUS_SM=T.RADIUS_SM,
        RADIUS_LG=T.RADIUS_LG,
    )
