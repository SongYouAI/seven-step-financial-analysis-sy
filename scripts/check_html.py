#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""七步财报分析 · 最终 HTML 交付门禁（P0 阻断 / P1 警告）。

用法：
  python3 check_html.py <最终报告.html> [--strict-p1] [--no-js]

检查项：
  P0-1  大写叙事占位符零残留（{{STEP1_CONTENT}} 等）
  P0-2  16 张 canvas 与 16 个 __reg 注册一一对应，且每步都内嵌 canvas
  P0-3  零远程资源依赖（script/link/img 的 http(s) 引用）、必须本地 assets/；
        v2.1.4 起 <a class="ref"> 来源角标为白名单（点击才联网，不影响离线渲染），
        但必须带 target="_blank" rel="noopener"，且 URL 要在来源汇总表登记
  P0-4  HYDRO PAPER 三层样式在位（hydro-base / hydro-skin / sevenstep-adapt）
  P0-5  内联 <script> 全部 node --check 通过
  P0-6  标签配平（div/section/table/script/style/blockquote）
  P0-7  9 个 step-card + 1 个 appendix，且免责声明在位
  P0-8  静默空图：数据数组为空的图必须有「未披露」提示卡（禁空白坐标轴交付）
  P0-9  作者溯源 brand 区块强制在位：公众号 + 视频号二维码（data URI 内嵌、零远程）
  P0-10 页脚层级：footer.report-footer 必须是 <body> 直接子元素，不得嵌在 .main-wrap 内
  P0-11 图表库自包含：Chart.js + datalabels 必须整段内联进 HTML，禁止仅靠同目录 assets/
        （报告会被单独复制/转发；外链本地资源 = 16 张图全空，typeof Chart === undefined）
  P0-12 16 图的数据标签 formatter 必须 null 安全（缺值按设计填 null 做断点；
        裸 v.toFixed() 会让 datalabels 抛 TypeError，整张图渲染失败）
  P0-14 表格排版质量（v2.1.6）：每张表必须经 enhance_tables() 注入
           data-table / colgroup / 列宽合计 100% / min-width；**th 与同列
           td 必须带同一组列语义类**（num / cell-key / cell-year / ...），
           否则表头与数据左右混排；CSS 必须含 table-layout:fixed、列级
           对齐规则、短列 nowrap、数字列右对齐、表头括注不拆行；
           图表数据标签必须移到柱顶外侧且顶部留白。
  P0-13 来源可核查（对标八维 P0-4）：id=src-summary 六元组汇总、≥12 个可点击角标、
        ≥5 个独立域名、无纯域名首页、角标 URL 全部登记、六元组列齐全、
        取数日期与 source-meta 本轮联网留痕、source-box + 状态徽章 + 页内跳转
  P1-1  正文无 emoji（字体缺字会渲染成豆腐块）
  P1-2  Markdown 残留（**粗体** / |--- 表格分隔 / 未转 <table>）
  P1-3  图表卡 .chart-card / .chart-idx 覆盖率
  P1-4  表格移动端滚动容器 .table-wrap 覆盖率
  P1-5  数据截止时点（YYYY-MM-DD HH:MM 或 YYYY-MM-DD）出现在 Hero
  P1-6  若仍保留相对 assets/ 引用，则同目录两个 js 必须齐备（v2.1.2 内联后已不再依赖）
  P1-7  悬空来源标记 UNSOURCED / [待验证] / [过时] 零残留

退出码：0=通过（可有 P1），1=P0 阻断，2=文件/依赖错误。
"""
import argparse
import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EMOJI_RE = re.compile('[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]')
PLACEHOLDER_RE = re.compile(r'\{\{([A-Z_][A-Z0-9_]*)\}\}')
EMPTY_DATA_PATTERNS = (
    r'var\s+names\s*=\s*\[\s*\]\s*;',
    r'var\s+series\s*=\s*\[\s*\]\s*;',
    r'\bdata\s*:\s*\[\s*\]\s*[,}]',
    r'\blabels\s*:\s*\[\s*\]\s*,',   # 图16 无 peer 时 labels:[] + 3 个 data:[]
)
def empty_note_ids(text):
    """P0-8：提示卡 class / data-chart 属性顺序无关，避免误判「静默空图」。"""
    out = set()
    for tag in re.findall(r'<div\b[^>]*\bclass="[^"]*chart-empty-note[^"]*"[^>]*>',
                          text, re.I):
        out.update(re.findall(r'data-chart="(chart\d+)"', tag))
    return out


def split_source_refs(text):
    """返回 (合规来源角标 URL 集合, 不合规角标 URL 列表)。

    v2.1.4：把「资源型远程引用」和「引用型溯源链接」分开。前者会让报告
    离开 assets/ 后丢图表库（v2.1.2 事故），必须继续 P0 阻断；后者只在用户
    点击时联网，离线打开时正文与 16 图照常渲染，予以放行。
    白名单必须同时满足 class 含 ref / target=_blank / rel 含 noopener，
    避免有人用普通 <a href="https://cdn..."> 绕过 P0-3。
    """
    allowed, bad = set(), []
    for tag in re.findall(r'<a\b[^>]*>', text, re.I):
        cls = re.search(r'\bclass\s*=\s*[\"\']([^\"\']*)[\"\']', tag, re.I)
        if not cls or 'ref' not in cls.group(1).split():
            continue
        href = re.search(r'\bhref\s*=\s*[\"\'](https?://[^\"\']+)[\"\']', tag, re.I)
        if not href:
            continue
        url = html.unescape(href.group(1))
        if (re.search(r'\btarget\s*=\s*[\"\']_blank[\"\']', tag, re.I) and
                re.search(r'\brel\s*=\s*[\"\'][^\"\']*\bnoopener\b[^\"\']*[\"\']',
                          tag, re.I)):
            allowed.add(url)
        else:
            bad.append(url)
    return allowed, bad


def is_pure_domain(url):
    """纯域名首页不合格：点开找不到被引数字（output-spec 四级颗粒度）。"""
    from urllib.parse import urlparse
    u = urlparse(url)
    return not u.path.strip('/') and not u.query and not u.fragment


def source_domains(urls):
    from urllib.parse import urlparse
    return sorted({urlparse(u).netloc.lower() for u in urls if urlparse(u).netloc})


def _managed_nodes():
    """WorkBuddy 内置 node：用 Path.home() 动态探测，不写死用户名与版本号。

    旧版硬编码 /Users/<某人>/.workbuddy/binaries/node/versions/22.x/bin/node，
    换机器即失效且会把本机用户名带进公开仓库，已改为通配目录。
    """
    import glob
    base = Path.home() / '.workbuddy' / 'binaries' / 'node' / 'versions'
    return sorted(glob.glob(str(base / '*' / 'bin' / 'node')), reverse=True)


NODE_CANDIDATES = ['node'] + _managed_nodes() + [
    '/usr/local/bin/node', '/opt/homebrew/bin/node',
]


def find_node():
    for c in NODE_CANDIDATES:
        p = shutil.which(c) if c == 'node' else (c if Path(c).exists() else None)
        if p:
            return p
    return None


def footer_inside_main_wrap(text):
    """P0-10：检测 footer 是否嵌在 .main-wrap 内。

    .main-wrap 与 .report-footer 各自带 padding-left（宽屏 248px，给固定侧栏让位）。
    footer 一旦嵌进 main-wrap，248px 会叠加两次，页脚相对正文右移 248px。
    八维 HYDRO PAPER 模板的 footer 是 <body> 直接子元素，此处保持同一 DOM 契约。
    """
    m_footer = re.search(r'<footer[^>]*class="[^"]*\breport-footer\b', text, re.I)
    if not m_footer:
        return False
    end = m_footer.start()
    stack = []
    tag_re = re.compile(r'<(/?)div\b([^>]*)>', re.I)
    for m in tag_re.finditer(text, 0, end):
        if m.group(1):
            if stack:
                stack.pop()
        else:
            stack.append(bool(re.search(r'\bclass="[^"]*\bmain-wrap\b', m.group(2), re.I)))
    return any(stack)


def main():
    ap = argparse.ArgumentParser(description='七步财报分析 HTML 交付门禁')
    ap.add_argument('html', help='最终报告 HTML 路径')
    ap.add_argument('--strict-p1', action='store_true', help='P1 警告也阻断（交付默认只阻断 P0）')
    ap.add_argument('--no-js', action='store_true', help='跳过 node --check')
    a = ap.parse_args()

    p = Path(a.html).resolve()
    if not p.exists():
        print('❌ 文件不存在: %s' % p)
        return 2
    t = p.read_text(encoding='utf-8-sig')
    # 正文档位独立命名：旧版 body 会被 P0-11 的内联库源码覆盖，
    # 导致 P1-1 emoji / P1-2 Markdown 残留实际在查 JS 源码，检查恒真通过。
    doc_body = t[t.find('<body'):] if '<body' in t else t
    p0, p1 = [], []

    # P0-1 占位符
    left = sorted(set(PLACEHOLDER_RE.findall(t)))
    if left:
        p0.append('P0-1 残留大写占位符 %d 个: %s' % (len(left), ', '.join(left[:12])))

    # P0-2 图表
    canvases = re.findall(r'<canvas[^>]*id="(chart\d+)"', t)
    regs = re.findall(r"__reg\('(chart\d+)'", t)
    if len(canvases) != 16:
        p0.append('P0-2 canvas 数 %d ≠ 16' % len(canvases))
    if len(regs) != 16:
        p0.append('P0-2 __reg 注册数 %d ≠ 16' % len(regs))
    if set(canvases) != set(regs):
        p0.append('P0-2 canvas 与 __reg ID 不一致: 缺注册=%s / 缺容器=%s'
                  % (sorted(set(canvases) - set(regs)), sorted(set(regs) - set(canvases))))
    if len(set(canvases)) != len(canvases):
        p0.append('P0-2 canvas ID 重复 %d 个（16 个容器必须是 1—16 各一次）'
                  % (len(canvases) - len(set(canvases))))
    if len(set(regs)) != len(regs):
        p0.append('P0-2 __reg ID 重复 %d 个' % (len(regs) - len(set(regs))))
    # 图表应内嵌在步骤卡里，但并非每步都有图（第8步「八问商业模式」按规范无图）。
    # 旧版逐卡要求 canvas 会对第8步误报，改为校验所有 canvas 都落在某个 step-card 内。
    cards = re.findall(
        r'<div class="step-card" id="(step\d+)"[^>]*>(.*?)'
        r'(?=<div class="step-card" id=|<div id="appendix"|<footer|$)', t, re.S)
    n_in_cards = sum(block.count('<canvas') for _, block in cards)
    if n_in_cards < len(canvases):
        p1.append('P1-3 %d 个 canvas 未内嵌在 step-card（裸放在卡外）'
                  % (len(canvases) - n_in_cards))

    # P0-3 远程资源依赖（v2.1.4 起区分资源型 / 引用型）
    # src / CSS url() / srcset / <link href> 一律禁：离线打开会缺图表库。
    # <a class="ref" href="http…" target="_blank" rel="noopener"> 点击才联网，
    # 不参与离线渲染，予以放行（对标八维 P0-4 可核查链接）。
    src_remote = re.findall(r'\bsrc\s*=\s*[\"\'](https?://[^\"\']+)[\"\']', t, re.I)
    href_remote = re.findall(r'\bhref\s*=\s*[\"\'](https?://[^\"\']+)[\"\']', t, re.I)
    css_remote = re.findall(r'url\(\s*[\"\']?(https?://[^)\s\"\']+)', t, re.I)
    srcset_remote = re.findall(r'srcset\s*=\s*[\"\']([^\"\']*https?://[^\"\']+)[\"\']', t, re.I)
    ref_allowed, ref_bad = split_source_refs(t)
    remote = (src_remote + css_remote + srcset_remote +
              [u for u in href_remote if html.unescape(u) not in ref_allowed])
    if remote:
        p0.append('P0-3 远程资源依赖 %d 处: %s' % (len(remote), ', '.join(remote[:3])))
    if ref_bad:
        p0.append('P0-3 %d 个来源角标缺 target="_blank"/rel="noopener": %s'
                  % (len(ref_bad), ', '.join(ref_bad[:3])))
    if 'cdn.jsdelivr' in t:
        p0.append('P0-3 存在 CDN 兜底分支（本环境不可达）')

    # P0-11 图表库自包含（v2.1.2）：报告会被单独复制/多级转发，
    # 只靠 <script src="assets/..."> 时，一旦 HTML 离开 assets/ 目录，
    # typeof Chart === 'undefined'，16 张 canvas 全部只剩空框。
    inlined = {}
    for _name, _min in (('chart.umd.min.js', 100000),
                        ('chartjs-plugin-datalabels.min.js', 8000)):
        m = re.search(r'<!-- ' + re.escape(_name) +
                      r' \(inlined, (\d+) bytes\) -->\s*<script>(.*?)</script>', t, re.S)
        if not m:
            p0.append('P0-11 图表库 %s 未内联（HTML 非自包含，单独转发会全图空白）' % _name)
            continue
        lib_body = m.group(2)
        real = len(lib_body.encode('utf-8'))
        if real < _min or int(m.group(1)) < _min:
            p0.append('P0-11 内联 %s 被截断（声明 %s bytes / 实测 %d bytes）'
                      % (_name, m.group(1), real))
        # 只量体积可被「120KB 任意 JS」绕过；必须含库特征串
        needle = 'Chart' if _name.startswith('chart.umd') else 'ChartDataLabels'
        if needle not in lib_body:
            p0.append('P0-11 内联 %s 不含特征串 %s（疑似占位内容，typeof 将为 undefined）'
                      % (_name, needle))
        inlined[_name] = real
    for _name in ('chart.umd.min.js', 'chartjs-plugin-datalabels.min.js'):
        if 'src="assets/%s"' % _name in t:
            p0.append('P0-11 仍存在相对引用 src="assets/%s"，报告不可单独转发' % _name)

    # P0-12 数据标签 formatter 必须 null 安全（只检查 16 段 __reg，不误伤内联库）
    reg_blocks = re.findall(r'<script>\s*window\.__reg\(.*?</script>', t, re.S)
    unsafe_fmt = []
    for _b in reg_blocks:
        _m = re.search(r"__reg\('(chart\d+)'", _b)
        _cid = _m.group(1) if _m else '?'
        # formatter 与 ticks.callback 都要查：Y 轴刻度同样会收到 null tick
        if re.search(r'(?:formatter|callback)\s*:\s*[^,}]{0,80}?v\.toFixed\(', _b):
            unsafe_fmt.append(_cid)
    if unsafe_fmt:
        p0.append('P0-12 %d 张图的 formatter 未做 null 保护：%s（缺值填 null 时整图渲染失败）'
                  % (len(unsafe_fmt), ', '.join(unsafe_fmt)))
    null_points = len(re.findall(r'\bdata\s*:\s*\[[^\]]*\bnull\b',
                                 '\n'.join(reg_blocks)))

    # ---- P0-13 来源可核查（v2.1.4 · 对标八维 P0-4 / P1-6 / P1-7）----
    # 只做离线静态门禁：网络探活由 verify_links.py --strict 单独跑。
    # 门禁本身绝不依赖网络，否则离线出稿会被当次网络状况误杀。
    sidx = t.find('id="src-summary"')
    summary = t[sidx:] if sidx >= 0 else ''
    ref_urls = sorted(ref_allowed)
    domains = source_domains(ref_urls)
    if sidx < 0:
        p0.append('P0-13 缺 id="src-summary" 来源汇总锚点区（六元组表 + 取数日期）')
    if len(ref_urls) < 12:
        p0.append('P0-13 可点击来源角标仅 %d 个（应 ≥12，每步 + 关键数据均需可回溯）'
                  % len(ref_urls))
    if len(domains) < 5:
        p0.append('P0-13 独立来源域名仅 %d 个（应 ≥5，疑似单一来源复用）' % len(domains))
    pure = [u for u in ref_urls if is_pure_domain(u)]
    if pure:
        p0.append('P0-13 %d 条纯域名首页不合格（应指向具体披露页/带锚点）: %s'
                  % (len(pure), ', '.join(pure[:3])))
    missing_reg = [u for u in ref_urls
                   if u not in summary and html.escape(u, quote=True) not in summary]
    if missing_reg:
        p0.append('P0-13 %d 条角标 URL 未在 src-summary 六元组表登记: %s'
                  % (len(missing_reg), ', '.join(missing_reg[:3])))
    for kw in ('口径', '页面标题', '发布日期', '抓取日期'):
        if kw not in summary:
            p0.append('P0-13 来源汇总表缺六元组列「%s」' % kw)
            break
    if not re.search(r'20\d{2}-\d{2}-\d{2}', summary):
        p0.append('P0-13 来源汇总区缺取数/抓取日期（YYYY-MM-DD）')
    meta_tag = re.search(r'id="source-meta"[^>]*>', t)
    if (not meta_tag or
            not re.search(r'data-fetched-at="\d{4}-\d{2}-\d{2}"', meta_tag.group(0)) or
            'data-online-checked=' not in meta_tag.group(0)):
        p0.append('P0-13 缺 id="source-meta" 本轮联网核实留痕'
                  '（data-fetched-at / data-online-checked）')
    if t.count('class="source-box"') < 1:
        p0.append('P0-13 正文缺 .source-box 数据来源框')
    if 'href="#src-summary"' not in t:
        p0.append('P0-13 来源框缺 href="#src-summary" 页内跳转')
    if 'status-badge' not in t:
        p0.append('P0-13 来源框缺状态徽章（已验证 / 已解释 / 数据缺口）')
    n_src_ref, n_src_dom = len(ref_urls), len(domains)

    # P0-4 三层皮肤
    for sid in ('hydro-base', 'hydro-skin', 'sevenstep-adapt'):
        if 'id="%s"' % sid not in t:
            p0.append('P0-4 缺样式层 id="%s"' % sid)
    if 'HYDRO PAPER' not in t:
        p1.append('P1-3 未见 HYDRO PAPER 设计标识')

    # P0-5 内联 JS 语法
    if not a.no_js:
        node = find_node()
        inline = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', t, re.S)
        if node:
            tmp = Path(tempfile.mkdtemp(prefix='sevenstep_checkjs_'))
            bad = []
            for i, s in enumerate(inline, 1):
                f = tmp / ('s%02d.js' % i)
                f.write_text(s, encoding='utf-8')
                r = subprocess.run([node, '--check', str(f)], capture_output=True,
                                   text=True, encoding='utf-8', errors='replace')
                if r.returncode != 0:
                    bad.append('s%02d: %s' % (i, r.stderr.strip().splitlines()[-1][:120]))
            if bad:
                p0.append('P0-5 内联 JS 语法错误 %d 段: %s' % (len(bad), ' | '.join(bad[:3])))
            print('  JS: %d 段内联脚本, node --check %s' % (len(inline), 'FAIL' if bad else 'PASS'))
        else:
            p1.append('P1-5 未找到 node，跳过 JS 语法检查')

    # P0-6 标签配平
    for tag in ('div', 'section', 'table', 'script', 'style', 'blockquote'):
        o = len(re.findall(r'<%s[\s>]' % tag, t))
        c = len(re.findall(r'</%s>' % tag, t))
        if o != c:
            p0.append('P0-6 <%s> 开 %d / 闭 %d 不配平' % (tag, o, c))

    # P0-7 章节与免责
    n_steps = len(re.findall(r'<div class="step-card" id="step\d+"', t))
    if n_steps != 9:
        p0.append('P0-7 step-card 数 %d ≠ 9' % n_steps)
    if 'id="appendix"' not in t:
        p0.append('P0-7 缺附录 section')
    if '不构成投资建议' not in t:
        p0.append('P0-7 缺固定免责声明')

    # P0-8 静默空图：names=[] / series=[] / data:[] 时 Chart.js 仍画空坐标轴。
    # SKILL.md §19.6 要求「须标注未披露，不得编造」，这里做结构性硬校验。
    empty_ids = []
    for cid, s in re.findall(r"__reg\('(chart\d+)',(.*?)</script>", t, re.S):
        if any(re.search(p, s) for p in EMPTY_DATA_PATTERNS):
            empty_ids.append(cid)
    noted = empty_note_ids(t)
    silent = [c for c in empty_ids if c not in noted]
    if silent:
        p0.append('P0-8 静默空图 %d 张（数据为空仍画空坐标轴，且无未披露提示）: %s'
                  % (len(silent), ', '.join(sorted(silent))))

    # P0-9 作者溯源 brand 区块（v2.1.0）：报告会被多级转发，页脚是唯一稳定出处锚点。
    # 与八维版 P0-16 同思路；content.json 不能关闭或覆盖，二维码必须是本地 data URI。
    if 'class="brand-block"' not in t:
        p0.append('P0-9 缺作者溯源 brand-block（页脚二维码区块被关闭或覆盖）')
    if 'id="qrLightbox"' not in t:
        p0.append('P0-9 缺二维码放大容器 qrLightbox')
    n_qr_btn = t.count('class="brand-qr"')
    if n_qr_btn < 2:
        p0.append('P0-9 二维码按钮仅 %d 个（应 2：公众号 + 视频号）' % n_qr_btn)
    n_qr_img = len(re.findall(
        r'<img[^>]+src="data:image/png;base64,[A-Za-z0-9+/=]{100,}"', t))
    if n_qr_img < 2:
        p0.append('P0-9 内嵌二维码 data URI 仅 %d 张（应 2，禁止远程图片）' % n_qr_img)
    for _label in ('公众号', '视频号'):
        if _label not in t:
            p0.append('P0-9 缺渠道标识「%s」' % _label)

    # P0-10 页脚层级（v2.1.1）：嵌套会让 padding-left 叠加，页脚跑到页面中间。
    if footer_inside_main_wrap(t):
        p0.append('P0-10 footer.report-footer 嵌在 .main-wrap 内：padding-left 双重偏移，'
                  '页脚相对正文右移；请让 footer 成为 <body> 直接子元素')

    # P1-1 emoji
    emo = sorted(set(EMOJI_RE.findall(doc_body)))
    if emo:
        p1.append('P1-1 正文残留 emoji %d 种: %s' % (len(emo), ' '.join(emo[:10])))

    # P1-2 Markdown 残留
    if re.search(r'\*\*[^*]+\*\*', doc_body):
        p1.append('P1-2 正文残留 Markdown **粗体**')
    if '|---' in doc_body or re.search(r'(?m)^\|[^|\n]+\|', doc_body):
        p1.append('P1-2 正文残留 Markdown 表格语法')

    # P1-3 图表卡
    n_chart_card = t.count('class="chart-card"')
    if n_chart_card < 16:
        p1.append('P1-3 .chart-card 仅 %d 个（应 16，裸图注未包卡）' % n_chart_card)
    if t.count('class="chart-idx"') < 16:
        p1.append('P1-3 .chart-idx 编号徽章不足 16')

    # P1-4 表格滚动
    n_table = len(re.findall(r'<table[\s>]', t))
    n_wrap = t.count('class="table-wrap table-scroll"')
    if n_table and n_wrap < n_table:
        p1.append('P1-4 %d 张表中仅 %d 张有移动端滚动容器' % (n_table, n_wrap))

    # ---- P0-14 表格排版质量（v2.1.6 · 竖排 / 挤叠 / 左右混排三类事故）----
    # ① 裸 table + table-layout:auto → 中文短列被压成 1 字宽竖排；
    # ② 逐格判定数字列 + th 完全不打类 → 31/31 张表同列 left/right 混排、
    #    表头与数据中心最大偏移 165px。列宽合格 != 对齐合格，必须单独验。
    tbl_blocks = re.findall(r'<table\b([^>]*)>(.*?)</table>', t, re.S | re.I)
    if not tbl_blocks:
        p0.append('P0-14 报告无表格（七步报告必须含数据表与来源汇总表）')
    else:
        bare = [i + 1 for i, (ta, _) in enumerate(tbl_blocks)
                if 'data-table' not in ta]
        if bare:
            p0.append('P0-14 %d 张表是裸 table（未经 enhance_tables，会竖排）: %s'
                      % (len(bare), ', '.join('#%d' % i for i in bare[:8])))
        bad_cols, bad_min = [], []
        for i, (ta, tb) in enumerate(tbl_blocks):
            n_th = len(re.findall(r'<th\b', tb, re.I))
            n_col = len(re.findall(r'<col\b', tb, re.I))
            widths = [float(x) for x in
                      re.findall(r'<col[^>]*width:\s*([\d.]+)%', tb)]
            if ('<colgroup' not in tb or (n_th and n_col != n_th)
                    or not widths or abs(sum(widths) - 100) > 0.5):
                bad_cols.append('#%d' % (i + 1))
            if not re.search(r'min-width:\d+px', ta):
                bad_min.append('#%d' % (i + 1))
        if bad_cols:
            p0.append('P0-14 %d 张表列宽契约不合格（colgroup / 列数 / 合计100%%）: %s'
                      % (len(bad_cols), ', '.join(bad_cols[:8])))
        if bad_min:
            p0.append('P0-14 %d 张表缺 min-width（宽表会被压回正文宽度）: %s'
                      % (len(bad_min), ', '.join(bad_min[:8])))

        # 列级对齐契约：同一列的表头与数据必须拿到同一组语义类。
        # 缺少任何一处，CSS 的 .num 右对齐就只作用于其中一半，肉眼即错位。
        ROLES = {'num', 'cell-key', 'cell-year', 'cell-tight', 'cell-status'}

        def col_roles(attrs):
            mc = re.search(r'class="([^"]*)"', attrs)
            return set(mc.group(1).split() if mc else []) & ROLES

        bad_align = []
        for i, (_, tb) in enumerate(tbl_blocks):
            hm = re.search(r'<thead[^>]*>(.*?)</thead>', tb, re.S | re.I)
            bm = re.search(r'<tbody[^>]*>\s*<tr[^>]*>(.*?)</tr>', tb, re.S | re.I)
            if not hm or not bm:
                continue
            ths = re.findall(r'<th\b([^>]*)>', hm.group(1), re.I)
            tds = re.findall(r'<td\b([^>]*)>', bm.group(1), re.I)
            if len(ths) != len(tds):
                continue                # colspan 等特殊行交给列宽契约检查
            for j, (a, b) in enumerate(zip(ths, tds)):
                if col_roles(a) != col_roles(b):
                    bad_align.append('#%d c%d' % (i + 1, j))
        if bad_align:
            p0.append('P0-14 %d 处表头/数据列类不一致（同列会左右混排）: %s'
                      % (len(bad_align), ', '.join(bad_align[:8])))
    for rule in ('table-layout:fixed', '.cell-tight', 'td.num',
                 'white-space:nowrap;flex:none',
                 '.data-table thead th.cell-key',
                 '.data-table tbody td.num.cell-tight',
                 '.data-table thead th .unit',
                 'text-align:left;'):
        if rule not in t:
            p0.append('P0-14 sevenstep-adapt.css 缺表格规则 %s' % rule)
    if "align='top'" not in t or 'padding.top=22' not in t:
        p0.append('P0-14 图表数据标签未移到柱顶外侧 / 顶部无留白')

    # P1-5 数据截止时点
    hero = t[t.find('<header class="hero"'):t.find('</header>') + 9]
    if not re.search(r'\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?', hero):
        p1.append('P1-5 Hero 未见数据截止时点（YYYY-MM-DD [HH:MM]）')
    elif not any(w in hero for w in ('截至', '截止', '数据时点')):
        p1.append('P1-5 Hero 有日期但缺「截至/截止/数据时点」口径关键词')

    # P1-7 悬空来源标记（v2.1.4）
    for mark in ('UNSOURCED', '[待验证]', '[过时]'):
        if mark in doc_body:
            p1.append('P1-7 正文残留悬空标记 %s（需补来源或改写为 L4 降级署名）' % mark)

    # P1-6 相对 assets/ 引用（v2.1.2 起已内联，正常应为 0；保留兼容旧流程）
    assets = p.parent / 'assets'
    if 'src="assets/' in t:
        for name in ('chart.umd.min.js', 'chartjs-plugin-datalabels.min.js'):
            if not (assets / name).exists():
                p1.append('P1-6 引用了 assets/%s，但同目录文件缺失' % name)

    # ---- 汇总 ----
    print('\n=== HTML 交付门禁: %s ===' % p.name)
    print('  体积 %d bytes | step-card %d | canvas %d | __reg %d | chart-card %d | table %d | 空图提示 %d/%d | 二维码 %d | 内联图表库 %d/2 | null断点 %d'
          % (p.stat().st_size, n_steps, len(canvases), len(regs), n_chart_card,
             n_table, len(noted), len(empty_ids), n_qr_img, len(inlined), null_points))
    print('  来源角标 %d | 来源域名 %d | src-summary %s | 来源留痕 %s'
          % (n_src_ref, n_src_dom, '在位' if sidx >= 0 else '缺',
             '在位' if meta_tag else '缺'))
    for x in p0:
        print('  ❌ ' + x)
    for x in p1:
        print('  ⚠️  ' + x)
    if not p0 and not p1:
        print('  ✅ 全绿：P0=0 / P1=0')
    else:
        print('  合计 P0=%d / P1=%d' % (len(p0), len(p1)))
    if p0:
        return 1
    if p1 and a.strict_p1:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
