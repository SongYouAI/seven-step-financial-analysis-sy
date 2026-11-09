#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""七步财报分析 · HYDRO PAPER 皮肤报告生成器（数据驱动，离线自包含）。

沉淀自「长江电力 · 中国大水电 · 八维行业分析报告」的 HYDRO PAPER v3.0 视觉模板。
视觉资源拆成三层 CSS，全部随 skill 分发，不依赖 CDN：
  assets/hydro-base.css        只读基底（组件结构、布局、深色模式变量）
  assets/hydro-skin.css        HYDRO PAPER 皮肤（暖纸底 / 宋体大标题 / 蓝色等高线 / 单强调色）
  assets/sevenstep-adapt.css   七步专用适配层（chart-card / table / src-tag / 隔离框 / 色板）

三种输入模式：
  A. 数据驱动：  --data content.json
     content.json 描述 Hero、目录、执行摘要、9 步正文、附录、16 图脚本。可复用于任意公司。
  B. 链路衔接：  --data content.json --prefilled <report_prefilled.html>
     content.json 只写叙事，16 图脚本自动从 build_report_data.py 的预填产物抽取。
  C. 旧版换肤：  --from-html <旧成品.html> [--data overrides.json]
     从既有七步报告抽取 9 步正文 / 执行摘要 / 附录 / 16 图脚本，只换版式，数值零改动。

输出：<out> 指定的**自包含单文件 HTML**：三层 CSS、Chart.js 4.4.1、
chartjs-plugin-datalabels 2.2.0、两张二维码全部内联，零远程资源、零同目录依赖。
报告会被多级转发或单独复制，只要落下一个 HTML 就必须能看图（v2.1.2 起硬约束）。
默认仍在同级目录补齐 assets/（仅作旧流程兼容），--no-assets 可关闭。
默认调用 check_html.py 做交付门禁（含 P0-11 自包含校验），--no-check 可跳过。

用法示例：
  python3 render_report.py --data content.json --out 长飞光纤_七步财报分析报告.html
  python3 render_report.py --data content.json --prefilled 02_指标产出/report_prefilled.html --out report.html
  python3 render_report.py --from-html _backup_旧版.html --data overrides.json --out report.html
"""
import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ASSETS = SKILL / 'assets'
CHART_ASSETS = ('chart.umd.min.js', 'chartjs-plugin-datalabels.min.js')
BRAND_JSON = ASSETS / 'brand.json'

# §14.2 图表嵌入映射：图号 -> 所属步骤。第8步「八问商业模式」按规范无图。
# from_prefilled() 只抽 16 段 __reg 脚本，正文若不自带容器，P0-2 必然阻断；
# 这里给生成器一个默认兜底，标题可在 content.json 的 chart_captions 里覆盖。
DEFAULT_CHART_STEPS = {
    1: [(1, '营业收入与归母净利润趋势'), (2, '盈利质量四关系')],
    2: [(3, '毛利率与净利率趋势'), (4, '期间费用率趋势')],
    3: [(5, '营收与归母净利润增长率'), (6, '历史 CAGR 与一致预期 CAGR')],
    4: [(7, '收入结构变化趋势'), (8, '分业务板块毛利率趋势')],
    5: [(9, '资产结构变化'), (10, '资产负债率趋势'), (11, '1 元收入所需营运资本')],
    6: [(12, '人均收入与人均归母净利润')],
    7: [(13, 'ROE / ROA / ROIC 趋势'), (14, '杜邦三因素拆解'), (15, '总资产与存货周转天数')],
    8: [],
    9: [(16, '同行关键指标对比')],
}

# ---------------------------------------------------------------------------
# 静态骨架：全部来自 HYDRO PAPER v3.0 模板，禁止在此改颜色（改 CSS 文件）
# ---------------------------------------------------------------------------

HERO_ART = """<svg class="hero-art" viewBox="0 0 720 520" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
<circle class="ring" cx="540" cy="230" r="158"/><circle class="ring" cx="540" cy="230" r="98"/>
<path class="contour" d="M -40 460 C 140 448 220 430 330 404 S 520 352 780 336"/>
<path class="contour" d="M -40 424 C 140 412 220 396 330 368 S 520 314 780 298"/>
<path class="contour" d="M -40 388 C 140 376 220 360 330 332 S 520 276 780 260"/>
<path class="contour strong" d="M -40 352 C 140 340 220 324 330 296 S 520 238 780 222"/>
<path class="contour" d="M -40 316 C 140 304 220 288 330 260 S 520 200 780 184"/>
<path class="contour" d="M -40 280 C 140 268 220 252 330 224 S 520 162 780 146"/>
<path class="river" d="M -40 442 C 130 430 210 372 322 356 C 430 340 470 300 545 286 C 630 270 700 214 780 196"/>
<path class="river" d="M -40 408 C 130 402 210 392 322 388 C 430 384 470 366 545 362 C 630 358 700 350 780 348" opacity=".45"/>
<circle class="station" cx="322" cy="356" r="4"/><circle class="station" cx="545" cy="286" r="4"/><circle class="station" cx="700" cy="214" r="4"/>
<circle class="station" cx="322" cy="388" r="3"/><circle class="station" cx="545" cy="362" r="3"/><circle class="station" cx="700" cy="350" r="3"/>
<line class="tick" x1="540" y1="62" x2="540" y2="78"/><line class="tick" x1="540" y1="382" x2="540" y2="398"/>
<text class="art-label" x="60" y="478">__ART_FIRST__</text><text class="art-label" x="300" y="478">__ART_MID__</text>
<text class="art-label" x="600" y="478">__ART_LAST__</text><text class="art-label" x="360" y="62">REVENUE / NET PROFIT</text>
</svg>"""

# 通用图表渲染引导：年份由 report_data.json / content.json 注入，不含任何 CDN 兜底
BOOT = r"""/* ===== 图表渲染引导（离线自包含 · HYDRO PAPER） ===== */
(function(){
  function showChartError(msg){
    var el=document.getElementById('chart-error');
    if(el){ el.style.display='block'; if(msg) el.textContent=msg; }
  }
  window.__charts=[];
  window.__ready=false;
  function renderChart(id, config){
    try{
      var el=document.getElementById(id);
      if(!el){ console.warn('图表容器缺失: '+id); return; }
      var c=new Chart(el, config);
      if(!window.__chartInstances) window.__chartInstances={};
      window.__chartInstances[id]=c;
      var cb = el.parentNode && el.parentNode.classList && el.parentNode.classList.contains('chart-body') ? el.parentNode : null;
      if(cb) cb.classList.add('ready');
    }catch(e){
      console.error('图表渲染失败: '+id, e);
      var box=document.getElementById(id);
      if(box){ box.innerHTML='<div style="padding:24px;color:var(--p-risk);font-size:13px;">该图表数据异常，未能渲染（'+(e&&e.message?e.message:'未知错误')+'）</div>'; }
    }
  }
  window.__renderChart=renderChart;
  window.__reg=function(id,cfg){ window.__charts.push([id,cfg]); if(window.__ready) renderChart(id,cfg); };
  function boot(){
    if(typeof ChartDataLabels!=='undefined'){ Chart.register(ChartDataLabels); }
    Chart.defaults.font.family="'PingFang SC','Microsoft YaHei',sans-serif";
    var __dark = document.documentElement.getAttribute('data-theme')==='dark';
    Chart.defaults.color = __dark ? '#a7b0b3' : '#4f5a60';
    Chart.defaults.borderColor = __dark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.08)';
    if(Chart.defaults.scale) Chart.defaults.scale.grid.color = __dark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)';
    Chart.defaults.plugins.datalabels.color = __dark ? '#c3cbd0' : '#12181c';
    /* v2.1.5：默认 align:'center' + anchor:'end' 会把标签画进柱体内部，
       分组柱状图（图16）相邻标签因此互相压叠。统一移到柱顶外侧。 */
    Chart.defaults.plugins.datalabels.font.size=10;
    Chart.defaults.plugins.datalabels.font.weight=600;
    Chart.defaults.plugins.datalabels.anchor='end';
    Chart.defaults.plugins.datalabels.align='top';
    Chart.defaults.plugins.datalabels.offset=3;
    Chart.defaults.plugins.datalabels.clamp=false;
    if(!Chart.defaults.layout.padding || typeof Chart.defaults.layout.padding!=='object')
      Chart.defaults.layout.padding={};
    Chart.defaults.layout.padding.top=22;
    window.__years=__YEARS_JSON__;
    /* 语义修正：__yearStart=最旧年，__yearEnd=最新年（左新右旧数组的反直觉坑） */
    window.__yearStart=window.__years[window.__years.length-1];
    window.__yearEnd=window.__years[0];
    window.__yearSpan=window.__yearStart+'-'+window.__yearEnd;
    window.__yearSpanGrowth=(window.__years.length>1)
      ? window.__years[window.__years.length-2]+'-'+window.__years[0] : window.__yearSpan;
    window.__expSpan='__EXP_SPAN__';
    function __cv(v){ try{ return getComputedStyle(document.documentElement).getPropertyValue(v).trim()||'#000'; }catch(e){ return '#000'; } }
    window.__c={accent:__cv('--chart-1'),green:__cv('--chart-2'),red:__cv('--chart-3'),
                orange:__cv('--chart-4'),blue2:__cv('--chart-5'),teal:__cv('--chart-6')};
    window.__ready=true;
    window.__charts.forEach(function(x){ renderChart(x[0],x[1]); });
  }
  if(typeof Chart==='undefined'){
    showChartError('图表库未加载：本报告应自包含 Chart.js（v2.1.2+），请确认 HTML 未被截断，并用最新版 skill 重新生成。');
  } else { boot(); }
})();"""

TAIL = r"""<script>
(function(){
  var btn=document.getElementById('themeToggle');
  if(btn) btn.addEventListener('click',function(){
    var dark=document.documentElement.getAttribute('data-theme')!=='dark';
    document.documentElement.setAttribute('data-theme',dark?'dark':'light');
    try{localStorage.setItem('eightdim-theme',dark?'dark':'light');}catch(e){}
  });
  var nav=document.querySelector('.side-nav'),heroEl=document.querySelector('.hero');
  if(heroEl && nav && 'IntersectionObserver' in window){
    new IntersectionObserver(function(es){es.forEach(function(e){nav.classList.toggle('nav-hidden',e.isIntersecting);});},{threshold:0.12}).observe(heroEl);
  }
  var anchors=[];
  document.querySelectorAll('.step-card[id]').forEach(function(s){anchors.push(s.id);});
  if('IntersectionObserver' in window){
    anchors.forEach(function(id){var s=document.getElementById(id);if(!s)return;
      new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){
        document.querySelectorAll('.side-nav a').forEach(function(a){a.classList.toggle('active',a.getAttribute('href')==='#'+id);});
      }});},{rootMargin:'-20% 0px -70% 0px'}).observe(s);});
  }
  var prog=document.getElementById('topProgress');
  if(prog){window.addEventListener('scroll',function(){var h=document.documentElement;
    var d=(h.scrollHeight-h.clientHeight)||1;
    var p=Math.max(0,Math.min(100,(h.scrollTop||document.body.scrollTop)/d*100));
    prog.style.setProperty('--p',p.toFixed(1)+'%');},{passive:true});}
})();
</script>"""

THEME_INIT = ("try{var t=localStorage.getItem('eightdim-theme');"
              "if(t==='dark')document.documentElement.setAttribute('data-theme','dark');}catch(e){}")

EMOJI = {
    '\U0001F947': '<span class="src-tag a">公告</span>',
    '\U0001F948': '<span class="src-tag b">接口</span>',
    '\U0001F949': '<span class="src-tag c">旁证</span>',
    '\U0001F6AB': '<span class="src-tag x">未采用</span>',
    '⚠️': '注意：', '⚡ ': '', '📋 ': '', '✅': '', '☀️': '', '🌙': '',
}

STEP_TITLES = ['看营收数据', '看成本费用构成', '看增长', '看业务构成', '看资产负债',
               '看投入产出', '看收益率', '八问商业模式', '同行对比']
STEP_SHORT = ['看营收', '看成本费用', '看增长', '看业务构成', '看资产负债',
              '看投入产出', '看收益率', '八问商业模式', '同行对比']

DEFAULT = {
    'company': '', 'code': '', 'title_html': '', 'industry': '', 'as_of': '',
    'period': '', 'quarantine': '', 'tier': '', 'rating': '不出具（仅财报拆解）',
    'badge': '', 'subtitle': '', 'hero_note': '', 'summary_html': '',
    'exec_inner_html': '', 'appendix_html': '', 'footer_html': '',
    'steps': [], 'chart_scripts': [], 'years': [], 'exp_span': '最新A→E3三年复合',
    'masthead_no': 'FINANCIAL STATEMENT NOTE · NO. 01',
    'hero_overline': 'SEVEN-STEP ANALYSIS',
    # v2.1.4 来源可核查契约（对标八维 sources / sources_html / link_patches）
    'sources': {}, 'step_sources': [], 'source_meta': {},
    'link_patches': [], 'sources_html': '',
}


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


# ── 来源与角标（v2.1.4 · 移植自八维 render_report.py L74–108）──────────
def ref(sources, key):
    """可点击来源角标。图标用 ↗（U+2197）而非 🔗：后者在 P1-1 emoji 范围内。

    URL 与 title 必须转义；含 & 的查询参数不转成 &amp; 会截断 href 属性。
    """
    s = sources.get(key) if isinstance(sources, dict) else None
    if not s or not s.get('url'):
        return ''
    return ('<a class="ref" href="%s" target="_blank" rel="noopener" '
            'title="%s">↗</a>'
            % (esc(s['url']), esc(s.get('title') or key)))


def SRC(sources, key):
    s = sources.get(key, {}) if isinstance(sources, dict) else {}
    return esc(s.get('title') or key) + ' ' + ref(sources, key)


def apply_link_patches(frag, step_no, patches, sources):
    """给正文关键数字补来源角标（对标八维 link_patches）。

    八维历史事故：补链脚本命中 <script>/<style>/注释 或标签属性里的同名字串，
    会破坏 JS 语法与 HTML 结构。这里先整段 stash 受保护区域，再校验命中点
    落在标签外文本中，且后面没有已存在的角标。
    """
    todo = [p for p in (patches or []) if int(p.get('step') or 0) == step_no]
    if not todo:
        return frag
    keep = []

    def stash(m):
        keep.append(m.group(0))
        return '\x00%d\x00' % (len(keep) - 1)

    s = re.sub(r'<script\b.*?</script>|<!--.*?-->|<style\b.*?</style>',
               stash, frag, flags=re.S | re.I)
    for p in todo:
        needle, r = p.get('after'), ref(sources, p.get('src'))
        if not needle or not r:
            continue
        idx = s.find(needle)
        if idx < 0:
            continue
        lt, gt = s.rfind('<', 0, idx), s.rfind('>', 0, idx)
        if lt > gt:                       # 命中点落在标签属性内部
            continue
        if s[idx + len(needle):idx + len(needle) + 80].lstrip().startswith('<a class="ref"'):
            continue
        s = s[:idx + len(needle)] + r + s[idx + len(needle):]
    for i, block in enumerate(keep):
        s = s.replace('\x00%d\x00' % i, block)
    return s


def step_source_box(cfg, i):
    """每步末尾的来源框：来源名 + 可点击角标 + 状态徽章 + 汇总跳转。"""
    sources = cfg.get('sources') or {}
    ss = cfg.get('step_sources') or []
    keys = ss[i] if i < len(ss) else []
    if not keys:   # 未显式配置时按 sources[].step_refs 反查
        keys = [k for k, v in sources.items() if i + 1 in (v.get('step_refs') or [])]
    if not keys:
        return ''
    parts = []
    for k in keys:
        s = sources.get(k) or {}
        label = s.get('org') or s.get('title') or k
        parts.append('%s %s' % (esc(label), ref(sources, k) or
                                '<span class="src-offline">无公开链接</span>'))
    return ('<div class="source-box"><div class="sb-title">数据来源'
            '<span class="status-badge status-resolved">已验证</span></div>'
            '<p>%s</p><a href="#src-summary">↗ 核查来源汇总（六元组）</a></div>\n'
            % ' · '.join(parts))


def build_source_summary(cfg):
    """文末六元组来源汇总区；不用 .step-card，避免撞 P0-7 的 9 步硬编码。"""
    sources = cfg.get('sources') or {}
    meta = cfg.get('source_meta') or {}
    fetched = meta.get('fetched_at') or ''
    checked = meta.get('online_checked') or {}
    n_ok = sum(1 for v in checked.values() if v)
    n_all = len(checked) or 6
    rows = []
    for key, s in sources.items():
        link = (ref(sources, key) if s.get('url') else
                '<span class="src-offline">无公开链接</span>')
        rows.append(
            '<tr><td>%s</td><td>%s</td><td>%s<br><span class="src-org">%s · %s</span></td>'
            '<td>%s</td><td>%s</td><td>%s</td></tr>'
            % (esc(s.get('value') or '—'), esc(s.get('caliber') or '—'),
               esc(s.get('title') or key), esc(s.get('org') or '—'),
               esc(s.get('published_at') or '—'), link,
               esc(s.get('fetched_at') or fetched or '—'),
               esc(s.get('level') or 'L4')))
    if not rows:
        rows.append('<tr><td colspan="6">未登记来源</td></tr>')
    return (
        '<div id="src-summary" class="src-summary">\n'
        '<div id="source-meta" data-fetched-at="%s" data-tier="%s" '
        'data-online-checked="%d/%d"></div>\n'
        '<h3>数据来源汇总 · 六元组登记</h3>\n'
        '<p>本轮联网核实 %d/%d 类，抓取日期 %s。每条来源按「数值 / 口径 / 页面标题 / '
        '发布日期 / 可核查链接 / 抓取日期」登记；点击角标可跳转原始页面，'
        '按四级颗粒度抽查能否直接找到被引数字。验活只判链接能否打开，不判页面内容。</p>\n'
        '<div class="table-wrap table-scroll"><table class="src-table">'
        '<thead><tr><th>数值 / 用途</th><th>口径</th><th>页面标题 · 发布日期</th>'
        '<th>可核查链接</th><th>抓取日期</th><th>颗粒度</th></tr></thead>'
        '<tbody>%s</tbody></table></div>\n'
        '<p class="src-foot">六类必查：一致预期 / 行情估值时点 / 最新公告 / '
        '分红承诺 / 同行指标 / 行业口径。本地 output.csv 为主数据源，'
        '联网核实用于交叉复核与新鲜度校验，不替代原始表。</p>\n</div>\n'
        % (esc(fetched), esc(meta.get('tier') or cfg.get('tier') or ''),
           n_ok, n_all, n_ok, n_all, esc(fetched or '—'), ''.join(rows)))


def clean(s):
    """正文清洗：emoji → 文字徽章、表格滚动容器、裸图注 → .chart-card、隔离框。"""
    for k, v in EMOJI.items():
        s = s.replace(k, v)
    s = s.replace('<div class="page-break"></div>', '')
    # 旧正文里可能夹着错误提示条容器；生成器会统一输出一个，避免重复 id
    s = s.replace('<div id="chart-error"></div>', '')
    s = s.replace('class="table-scroll"', 'class="table-wrap table-scroll"')
    s = re.sub(r'<div class="source-box" style="[^"]*">',
               '<div class="source-box quarantine">', s)
    # 裸图注 + 裸画布 → 模板 .chart-card（图号徽章 + 卡片边框）
    pat = (r'<p style="font-size:12px;color:var\(--text-secondary\);margin:22px 0 6px;">'
           r'图(\d+)\s*·\s*([^<]+)</p>\s*'
           r'<div class="chart-body">(<canvas id="chart\d+"></canvas>)'
           r'<div class="chart-skeleton"></div></div>')

    def card(m):
        return ('<div class="chart-card"><div class="chart-head">'
                '<span class="chart-idx">FIG.' + m.group(1).zfill(2) + '</span>' +
                m.group(2).strip() + '</div>'
                '<div class="chart-body">' + m.group(3) +
                '<div class="chart-skeleton"></div></div></div>')

    s = re.sub(pat, card, s, flags=re.S)
    return s


def strip_tags(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s)).strip()


# ---------------------------------------------------------------------------
# 表格排版（v2.1.5）：内容感知列宽，根治中文表格被压成竖排
#
# 事故背景：正文表格是裸 <table> + 默认 table-layout:auto。中文可在任意字间
# 断行，浏览器把「年份 / 状态 / 事实」这类短列压到 1~2 字宽，出现「已/闭/环」
# 「分/红/承/诺」竖排；9 列数据表与 7 列六元组表则全部挤在 944px 正文宽度里。
# 只加滚动容器或 min-width 都无效：列宽仍由浏览器自由分配。必须显式给列宽。
# ---------------------------------------------------------------------------
TABLE_BLOCK_RE = re.compile(r'<table\b([^>]*)>(.*?)</table>', re.S | re.I)
CELL_RE = re.compile(r'<t[dh]\b([^>]*)>(.*?)</t[dh]>', re.S | re.I)
ROW_RE = re.compile(r'<tr\b[^>]*>(.*?)</tr>', re.S | re.I)
NUM_RE = re.compile(
    r'^[+\-−]?[\d,]+(?:\.\d+)?\s*'
    r'(?:[%％]|亿元|万元|亿股|万股|元|亿|万|pct|次|天|倍|x)?$')
# 下限 12 保证日期 / 徽章 / 年份列不被长文本列挤成竖排；上限 32 防止
# 单个超长「依据」列吃掉全部宽度（六元组表曾出现 27% vs 6% 的失衡）。
COL_W_MIN, COL_W_MAX = 12.0, 32.0
# v2.1.6：年份 / 期间首列专用权重。4 位年份只占 4 个视觉字符，通用下限 12
# 会把它撑到 140px（实测异常点表 142px），长文本「依据」列反而被挤窄。
COL_W_YEAR = 7.5
# 4~6 列的短表（典型：异常点三态闭环）年份列可以更紧；7 列以上宽表
# 列本身已很窄，年份列再压会与相邻数字列贴在一起。
COL_W_YEAR_NARROW = 6.2
YEAR_HEAD_RE = re.compile(r'^(年份|年度|期间|报告期|财年|时间|日期)')
YEAR_VAL_RE = re.compile(r'^(19|20)\d{2}(?:[—\-–~至]\s*(?:19|20)?\d{2,4})?$')
NUMISH_RE = re.compile(r'^[+\-−]?\d')
# ISO 日期是标签，不是数值：宽松的数值判定不能把「2026-11-09」列右对齐，
# 否则与相邻「↗」「L3」标签列的左对齐语义冲突。
ISO_DATE_RE = re.compile(r'^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$')
# 表头里的单位 / 口径括注必须整体换行，不能被拆成「财务费用(亿」+「元)」。
# 只包短括注（≤8 字符、不含斜杠），避免把「差异来源（模式 / 阶段 / 口径）」
# 这类长表头锁成不可断行而溢出。
UNIT_RE = re.compile(r'(\([^()<>/]{1,8}\)|（[^（）<>/]{1,8}）)')


def _visual_len(t):
    """CJK / 中文标点记 1，ASCII 记 0.55；用于估算列所需宽度。"""
    n = 0.0
    for ch in t:
        if ch.isspace():
            continue
        n += 0.55 if ord(ch) < 0x2E80 else 1.0
    return n


def _p75(vals):
    if not vals:
        return 0.0
    s = sorted(vals)
    return s[int((len(s) - 1) * 0.75)]


def _table_cols(inner):
    """返回 (列数, 每列视觉长度样本, 徽章列集合)。colspan 单元格不参与测量。"""
    rows = [CELL_RE.findall(r) for r in ROW_RE.findall(inner)]
    rows = [r for r in rows if r]
    if not rows:
        return 0, [], set()
    plain = [len(r) for r in rows
             if not any(re.search(r'colspan', a, re.I) for a, _ in r)]
    n = max(plain) if plain else len(rows[0])
    cols = [[] for _ in range(n)]
    badge = set()
    for r in rows:
        for i, (attrs, cell) in enumerate(r):
            if i >= n or re.search(r'colspan\s*=\s*["\x27]?[2-9]', attrs, re.I):
                continue
            cols[i].append(_visual_len(strip_tags(cell)))
            if 'src-tag' in cell or 'status-badge' in cell:
                badge.add(i)
    return n, cols, badge


def _year_column(inner, n):
    """识别「年份 / 期间」首列，返回 (列号, 最长值视觉长度)。

    表头匹配且 ≥60% 数据行是 4 位年份 / 年份区间才算。只认首列，避免把
    「2025A / 2026E」这类预测年份表头列误判成窄列。
    最长值用于动态权重：纯 4 位年份收窄到 COL_W_YEAR；含「2016—2017」
    区间的表自动放宽，否则 nowrap 会把单元格撑破（实测 1 处溢出）。
    """
    rows = [CELL_RE.findall(r) for r in ROW_RE.findall(inner)]
    rows = [r for r in rows if r]
    if not n or not rows or not rows[0]:
        return -1, 0.0
    if not YEAR_HEAD_RE.match(strip_tags(rows[0][0][1]).strip()):
        return -1, 0.0
    vals = [strip_tags(r[0][1]).strip() for r in rows[1:]
            if r and not re.search(r'colspan', r[0][0], re.I)]
    if vals and sum(1 for v in vals if YEAR_VAL_RE.match(v)) / len(vals) >= 0.6:
        return 0, max(_visual_len(v) for v in vals)
    return -1, 0.0


def _column_roles(inner, n):
    """**整列**判定数值列（v2.1.6）。

    v2.1.5 是逐单元格判定：同一列里「862.42↗」带角标不算数字 → 左对齐，
    「844.92」算数字 → 右对齐；表头 <th> 更是完全没打类，一律左对齐。
    结果 31/31 张表同列混排、表头与数据中心最大偏移 165px。
    这里改为按列统计：≥50% 数据单元格是数值（或短数值串，如
    「+2.07% / +6.18%」「12.1 元 / 2954 亿」）→ 整列（含表头）都是数值列。
    """
    rows = [CELL_RE.findall(r) for r in ROW_RE.findall(inner)]
    rows = [r for r in rows if r]
    body = rows[1:] if len(rows) > 1 else []
    texts = [[] for _ in range(n)]
    for r in body:
        for i, (attrs, cell) in enumerate(r):
            if i >= n or re.search(r'colspan', attrs, re.I):
                continue
            texts[i].append(strip_tags(cell).strip())
    num_cols = set()
    for i, vals in enumerate(texts):
        if not vals:
            continue
        hits = 0
        for t in vals:
            t = t.replace('↗', '').strip()
            if not t or ISO_DATE_RE.match(t):
                continue
            if (NUM_RE.match(t)
                    or (NUMISH_RE.match(t) and _visual_len(t) <= 22)):
                hits += 1
        if hits / len(vals) >= 0.5:
            num_cols.add(i)
    return num_cols


def _col_pct(cols, badge, year_col=-1, year_len=0.0):
    """列权重 → 百分比宽度。短列保底、长列封顶、徽章列额外加权。"""
    w = []
    for i, vals in enumerate(cols):
        if i == year_col:
            # 纯 4 位年份 → 窄权重；年份区间 → 按最长值放宽但不超过通用下限 12
            base = COL_W_YEAR if len(cols) >= 7 else COL_W_YEAR_NARROW
            w.append(max(base, min(COL_W_MIN, year_len * 2.0)))
            continue
        # 行数少（异常点表常见 4~5 行）时 p75 会退化为最小值，长文本列被
        # 压回下限 → 依据列反而拿不到宽度。用 max*0.6 托底，仍由上限封顶。
        v = min(max(_p75(vals), max(vals) * 0.8 if vals else 0,
                    COL_W_MIN), COL_W_MAX)
        if i in badge:
            v += 3.0
        w.append(v)
    total = sum(w) or 1.0
    pct = [x * 100.0 / total for x in w]
    pct[-1] = round(100.0 - sum(pct[:-1]), 4)      # 合计精确 100%
    return w, [round(x, 4) for x in pct[:-1]] + [pct[-1]]


def _mark_cells(inner, n, cols, badge, num_cols, year_col=-1):
    """按**列**给 th + td 打同一组语义 class，供 CSS 统一对齐与换行。

    v2.1.6 关键：表头 <th> 必须与同列 <td> 拿到相同的 num / cell-key /
    cell-year 类，否则「表头左对齐 + 数据右对齐」必然错位。
    """
    # 只有「整列最长单元格 ≤7 视觉字符」才允许 nowrap（空白字符不计长度）。
    # 阈值 12 / 8 都会把「+2.07% / +6.18%」（视觉长度 7.15）或
    # 「本轮 14.18 元 / 3468.6 亿」锁成不换行并撑破 108px 的数字列。
    tight = {i for i, vals in enumerate(cols)
             if vals and max(vals) <= 7.0}

    def row_repl(rm):
        idx = [0]

        def cell_repl(cm):
            i = idx[0]
            idx[0] += 1
            attrs, cell, whole = cm.group(1), cm.group(2), cm.group(0)
            if i >= n or re.search(r'colspan', attrs, re.I):
                return whole
            cls = []
            if i == 0:
                cls.append('cell-key')
            if i == year_col:
                cls.append('cell-year')
            if i in num_cols:
                cls.append('num')
            if i in tight:
                cls.append('cell-tight')
            if i in badge:
                cls.append('cell-status')
            if not cls:
                return whole
            mcls = re.search(r'class="([^"]*)"', attrs)
            if mcls:
                attrs = (attrs[:mcls.start()] + 'class="%s %s"' %
                         (mcls.group(1), ' '.join(cls)) + attrs[mcls.end():])
            else:
                attrs += ' class="%s"' % ' '.join(cls)
            is_td = whole.lower().startswith('<td')
            if not is_td:
                cell = UNIT_RE.sub(r'<span class="unit">\1</span>', cell)
            tag = 'td' if is_td else 'th'
            return '<%s%s>%s</%s>' % (tag, attrs, cell, tag)

        return CELL_RE.sub(cell_repl, rm.group(0))

    return ROW_RE.sub(row_repl, inner)


def enhance_tables(frag):
    """统一增强正文所有表格：列宽受控 + 语义标记 + 滚动容器。

    幂等：已有 data-table 的表格保持原样，只重新统一包裹一层容器。
    script / style / 注释先暂存，避免补链类事故（八维历史事故）。
    """
    keep = []

    def stash(m):
        keep.append(m.group(0))
        return '\x00T%d\x00' % (len(keep) - 1)

    s = re.sub(r'<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->',
               stash, frag, flags=re.S | re.I)
    # 先拆掉旧包裹，避免重复嵌套；div 内只有 table 时才拆（src-summary / 正文均如此）
    s = re.sub(r'<div class="table-wrap table-scroll">\s*(<table\b.*?</table>)\s*</div>',
               r'\1', s, flags=re.S | re.I)
    s = re.sub(r'<div class="table-scroll">\s*(<table\b.*?</table>)\s*</div>',
               r'\1', s, flags=re.S | re.I)

    def repl(m):
        attrs, inner = m.group(1), m.group(2)
        mcls = re.search(r'class="([^"]*)"', attrs)
        old_cls = mcls.group(1) if mcls else ''
        if 'data-table' in old_cls:            # 幂等：已增强过
            return ('<div class="table-wrap table-scroll">' + m.group(0) + '</div>')
        n, cols, badge = _table_cols(inner)
        if not n:
            return m.group(0)
        year_col, year_len = _year_column(inner, n)
        num_cols = _column_roles(inner, n)
        w, pct = _col_pct(cols, badge, year_col, year_len)
        head_txt = ' '.join(strip_tags(c) for _, c in
                            (CELL_RE.findall(ROW_RE.findall(inner)[0])
                             if ROW_RE.findall(inner) else []))
        kind = ('table-anomaly' if '异常点' in head_txt else
                'table-wide' if n >= 7 else 'table-data')
        cls = (old_cls + ' data-table ' + kind).strip()
        if mcls:
            attrs = attrs[:mcls.start()] + 'class="%s"' % cls + attrs[mcls.end():]
        else:
            attrs = ' class="%s"' % cls + attrs
        # v2.1.6：宽表不再被横向裁掉半列。旧系数 (7×权重 + 32×列数) 把
        # 9 列成本费用表撑到 1012px、7 列历史数字表撑到 922px，在 862px
        # 正文里末列只露出 1~2 个字，看起来就像「没对齐 / 表格残缺」。
        # 收紧到 (6×权重 + 24×列数)：9 列 ≈836px 可完整显示；只有超长
        # 文本六元组表（6 列 ≈936px）仍保留横向滚动，避免长文本被压成 5 行。
        min_w = int(max(680, sum(w) * 6 + n * 24))
        ms = re.search(r'style="([^"]*)"', attrs)
        style = 'min-width:%dpx;' % min_w
        if ms:
            attrs = (attrs[:ms.start()] + 'style="%s%s"' %
                     (ms.group(1).rstrip(';') + ';' if ms.group(1) else '', style)
                     + attrs[ms.end():])
        else:
            attrs += ' style="%s"' % style
        colgroup = ('<colgroup>' + ''.join(
            '<col style="width:%s%%">' % ('%g' % p) for p in pct) + '</colgroup>')
        out = '<table%s>%s%s</table>' % (
            attrs, colgroup,
            _mark_cells(inner, n, cols, badge, num_cols, year_col))
        return '<div class="table-wrap table-scroll">' + out + '</div>'

    s = TABLE_BLOCK_RE.sub(repl, s)
    for i, block in enumerate(keep):
        s = s.replace('\x00T%d\x00' % i, block)
    return s


def load_css():
    out = {}
    for name in ('hydro-base.css', 'hydro-skin.css', 'sevenstep-adapt.css'):
        p = ASSETS / name
        if not p.exists():
            sys.exit('❌ 皮肤资产缺失: %s' % p)
        out[name] = p.read_text(encoding='utf-8').strip()
    return out


def read_json(path):
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        sys.exit('❌ 文件不存在: %s' % p)
    return json.loads(p.read_text(encoding='utf-8-sig'))


# ---------------------------------------------------------------------------
# 从既有 HTML 抽取内容（模式 C）
# ---------------------------------------------------------------------------
def cut_at_close(s):
    """从某个 div 内部起点出发，截到其闭合 </div> 之前（按标签深度，不靠正则贪婪）。"""
    depth = 0
    for m in re.finditer(r'<div\b|</div>', s):
        depth += 1 if m.group(0).startswith('<div') else -1
        if depth < 0:
            return s[:m.start()]
    return s


def from_html(path, cfg):
    t = Path(path).read_text(encoding='utf-8')
    b = t[t.index('<body'):]

    # 16 图脚本
    regs = re.findall(r"<script>window\.__reg\('chart\d+',.*?</script>", b, re.S)
    if regs:
        cfg['chart_scripts'] = regs

    # 年份轴
    m = re.search(r'window\.__years=(\[[^\]]+\])', b)
    if m and not cfg.get('years'):
        try:
            cfg['years'] = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 9 步正文：兼容 <section id="stepN">（旧版）与 <div class="step-card" id="stepN">（HYDRO 版）
    secs = re.findall(r'<section id="step(\d+)"[^>]*>(.*?)</section>', b, re.S)
    if len(secs) != 9:
        marks = list(re.finditer(r'<div class="step-card" id="step(\d+)"[^>]*>', b))
        secs = []
        for i, mk in enumerate(marks):
            e = marks[i + 1].start() if i + 1 < len(marks) else b.find('<script', mk.end())
            inner = b[mk.end():e if e > mk.end() else len(b)]
            bi = inner.find('<div class="step-body">')
            if bi >= 0:
                inner = cut_at_close(inner[bi + len('<div class="step-body">'):])
            secs.append((mk.group(1), inner))
    if len(secs) == 9:
        steps = []
        subs = cfg.get('step_subs') or []
        tocs = cfg.get('step_tocs') or []
        for idx, (num, inner) in enumerate(secs):
            body = inner.strip()
            if body.startswith('<div class="step-body">'):
                body = body[len('<div class="step-body">'):]
                if body.endswith('</div>'):
                    body = body[:-len('</div>')]
            hm = re.search(r'<h2[^>]*>(.*?)</h2>', body, re.S)
            title = strip_tags(hm.group(1)) if hm else ''
            short = re.sub(r'^第\d+步[：:]', '', title).split('（')[0]
            if hm:
                body = body.replace(hm.group(0), '', 1)
            # HYDRO 版已经包过 .chart-card / 转过文字徽章，clean() 幂等
            steps.append({'title': short or STEP_TITLES[int(num) - 1],
                          'sub': subs[idx] if idx < len(subs) else '',
                          'toc': tocs[idx] if idx < len(tocs) else '',
                          'html': clean(body.strip())})
        cfg['steps'] = steps

    # 执行摘要内层（KPI / 来源 / 警示）
    if '<div class="exec-summary">' in b:
        i = b.index('<div class="exec-summary">')
        j = b.find('<!-- 第1步 -->', i)
        if j < 0:
            j = b.find('id="step1"', i)
        blk = b[i:j]
        inner = blk[blk.index('>') + 1:]
        if '</div>' in inner:
            inner = inner[:inner.rindex('</div>')]
        inner = re.sub(r'<h2[^>]*>.*?</h2>', '', inner, count=1, flags=re.S)
        # 摘要段由 content.json 的 summary_html 统一提供；旧成品 exec 区里已有的
        # 裸 <p> 摘要必须剔除，否则换肤后同一段话会输出两遍。
        if cfg.get('summary_html'):
            inner = re.sub(r'^\s*(?:<p\b[^>]*>.*?</p>\s*)+', '', inner, count=1, flags=re.S)
        cfg['exec_inner_html'] = clean(inner)

    # 附录：兼容旧版 <!-- 附录 --> 注释块 与 HYDRO 版 <div class="step-card" id="appendix">
    k = b.find('<!-- 附录 -->')
    if k >= 0:
        e = b.find('<!-- Chart.js 图表脚本 -->', k)
        app = b[k:e if e > k else len(b)]
    else:
        k = b.find('<div class="step-card" id="appendix"')
        if k >= 0:
            e = b.find('<script', k)
            app = b[k:e if e > k else len(b)]
            bi = app.find('<div class="step-body">')
            if bi >= 0:
                app = cut_at_close(app[bi + len('<div class="step-body">'):])
        else:
            app = ''
    if app:
        app = re.sub(r'<div class="appendix-wrap"[^>]*>', '', app, count=1)
        app = re.sub(r'<h2[^>]*>.*?</h2>', '', app, count=1, flags=re.S)
        fm = re.search(r'<div class="report-footer">.*?</div>', app, re.S)
        if fm:
            cfg['footer_html'] = clean(fm.group(0))
            app = app.replace(fm.group(0), '')
        app = app.strip()
        if app.endswith('</div>'):
            app = app[:-len('</div>')]
        cfg['appendix_html'] = clean(app)
    return cfg


def from_prefilled(path, cfg):
    if not Path(path).exists():
        sys.exit('❌ 预填模板不存在: %s（请先跑 build_report_data.py 产出 report_prefilled.html）' % path)
    t = Path(path).read_text(encoding='utf-8')
    regs = re.findall(r"<script>window\.__reg\('chart\d+',.*?</script>", t, re.S)
    if regs:
        cfg['chart_scripts'] = regs
    if not cfg.get('years'):
        m = re.search(r'window\.__years=(\[[^\]]+\])', t)
        if m:
            try:
                cfg['years'] = json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    return cfg


def chart_card(num, caption):
    """输出完整 .chart-card（不经 clean() 包装正则，避免重复包卡）。"""
    return ('<div class="chart-card"><div class="chart-head">'
            '<span class="chart-idx">FIG.%02d</span>%s</div>'
            '<div class="chart-body"><canvas id="chart%d"></canvas>'
            '<div class="chart-skeleton"></div></div></div>'
            % (num, esc(caption), num))


def inject_chart_containers(cfg):
    """幂等补齐 16 个 canvas / chart-card 容器（v2.1.3）。

    正文已自带容器时零改动；只在某图缺容器时把标准卡片追加到所属步骤末尾。
    content.json 可用 chart_captions: {"7": "自定义标题"} 覆盖默认标题。
    """
    steps = cfg.get('steps') or []
    if len(steps) != 9:
        return cfg
    overrides = cfg.get('chart_captions') or {}
    all_html = '\n'.join(str(s.get('html') or '') for s in steps)
    present = set(re.findall(r'<canvas[^>]*\bid="(chart\d+)"', all_html))
    added = 0
    for step_no, specs in DEFAULT_CHART_STEPS.items():
        missing = [(n, overrides.get(str(n)) or c) for n, c in specs
                   if 'chart%d' % n not in present]
        if missing:
            steps[step_no - 1]['html'] = (str(steps[step_no - 1].get('html') or '') +
                '\n' + '\n'.join(chart_card(n, c) for n, c in missing))
            added += len(missing)
    if added:
        print('  ↳ 自动补齐图表容器 %d 个（§14.2 映射，正文未自带）' % added)
    return cfg


# ---------------------------------------------------------------------------
# 组装
# ---------------------------------------------------------------------------
def build_head(cfg, css):
    title = cfg.get('title_html') or (cfg.get('company', '') + ' 七步财报分析报告')
    title_plain = strip_tags(title)
    return (
        '<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<title>' + title_plain + '</title>\n'
        '<script>' + THEME_INIT + '</script>\n'
        '<style id="hydro-base">\n' + css['hydro-base.css'] + '\n</style>\n'
        '<style id="hydro-skin" data-design="HYDRO PAPER v3.0">\n' + css['hydro-skin.css'] + '\n</style>\n'
        '<style id="sevenstep-adapt">\n' + css['sevenstep-adapt.css'] + '\n</style>\n'
        '</head>'
    )


def build_header(cfg):
    years = cfg.get('years') or []
    art = (HERO_ART.replace('__ART_FIRST__', esc(years[-1] if years else 'START'))
                   .replace('__ART_MID__', esc(years[len(years) // 2] if years else 'MID'))
                   .replace('__ART_LAST__', esc(years[0] if years else 'END')))
    steps = cfg['steps']
    side = ''.join('<a href="#step%d">第%d步 · %s</a>' % (i + 1, i + 1,
                   esc(s.get('short') or STEP_SHORT[i])) for i, s in enumerate(steps))
    side += '<a href="#appendix">附录 · 数据来源</a>\n<a href="#src-summary">来源汇总 · 六元组</a>'
    overline = esc(cfg.get('hero_overline') or 'SEVEN-STEP ANALYSIS')
    if cfg.get('industry'):
        overline += ' / ' + esc(cfg['industry'])
    meta = [
        ('分析期间', cfg.get('period', '')),
        ('隔离区', cfg.get('quarantine', '')),
        ('数据档位', cfg.get('tier', '')),
        ('投资评级', cfg.get('rating', '')),
    ]
    meta_html = ''.join('<div class="mt"><span class="mt-l">%s</span>'
                        '<span class="mt-v">%s</span></div>' % (esc(k), esc(v))
                        for k, v in meta)
    return (
        '<button id="themeToggle" class="theme-toggle" aria-label="切换深色/亮色模式" title="切换深色模式"></button>\n'
        '<aside class="side-nav nav-hidden" aria-label="报告章节导航">\n'
        '<div class="sn-title">报告导航 · 七步</div>\n' + side + '\n</aside>\n'
        '<div class="top-progress" id="topProgress"></div>\n'
        '<header class="hero">\n' + art + '\n'
        '<div class="hero-content">\n'
        '<div class="hero-masthead"><span class="mh-left">' + esc(cfg.get('masthead_no', '')) +
        '</span><span>数据截至 ' + esc(cfg.get('as_of', '')) + '</span></div>\n'
        '<div class="hero-overline">' + overline + '</div>\n'
        '<h1 data-note="01">' + (cfg.get('title_html') or esc(cfg.get('company', ''))) + '</h1>\n'
        '<div class="badge">' + esc(cfg.get('badge', '')) + '</div>\n'
        '<p class="subtitle">' + cfg.get('subtitle', '') + '</p>\n'
        '<div class="meta-row">\n' + meta_html + '\n</div>\n'
        '<div class="hero-foot"><span>SCROLL TO EXPLORE · 10 SECTIONS / 16 CHARTS</span>'
        '<span class="hero-note">' + esc(cfg.get('hero_note', '')) + '</span>'
        '<span class="scroll-line"></span></div>\n'
        '</div>\n</header>\n'
    )


def build_toc(cfg):
    items = []
    for i, s in enumerate(cfg['steps']):
        items.append(
            '<div class="toc-item" onclick="document.getElementById(\'step%d\').scrollIntoView({behavior:\'smooth\'})">'
            '<span class="toc-num">%02d</span><div><span class="toc-t">第%d步 · %s</span>'
            '<span class="toc-d">%s</span></div></div>'
            % (i + 1, i + 1, i + 1, esc(s.get('title') or STEP_TITLES[i]), esc(s.get('toc', ''))))
    items.append(
        '<div class="toc-item" onclick="document.getElementById(\'appendix\').scrollIntoView({behavior:\'smooth\'})">'
        '<span class="toc-num">10</span><div><span class="toc-t">附录 · 数据来源与校验</span>'
        '<span class="toc-d">六元组来源汇总、缺口、免责声明</span></div></div>')
    return ('<div class="toc-card"><div class="toc-title">报告导航 · 点击跳转</div>'
            '<div class="toc-grid">' + ''.join(items) + '</div></div>')


def build_steps(cfg):
    out = []
    for i, s in enumerate(cfg['steps']):
        num = str(i + 1)
        sub = s.get('sub') or ''
        body = clean(s.get('html', ''))
        body = apply_link_patches(body, i + 1, cfg.get('link_patches'),
                                  cfg.get('sources') or {})
        out.append(
            '<div class="step-card" id="step' + num + '">\n'
            '<div class="step-head"><div class="step-num-watermark">' + num.zfill(2) + '</div>\n'
            '<div class="step-head-text"><div class="step-num">STEP ' + num.zfill(2) + ' / 09</div>\n'
            '<div class="step-title">' + esc(s.get('title') or STEP_TITLES[i]) + '</div>'
            '<div class="step-sub">' + esc(sub) + '</div></div></div>\n'
            '<div class="step-body">' + body + step_source_box(cfg, i) +
            '</div>\n</div>\n')
    return ''.join(out)


# ---------------------------------------------------------------------------
# 页脚 brand 溯源条（v2.1.0 · 移植自八维 HYDRO PAPER v3.2.2）
# ---------------------------------------------------------------------------
# 报告会被多级转发，页脚是唯一稳定的出处锚点。品牌常量集中在 assets/brand.json，
# 二维码以 data URI 内嵌：离线打开 / 打印 / SkillHub 纯文本分发都不丢图。
# 本块强制输出，content.json 不能关闭或覆盖（check_html.py P0-9 反向复核）。
# 与八维版差异：品牌块不挂外链；来源外链统一走 sources 契约（v2.1.4
# P0-3 白名单仅放行 <a class="ref" target="_blank" rel="noopener">），
# 避免品牌导流链接与可核查来源角标混在一起。
DEFAULT_ATTRIBUTION = '七步财报分析法 · 松幽'


def load_brand():
    if not BRAND_JSON.exists():
        sys.exit('❌ 品牌资源缺失: %s' % BRAND_JSON)
    b = json.loads(BRAND_JSON.read_text(encoding='utf-8'))
    for key in ('wechat', 'video', 'qr_wechat', 'qr_video'):
        if not b.get(key):
            sys.exit('❌ assets/brand.json 缺少必填字段 %s' % key)
    return b


def qr_data_uri(filename, brand):
    """二维码 data URI：优先 brand.json 内嵌 base64，回退读同目录 PNG 源图。"""
    field = 'qr_wechat_data' if filename == brand.get('qr_wechat') else 'qr_video_data'
    b64 = brand.get(field)
    if not b64:
        p = ASSETS / filename
        if not p.exists():
            sys.exit('❌ 二维码源图缺失且 brand.json 无内嵌数据: %s' % p)
        b64 = base64.b64encode(p.read_bytes()).decode('ascii')
    if not isinstance(b64, str) or not re.fullmatch(r'[A-Za-z0-9+/=]+', b64):
        sys.exit('❌ %s 不是合法 base64，拒绝写入 HTML' % field)
    return 'data:image/png;base64,' + b64


# 点击小码放大：复用同一份 base64，不重复内嵌图片；ESC / 点遮罩关闭。
QR_LIGHTBOX_JS = """<script>
(function(){
  var box=document.getElementById('qrLightbox');
  if(!box) return;
  var big=box.querySelector('img');
  document.addEventListener('click',function(e){
    var btn=e.target.closest && e.target.closest('.brand-qr');
    if(!btn) return;
    e.preventDefault();
    big.src=btn.querySelector('img').src;
    big.alt=btn.querySelector('img').alt;
    box.hidden=false;
  });
  box.addEventListener('click',function(){box.hidden=true;});
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape') box.hidden=true;
  });
})();
</script>"""


def render_brand_footer(cfg):
    """强制输出紧凑溯源条：公众号 / 视频号各一行，小码点击放大。

    旧成品 --from-html 抽出的 footer_html 若只是默认单行署名，不再重复渲染；
    用户自定义且不含 report-footer 包装、不含免责声明的纯文本则作为附注保留。
    """
    b = load_brand()
    hint = esc(b.get('hint', '点击二维码查看大图'))
    rows = []
    for kind, name, filename in (('公众号', b['wechat'], b['qr_wechat']),
                                 ('视频号', b['video'], b['qr_video'])):
        uri = qr_data_uri(filename, b)
        rows.append(
            '<div class="brand-channel">'
            '<div class="brand-channel-copy">'
            '<p class="brand-channel-name">%s「%s」</p>'
            '<p class="brand-channel-hint">%s</p>'
            '</div>'
            '<button class="brand-qr" type="button" aria-label="放大%s「%s」二维码">'
            '<img src="%s" alt="%s「%s」二维码">'
            '</button>'
            '</div>' % (esc(kind), esc(name), hint, esc(kind), esc(name),
                        uri, esc(kind), esc(name)))
    meta = ['<p class="brand-meta">',
            '<span class="brand-note">%s</span>' % esc(b.get('note', '')),
            '<span class="brand-note">本报告只做财报拆解，不构成投资建议</span>']
    extra = (cfg.get('footer_html') or '').strip()
    if extra and 'report-footer' not in extra and '不构成投资建议' not in extra:
        txt = strip_tags(extra)
        if txt:
            meta.append('<span class="brand-note">%s</span>' % esc(txt))
    meta.append('<span class="report-attribution">分析框架：%s</span>'
                % esc(b.get('method') or DEFAULT_ATTRIBUTION))
    meta.append('</p>')
    return '\n'.join([
        '<footer class="report-footer">',
        '<div class="brand-block">',
        '<p class="brand-head"><span class="brand-kicker">%s</span>'
        '<span class="brand-title">%s</span></p>'
        % (esc(b.get('kicker', '原创出品 · 欢迎溯源')), esc(b.get('title', ''))),
        '<div class="brand-channels">', '\n'.join(rows), '</div>',
        '\n'.join(meta),
        '</div>',
        '<div class="qr-lightbox" id="qrLightbox" hidden><img alt="二维码大图"></div>',
        '</footer>',
    ]) + '\n'


def build_appendix(cfg):
    app = ('<div class="step-card" id="appendix">\n'
           '<div class="step-head"><div class="step-num-watermark">10</div>\n'
           '<div class="step-head-text"><div class="step-num">APPENDIX / 10</div>\n'
           '<div class="step-title">附录 · 数据口径与校验记录</div>'
           '<div class="step-sub">DATA PROVENANCE · 原始表、缺口与免责声明</div></div></div>\n'
           '<div class="step-body">' + clean(cfg.get('appendix_html', '')) +
           (cfg.get('sources_html') or build_source_summary(cfg)) +
           '\n</div>\n</div>\n')
    # brand 溯源条由 build() 单独挂在 </div.main-wrap> 之后，不随附录进主容器。
    # 原因：.main-wrap 与 .report-footer 各自带 padding-left:248px（宽屏给侧栏让位），
    # 若 footer 嵌在 main-wrap 内，248px 会叠加两次，页脚相对正文右移 248px。
    # 八维 HYDRO PAPER 模板的 footer 是 <body> 直接子元素，此处保持同一 DOM 契约（P0-10）。
    return app


def normalize_chart_colors(scripts):
    """把旧模板硬编码色值统一到 HYDRO 单强调色板（只改配色，不动数据）。"""
    pairs = [
        ("'rgba(30,95,180,0.5)'", "'#2a4bd7'"), ("'#1e5fb4'", "'#2a4bd7'"),
        ("'rgba(183,28,28,0.3)'", "'#c0442c'"), ("'#b71c1c'", "'#c0442c'"),
        ("'rgba(200,148,59,0.4)'", "'#b7852a'"), ("'#c8943b'", "'#b7852a'"),
        ("'#2e8b57'", "'#12684a'"), ("'#4682b4'", "'#7f96a6'"),
        ("'#4a5468'", "'#4f5a60'"), ("'#1a1a2e'", "'#12181c'"),
        ('⚠️ 图表库未加载', '图表库未加载'), ('⚠️ 该图表数据异常', '该图表数据异常'),
    ]
    out = []
    for s in scripts:
        for a, b in pairs:
            s = s.replace(a, b)
        out.append(s)
    return out


def inline_lib(name):
    """把 skill 自带的图表库整段内联进 HTML（v2.1.2 · 自包含硬约束）。

    v2.1.1 及以前用 <script src="assets/...">，报告一旦被单独复制/转发就全图空白
    （typeof Chart === 'undefined'，16 张 canvas 只留空框）。报告是可多级转发的
    交付物，不能依赖同目录资源，故改为内联固定版本，零远程、零同目录依赖。
    """
    src = ASSETS / name
    if not src.is_file():
        sys.exit('❌ 本地图表库缺失: %s' % src)
    code = src.read_text(encoding='utf-8')
    n = len(code.encode('utf-8'))
    if n < 10000:
        sys.exit('❌ %s 体积异常（%d bytes），拒绝内联' % (name, n))
    for bad in ('</script', '<!--', '<script'):
        if bad in code.lower():
            sys.exit('❌ %s 含 %s 字面串，内联会截断 HTML 文档' % (name, bad))
    return ('<!-- %s (inlined, %d bytes) -->\n<script>\n%s\n</script>\n'
            % (name, n, code.rstrip()))


def harden_null_formatters(scripts):
    """把 16 图的数据标签 formatter 改成 null 安全（v2.1.2 · P0-12）。

    build_report_data.py 的设计原则是「缺数据填 null 让图表自动断点，不编造」，
    但旧的 formatter 直接 `v.toFixed(1)+'%'`：Chart.js 的 datalabels 仍会为 null
    数据点调用 formatter，抛 `TypeError: Cannot read properties of null`，
    **整张图渲染失败**（实测 A 股 ONLINE 无一致预期时图6 全白）。
    这里只加固 16 段图脚本，不触碰内联的 Chart.js 库内部 formatter。
    """
    guard = "(v===null||v===undefined||isNaN(v))?'':"
    out = []
    for s in scripts or []:
        # 形式1: formatter:v=>v.toFixed(N)+'单位'
        s = re.sub(
            r"formatter\s*:\s*v\s*=>\s*v\.toFixed\((\d+)\)\s*\+\s*('[^']*')",
            lambda m: 'formatter:v=>' + guard + 'Number(v).toFixed(%s)+%s'
                      % (m.group(1), m.group(2)), s)
        # 形式2: formatter:function(v){return v.toFixed(N)+'单位';}
        s = re.sub(
            r"formatter\s*:\s*function\s*\(\s*v\s*\)\s*\{\s*return\s+v\.toFixed\((\d+)\)\s*\+\s*('[^']*')\s*;\s*\}",
            lambda m: 'formatter:function(v){return ' + guard
                      + 'Number(v).toFixed(%s)+%s;}' % (m.group(1), m.group(2)), s)
        # 形式3: formatter:(v,i)=>[v+'%',v+'次',v+'x'][i]（图14 多单位）
        s = re.sub(
            r"formatter\s*:\s*\(\s*v\s*,\s*i\s*\)\s*=>\s*(\[[^\]]*\]\s*\[\s*i\s*\])",
            lambda m: 'formatter:(v,i)=>' + guard + '(%s)' % m.group(1), s)
        # 形式4—6: Y 轴 ticks.callback。旧模板的 v+'%' / v.toFixed() 在
        # Chart.js 传入 null / undefined tick 时会显示 'null%' 或抛 TypeError。
        s = re.sub(
            r"callback\s*:\s*v\s*=>\s*Number\(v\.toFixed\((\d+)\)\)\s*\+\s*('[^']*')",
            lambda m: 'callback:v=>' + guard + 'Number(v).toFixed(%s)+%s'
                      % (m.group(1), m.group(2)), s)
        s = re.sub(
            r"callback\s*:\s*v\s*=>\s*v\+\s*('[^']*')",
            lambda m: 'callback:v=>' + guard + 'Number(v).toFixed(1)+' + m.group(1), s)
        s = re.sub(
            r"callback\s*:\s*function\s*\(\s*v\s*\)\s*\{\s*return\s+v\+\s*('[^']*')\s*;\s*\}",
            lambda m: 'callback:function(v){return ' + guard
                      + 'Number(v).toFixed(1)+' + m.group(1) + ';}', s)
        out.append(s)
    return out


def relax_bar_headroom(scripts):
    """柱状图 y 轴顶部留白（v2.1.5）。

    标签移到柱顶外侧后，若 y 轴自动 max 正好贴住最高柱（图16 的 291.13%
    对应 300% 顶格），标签会被裁掉。grace 只加在没有显式 max 的图上，
    不改动任何数值、不新增数据点，且不触碰 null 安全的 formatter。
    """
    out = []
    for s in scripts or []:
        compact = s.replace(' ', '')
        if (("type:'bar'" in compact or 'type:"bar"' in compact)
                and 'max:' not in s and 'grace' not in s):
            s = re.sub(r'(scales\s*:\s*\{\s*y\s*:\s*\{)',
                       lambda m: m.group(1) + "grace:'12%',", s, count=1)
        out.append(s)
    return out


def build_scripts(cfg):
    years = cfg.get('years') or []
    boot = (BOOT.replace('__YEARS_JSON__', json.dumps(years, ensure_ascii=False))
                .replace('__EXP_SPAN__', cfg.get('exp_span') or '最新A→E3三年复合'))
    regs = relax_bar_headroom(
        harden_null_formatters(normalize_chart_colors(cfg['chart_scripts'])))
    # 内联顺序固定：Chart.js → datalabels → boot(register) → 16 图 __reg → tail
    return (inline_lib('chart.umd.min.js') +
            inline_lib('chartjs-plugin-datalabels.min.js') +
            '<script>\n' + boot + '\n</script>\n' + '\n'.join(regs) +
            '\n' + TAIL + '\n' + QR_LIGHTBOX_JS + '\n')


EMPTY_DATA_PATTERNS = (
    r'var\s+names\s*=\s*\[\s*\]\s*;',
    r'var\s+series\s*=\s*\[\s*\]\s*;',
    r'\bdata\s*:\s*\[\s*\]\s*[,}]',
    r'\blabels\s*:\s*\[\s*\]\s*,',   # 图16 无 peer 时 labels:[] + 3 个 data:[]
)


def empty_chart_ids(scripts):
    """找出「数据数组为空」的图号。

    缺 segment / headcount 辅助表时 build_report_data.py 会写 names=[] / series=[]
    或 data:[]，Chart.js 仍会画出一套空坐标轴，交付出去就是「静默空图」。
    """
    out = []
    for s in scripts or []:
        m = re.search(r"__reg\('(chart\d+)'", s)
        if m and any(re.search(p, s) for p in EMPTY_DATA_PATTERNS):
            out.append(m.group(1))
    return out


def mark_empty_charts(doc, scripts):
    """静默空图 → 显式「数据未取得」提示卡。

    canvas 保留但置 hidden，维持 16 canvas ↔ 16 __reg 的交付门禁契约；
    不做任何插值、外推或编造。check_html.py 的 P0-8 会反向校验此标记。
    """
    for cid in empty_chart_ids(scripts):
        num = cid.replace('chart', '').zfill(2)
        if cid == 'chart16':
            reason = ('绘制本图需要同行可比公司的毛利率、净利率与资产负债率'
                      '（peer_comparison.csv），当前资料未提供。')
        else:
            reason = ('绘制本图所需的原始资料（分业务 / 分地域口径或员工人数）'
                      '未在现有资料中披露。')
        note = (
            '<div class="chart-empty-note" data-chart="%s">'
            '<div class="cen-badge">FIG.%s · 未披露</div>'
            '<div class="cen-title">本图数据未取得</div>'
            '<p>%s'
            '按「不编造、不插值」原则留空，补齐辅助表后重新生成即可自动出图。</p>'
            '</div>' % (cid, num, reason))
        pat = re.compile(
            r'(<div class="chart-body"[^>]*>)(<canvas[^>]*id="%s"[^>]*>)' % cid)
        m = pat.search(doc)
        if not m:
            continue
        body_open = m.group(1).replace('class="chart-body"',
                                       'class="chart-body chart-body-empty"')
        canvas = m.group(2)[:-1].rstrip() + ' hidden>'
        doc = doc[:m.start()] + body_open + note + canvas + doc[m.end():]
    return doc


def build(cfg, css):
    steps = cfg.get('steps') or []
    if len(steps) != 9:
        sys.exit('❌ content.json 需要恰好 9 个 steps（当前 %d 个）。'
                 '旧版换肤请用 --from-html，图表自动抽取请用 --prefilled。' % len(steps))
    if not cfg.get('chart_scripts'):
        print('  ⚠️  未提供 16 图脚本，报告将只有正文没有图表', file=sys.stderr)
    exec_block = ('<div class="exec-summary">\n<h2>执行摘要 <span>' +
                  esc(cfg.get('company', '')) + ' ' + esc(cfg.get('code', '')) +
                  ' · 十年年报口径</span></h2>\n' + cfg.get('summary_html', '') +
                  clean(cfg.get('exec_inner_html', '')) + '\n</div>\n')
    # footer 必须是 <body> 直接子元素（P0-10）：不能放进 .main-wrap，
    # 否则 .main-wrap / .report-footer 的双重 padding-left 会把页脚推到页面中间。
    main = ('<div class="main-wrap">\n' + build_toc(cfg) + '\n' + exec_block +
            '<div id="chart-error"></div>\n' + build_steps(cfg) + build_appendix(cfg) +
            '\n</div>\n' + render_brand_footer(cfg))
    # v2.1.5：正文表格统一列宽治理。只作用于 main，天然不触碰 build_scripts
    # 里内联的 Chart.js / datalabels 源码（八维历史补链事故同类风险）。
    main = enhance_tables(main)
    doc = ('<!DOCTYPE html>\n<html lang="zh-CN" data-theme="light">\n' +
           build_head(cfg, css) + '\n<body>\n' + build_header(cfg) + '\n' +
           main + build_scripts(cfg) + '</body>\n</html>\n')
    return mark_empty_charts(doc, cfg.get('chart_scripts'))


def copy_assets(out_path):
    dest = out_path.parent / 'assets'
    dest.mkdir(parents=True, exist_ok=True)
    for name in CHART_ASSETS:
        src = ASSETS / name
        if not src.exists():
            sys.exit('❌ 本地图表库缺失: %s' % src)
        tgt = dest / name
        if not tgt.exists() or tgt.stat().st_size != src.stat().st_size:
            shutil.copy2(src, tgt)


def main():
    ap = argparse.ArgumentParser(description='七步财报分析 · HYDRO PAPER 皮肤报告生成器')
    ap.add_argument('--data', help='content.json（叙事 + 可选 16 图脚本）')
    ap.add_argument('--from-html', help='旧成品 HTML：自动抽取 9 步正文/摘要/附录/16 图')
    ap.add_argument('--prefilled', help='report_prefilled.html：自动抽取 16 图脚本与年份轴')
    ap.add_argument('--out', required=True, help='最终 HTML 输出路径')
    ap.add_argument('--no-check', action='store_true', help='跳过 check_html.py 门禁')
    ap.add_argument('--no-assets', action='store_true',
                    help='不在同目录补齐 assets/（v2.1.2 起图表库已内联，此拷贝仅作旧流程兼容）')
    a = ap.parse_args()

    cfg = dict(DEFAULT)
    cfg.update(read_json(a.data))
    if a.from_html:
        cfg = from_html(a.from_html, cfg)
    if a.prefilled:
        cfg = from_prefilled(a.prefilled, cfg)
    # 16 图脚本由预填模板提供，容器由生成器幂等补齐（v2.1.3 · 修 P0-2 自杀式阻断）
    cfg = inject_chart_containers(cfg)
    # data 里的显式字段优先于自动抽取（overrides 语义）
    if a.data and a.from_html:
        cfg.update({k: v for k, v in read_json(a.data).items() if v not in ('', [], None)})

    css = load_css()
    doc = build(cfg, css)
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding='utf-8')
    if not a.no_assets:
        copy_assets(out)

    print('✅ 已生成: %s (%d bytes)' % (out, out.stat().st_size))
    print('   皮肤: HYDRO PAPER v3.0 | 章节: 9 + 附录 | 图表脚本: %d | 年份: %s'
          % (len(cfg['chart_scripts']), cfg.get('years') or '未注入'))
    print('   来源: %d 条登记 | 本轮联网核实 %s | 汇总锚点 #src-summary'
          % (len(cfg.get('sources') or {}),
             (cfg.get('source_meta') or {}).get('fetched_at') or '未留痕'))

    if not a.no_check:
        chk = Path(__file__).with_name('check_html.py')
        if chk.exists():
            r = subprocess.run([sys.executable, str(chk), str(out)],
                               capture_output=True, text=True, encoding='utf-8', errors='replace')
            print(r.stdout.rstrip())
            if r.stderr:
                print(r.stderr.rstrip(), file=sys.stderr)
            if r.returncode != 0:
                sys.exit(r.returncode)
        else:
            print('  ⚠️  check_html.py 不存在，跳过门禁', file=sys.stderr)


if __name__ == '__main__':
    main()
