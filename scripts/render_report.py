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
    Chart.defaults.plugins.datalabels.font.size=11;
    Chart.defaults.plugins.datalabels.anchor='end';
    Chart.defaults.plugins.datalabels.clamp=true;
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
}


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


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
    side += '<a href="#appendix">附录 · 数据来源</a>'
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
        '<span class="toc-d">原始表、缺口、免责声明</span></div></div>')
    return ('<div class="toc-card"><div class="toc-title">报告导航 · 点击跳转</div>'
            '<div class="toc-grid">' + ''.join(items) + '</div></div>')


def build_steps(cfg):
    out = []
    for i, s in enumerate(cfg['steps']):
        num = str(i + 1)
        sub = s.get('sub') or ''
        out.append(
            '<div class="step-card" id="step' + num + '">\n'
            '<div class="step-head"><div class="step-num-watermark">' + num.zfill(2) + '</div>\n'
            '<div class="step-head-text"><div class="step-num">STEP ' + num.zfill(2) + ' / 09</div>\n'
            '<div class="step-title">' + esc(s.get('title') or STEP_TITLES[i]) + '</div>'
            '<div class="step-sub">' + esc(sub) + '</div></div></div>\n'
            '<div class="step-body">' + clean(s.get('html', '')) + '</div>\n</div>\n')
    return ''.join(out)


# ---------------------------------------------------------------------------
# 页脚 brand 溯源条（v2.1.0 · 移植自八维 HYDRO PAPER v3.2.2）
# ---------------------------------------------------------------------------
# 报告会被多级转发，页脚是唯一稳定的出处锚点。品牌常量集中在 assets/brand.json，
# 二维码以 data URI 内嵌：离线打开 / 打印 / SkillHub 纯文本分发都不丢图。
# 本块强制输出，content.json 不能关闭或覆盖（check_html.py P0-9 反向复核）。
# 与八维版差异：七步门禁 P0-3 禁止任何 http(s) src/href，故不提供 branding.url。
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
           '<div class="step-body">' + clean(cfg.get('appendix_html', '')) + '\n</div>\n</div>\n')
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
        out.append(s)
    return out


def build_scripts(cfg):
    years = cfg.get('years') or []
    boot = (BOOT.replace('__YEARS_JSON__', json.dumps(years, ensure_ascii=False))
                .replace('__EXP_SPAN__', cfg.get('exp_span') or '最新A→E3三年复合'))
    regs = harden_null_formatters(normalize_chart_colors(cfg['chart_scripts']))
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
