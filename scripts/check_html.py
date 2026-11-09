#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""七步财报分析 · 最终 HTML 交付门禁（P0 阻断 / P1 警告）。

用法：
  python3 check_html.py <最终报告.html> [--strict-p1] [--no-js]

检查项：
  P0-1  大写叙事占位符零残留（{{STEP1_CONTENT}} 等）
  P0-2  16 张 canvas 与 16 个 __reg 注册一一对应，且每步都内嵌 canvas
  P0-3  零远程资源（script/link/img 的 http(s) 引用）、必须本地 assets/
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
  P1-1  正文无 emoji（字体缺字会渲染成豆腐块）
  P1-2  Markdown 残留（**粗体** / |--- 表格分隔 / 未转 <table>）
  P1-3  图表卡 .chart-card / .chart-idx 覆盖率
  P1-4  表格移动端滚动容器 .table-wrap 覆盖率
  P1-5  数据截止时点（YYYY-MM-DD HH:MM 或 YYYY-MM-DD）出现在 Hero
  P1-6  若仍保留相对 assets/ 引用，则同目录两个 js 必须齐备（v2.1.2 内联后已不再依赖）

退出码：0=通过（可有 P1），1=P0 阻断，2=文件/依赖错误。
"""
import argparse
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

    # P0-3 远程资源
    # 属性引号 / 等号空格 / CSS url() / srcset 一律归一化后再扫，防单引号绕过
    remote = re.findall(r'(?:src|href)\s*=\s*[\"\'](https?://[^\"\']+)[\"\']', t, re.I)
    remote += re.findall(r'url\(\s*[\"\']?(https?://[^)\s\"\']+)', t, re.I)
    remote += re.findall(r'srcset\s*=\s*[\"\']([^\"\']*https?://[^\"\']+)[\"\']', t, re.I)
    if remote:
        p0.append('P0-3 远程资源 %d 处: %s' % (len(remote), ', '.join(remote[:3])))
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

    # P1-5 数据截止时点
    hero = t[t.find('<header class="hero"'):t.find('</header>') + 9]
    if not re.search(r'\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?', hero):
        p1.append('P1-5 Hero 未见数据截止时点（YYYY-MM-DD [HH:MM]）')

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
