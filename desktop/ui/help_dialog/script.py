# -*- coding: utf-8 -*-
"""手册页的内嵌 JS（自 ``desktop/ui/help_dialog.py`` 拆出）。"""

from __future__ import annotations

# ---------------------------------------------------------------------------- JS
# 纯原生 JS，无外部依赖（手册页是 file:// 打开的，绝不能引 CDN）。
# ⚠️ 放大浮层的 <img> 由 JS 动态创建，**不要**在 HTML 里写死一个空的
#    <img ...>：护栏按「<img 」计数核对 13 张截图，多一个空标签就红。
_JS = """
(function () {
  const tocNav = document.getElementById('toc-nav');
  const lightbox = document.getElementById('lightbox');
  const toTop = document.getElementById('to-top');

  // 记住上次看的分段：file:// 页面在 Edge/Chrome 里同样能读写 localStorage，
  // 于是下次点「用户手册」会落回上次那一页，而不是每次都被打回第一页。
  // 存储被禁用（隐私模式等）时静默降级成"每次都从默认页开始"。
  const TAB_STORE_KEY = 'guji.manual.tab';
  const rememberTab = (tabId) => {
    try { localStorage.setItem(TAB_STORE_KEY, tabId); } catch (err) { /* 忽略 */ }
  };
  const recalledTab = () => {
    try { return localStorage.getItem(TAB_STORE_KEY); } catch (err) { return null; }
  };
  const panelOf = (tabId) => document.getElementById('tab-' + tabId);

  // ⚠️ file:// 下文档 origin 是 opaque，history.replaceState 会抛 SecurityError。
  // 必须接住：曾经这个异常**中断了整个处理函数** —— 点目录时 preventDefault 已经
  // 执行（原生锚点跳转被取消），紧随其后的 scrollIntoView 却再也执行不到，
  // 用户看到的就是「点目录没反应 / 跳不过去」；切页签同样会跳过 window.scrollTo(0,0)。
  // 所以：能改就改，改不了（file://）就静默放过，滚动永远不依赖它。
  const setHash = (fragment) => {
    try { history.replaceState(null, null, fragment); } catch (err) { /* file:// 常见 */ }
  };

  const activePanel = () => document.querySelector('.tab-content.active');

  // 目录从**当前激活**的分段里现采 h2/h3 —— 两份手册各自成目录
  function buildToc() {
    if (!tocNav) { return; }
    tocNav.innerHTML = '';
    const panel = activePanel();
    if (!panel) { return; }
    const heads = panel.querySelectorAll('h2, h3');
    // ⚠️ id 必须**按页签加前缀**。曾经用的是无前缀的「sec- + 序号」写法：
    // 两份手册都从 sec-0 开始，于是 sec-0..sec-11 在两个 <section> 里各有一份，
    // 在 CLI 页签点目录时，浏览器按文档顺序跳到**第一个**同名元素——那在隐藏的
    // GUI 页签里（display:none 无法滚动）→ 表现为「点目录跳到别处 / 根本没定位」。
    const prefix = (panel.id || 'tab').replace(/^tab-/, '') + '-sec-';
    for (let i = 0; i < heads.length; i++) {
      const h = heads[i];
      if (!h.id) { h.id = prefix + i; }
      const link = document.createElement('a');
      link.href = '#' + h.id;
      link.textContent = h.textContent;
      link.setAttribute('data-target', h.id);
      if (h.tagName === 'H3') { link.className = 'lv3'; }
      tocNav.appendChild(link);
      if (!h.querySelector('.h-anchor')) {
        const mark = document.createElement('a');
        mark.className = 'h-anchor';
        mark.href = '#' + h.id;
        mark.textContent = '#';
        mark.setAttribute('aria-hidden', 'true');
        h.appendChild(mark);
      }
    }
    spy();
  }

  // 滚动高亮：取「已越过顶栏的最后一个小节」
  function spy() {
    if (!tocNav) { return; }
    const links = tocNav.querySelectorAll('a');
    let best = null;
    for (const link of links) {
      const el = document.getElementById(link.getAttribute('data-target'));
      if (el && el.getBoundingClientRect().top <= 120) { best = link; }
    }
    // 页面刚到顶（还没越过任何小节）时也别让目录一片"无高亮"——落在第一条上
    if (!best && links.length) { best = links[0]; }
    for (const link of links) { link.classList.remove('active'); }
    if (best) { best.classList.add('active'); }
  }

  function activate(tabId) {
    const tabs = document.querySelectorAll('.tab');
    const panels = document.querySelectorAll('.tab-content');
    for (const tab of tabs) {
      tab.classList.toggle('active', tab.dataset.tab === tabId);
    }
    for (const panel of panels) {
      panel.classList.toggle('active', panel.id === 'tab-' + tabId);
    }
    rememberTab(tabId);
    buildToc();
    setHash('#tab-' + tabId);
    window.scrollTo(0, 0);
  }

  for (const tab of document.querySelectorAll('.tab')) {
    tab.addEventListener('click', () => activate(tab.dataset.tab));
  }

  // 正文里指向另一份手册的链接（已在渲染时改写成 #tab-xxx）→ 切页而不是跳锚点
  for (const link of document.querySelectorAll('a[href^="#tab-"]')) {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      activate(link.getAttribute('href').slice(5));
    });
  }

  // 目录点击：显式滚动到小节，而不是只靠原生锚点跳转。
  // 原生跳转会把标题顶到视口最上沿、被吸顶栏盖住（看着像"没定位到"）；
  // 这里由 CSS 的 scroll-margin-top 留出顶栏高度，再把 hash 写回去（可复制链接）。
  if (tocNav) {
    tocNav.addEventListener('click', (event) => {
      const link = event.target.closest
        ? event.target.closest('a[data-target]') : null;
      if (!link) { return; }
      const el = document.getElementById(link.getAttribute('data-target'));
      if (!el) { return; }
      event.preventDefault();
      // 先滚动再动 hash：hash 更新在 file:// 下会抛，万一将来又漏接，
      // 也不能把滚动这件事一起带走。scrollIntoView 若不支持平滑滚动，用
      // 绝对位置兜底（84px = 吸顶栏高度 + 呼吸，与 CSS 的 scroll-margin-top 一致）。
      try {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } catch (err) {
        window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 84);
      }
      setHash('#' + el.id);
    });
  }

  // 点截图放大（900px 行宽里看不清 1500px 的界面截图）
  if (lightbox) {
    document.addEventListener('click', (event) => {
      const target = event.target;
      if (!target || target.tagName !== 'IMG'
          || !target.closest || !target.closest('.paper')) {
        return;
      }
      const big = document.createElement('img');
      big.src = target.src;
      big.alt = target.alt || '';
      lightbox.innerHTML = '';
      lightbox.appendChild(big);
      lightbox.classList.add('open');
    });
    lightbox.addEventListener('click', () => {
      lightbox.classList.remove('open');
      lightbox.innerHTML = '';
    });
  }

  if (toTop) {
    toTop.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  window.addEventListener('scroll', () => {
    if (toTop) { toTop.classList.toggle('show', window.scrollY > 420); }
    spy();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && lightbox) {
      lightbox.classList.remove('open');
      lightbox.innerHTML = '';
    }
  });

  const printBtn = document.getElementById('print-btn');
  if (printBtn) {
    printBtn.addEventListener('click', () => { window.print(); });
  }

  // 启动时定页签，优先级：显式 #tab-x 深链 > 上次看过的页签 > 默认（第一项）
  const deep = location.hash.match(/^#tab-(.+)$/);
  const remembered = recalledTab();
  if (deep && panelOf(deep[1])) {
    activate(deep[1]);
  } else if (remembered && panelOf(remembered)) {
    activate(remembered);
  } else {
    buildToc();
  }
})();
"""
