#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""七步财报分析 · 分段视觉验收截图（HYDRO PAPER 配套）。

Chrome headless 对 file://...#step4 锚点不会滚动，直接截图永远停在首屏（白屏）。
本脚本把目标 section 裁成独立 HTML：复用原报告完整 <head> + 目标 section 正文
+ 全部 <script>（含本地 Chart.js，改写为绝对 file URI），再截图。
**不修改最终交付 HTML**，所有临时文件在系统临时目录。

用法：
  python3 capture.py <报告.html> --section step4
  python3 capture.py <报告.html> --all --outdir ./shots   # 9 步 + 附录 + 页脚二维码
  python3 capture.py <报告.html> --section step1 --width 1440 --height 2400

退出码：0=全部成功；1=参数/文件/Chrome 不可用；2=部分失败。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME_CANDIDATES = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium', '/usr/bin/chromium-browser',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
]
CHROME_COMMANDS = ['google-chrome', 'google-chrome-stable', 'chromium', 'chrome']
SECTIONS = ['step%d' % i for i in range(1, 10)] + ['appendix', 'footer']

OVERRIDE = """<style id="capture-only">
  .side-nav,.top-progress,.theme-toggle,#chart-error{display:none !important;}
  .main-wrap{max-width:none !important;width:100% !important;margin:0 !important;padding:16px 24px !important;}
  .step-card{opacity:1 !important;transform:none !important;margin:0 0 24px !important;}
  .chart-body{height:340px !important;}
  .hero{min-height:0 !important;}
</style>"""


def find_chrome(explicit=None):
    if explicit:
        return explicit if (os.path.isfile(explicit) or shutil.which(explicit)) else None
    for p in CHROME_CANDIDATES:
        if os.path.isfile(p):
            return p
    for c in CHROME_COMMANDS:
        got = shutil.which(c)
        if got:
            return got
    return None


def slice_page(text, sid, report_dir):
    h_end = text.rfind('</head>')
    if h_end < 0:
        return None
    head = text[:h_end] + OVERRIDE + '\n</head>'

    if sid in ('hero', 'exec', 'footer'):
        if sid == 'hero':
            i = text.find('<header class="hero"')
            e = text.find('</header>', i) + len('</header>')
        elif sid == 'footer':
            # 页脚 brand 溯源条：公众号 / 视频号二维码目视验收（v2.1.0）
            i = text.find('<footer class="report-footer"')
            e = text.find('</footer>', i) + len('</footer>')
        else:
            i = text.find('<div class="main-wrap">')
            e = text.find('<div id="chart-error">', i)
        frag = text[i:e] if i >= 0 and e > i else None
    else:
        m = re.search(r'id=["\']%s["\']' % re.escape(sid), text)
        if not m:
            return None
        start = text.rfind('<div', 0, m.start())
        tag_end = text.find('>', m.start())
        if start < 0 or 'step-card' not in text[start:tag_end + 1]:
            return None
        nxt = re.search(r'<div\b[^>]*\bclass=["\'][^"\']*\bstep-card\b', text[tag_end + 1:])
        end = tag_end + 1 + nxt.start() if nxt else text.rfind('</body>')
        frag = text[start:end]
    if frag is None:
        return None

    scripts = '\n'.join(re.findall(r'<script[^>]*>.*?</script>', text, re.S))
    # 本地相对 assets 改绝对 file URI，保证临时目录里 Chart.js 能加载
    for name in ('chart.umd.min.js', 'chartjs-plugin-datalabels.min.js'):
        asset = (report_dir / 'assets' / name).resolve()
        uri = asset.as_uri()
        scripts = scripts.replace('src="assets/%s"' % name, 'src="%s"' % uri)

    return ('<!DOCTYPE html><html lang="zh-CN" data-theme="light">' + head +
            '\n<body><div class="main-wrap">' + frag + '\n</div>\n' + scripts +
            '\n</body></html>')


def shot(page, out, chrome, width, height, budget, user_dir):
    cmd = [chrome, '--headless=new', '--no-sandbox', '--disable-gpu',
           '--hide-scrollbars', '--force-device-scale-factor=1',
           '--virtual-time-budget=%d' % budget,
           '--window-size=%d,%d' % (width, height),
           '--user-data-dir=' + user_dir,
           '--screenshot=' + str(out), Path(page).resolve().as_uri()]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=120)
    except subprocess.TimeoutExpired:
        print('  超时: %s' % out, file=sys.stderr)
        return False
    ok = r.returncode == 0 and out.exists() and out.stat().st_size > 0
    if not ok:
        print('  失败 rc=%d %s' % (r.returncode, (r.stderr or '')[-200:]), file=sys.stderr)
    return ok


def main():
    ap = argparse.ArgumentParser(description='七步报告分段视觉验收截图')
    ap.add_argument('report', help='最终报告 HTML')
    ap.add_argument('--section', choices=SECTIONS + ['hero', 'exec'])
    ap.add_argument('--all', action='store_true', help='截全部 9 步 + 附录 + 页脚二维码')
    ap.add_argument('--out', help='单张输出路径')
    ap.add_argument('--outdir', help='--all 输出目录')
    ap.add_argument('--chrome', default=None)
    ap.add_argument('--width', type=int, default=1440)
    ap.add_argument('--height', type=int, default=2400)
    ap.add_argument('--timeout', type=int, default=9000, help='virtual-time-budget 毫秒')
    a = ap.parse_args()

    report = Path(a.report).resolve()
    if not report.is_file():
        print('❌ 报告不存在: %s' % report, file=sys.stderr)
        return 1
    chrome = find_chrome(a.chrome)
    if not chrome:
        print('❌ 未找到 Chrome（用 --chrome 指定）', file=sys.stderr)
        return 1
    if not a.section and not a.all:
        ap.error('需要 --section 或 --all')

    ids = SECTIONS if a.all else [a.section]
    outdir = Path(a.outdir or './shots').resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    text = report.read_text(encoding='utf-8-sig')
    print('Chrome: %s' % chrome)

    failed = []
    with tempfile.TemporaryDirectory(prefix='sevenstep-capture-') as tmp:
        for i, sid in enumerate(ids):
            frag = slice_page(text, sid, report.parent)
            if frag is None:
                print('SKIP %s：找不到该 section' % sid)
                failed.append(sid)
                continue
            page = Path(tmp) / (sid + '.html')
            page.write_text(frag, encoding='utf-8')
            out = (outdir / (sid + '.png')) if a.all else Path(a.out or (sid + '_capture.png'))
            ok = shot(page, out, chrome, a.width, a.height, a.timeout,
                      os.path.join(tmp, 'profile_%d' % i))
            print(('OK   ' if ok else 'FAIL ') + sid + ' -> ' + str(out))
            if not ok:
                failed.append(sid)
    return 2 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
