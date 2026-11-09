#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
orchestrate.py — 七步财报分析 端到端编排 (v4.0)
=============================================
串联：
  模块0 输入适配 → 模块1 合并行防御 → 核心 build_metrics →
  模块2 业务构成 → 模块3 员工构成 → 模块4 一致预期 →
  模块5 强校验 → 模块6 口径自证 → 模块7 图表数据/prefilled →
  模块8 内容质检(MD) → 模块9 最终 HTML(render_report + check_html)

核心步骤失败**立即阻断并非零退出**（旧版丢弃所有返回码，仍打印「✅ 流水线完成」）；
可选模块失败只警告。提供 --content 才会产出最终 HTML，否则明确提示停在中间稿。

用法：
  # 本地 CSV 档
  orchestrate.py --in <源数据dir> --out <产出dir> \
      [--forecast <forecast_input.csv>] [--aliases <json>] \
      [--md <9步完整版.md>] [--content <content.json>] [--report <最终报告.html>]
  # A股 ONLINE 档：无本地 CSV，直接在线拉十年年报并跑完整闭环
  orchestrate.py --online-a 601869 --out <产出dir> [--years 10] \
      [--forecast <csv>] [--md <9步MD>] [--content <content.json>] [--report <最终HTML>]
"""
import os
import sys
import glob
import subprocess


SK = os.path.dirname(os.path.abspath(__file__))


def run(script, *args, fatal=True):
    """执行子脚本。fatal=True 时失败立即阻断整条流水线。"""
    cmd = [sys.executable, os.path.join(SK, script)] + list(args)
    print(f"\n$ python {script} {' '.join(args)}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
    except OSError as e:
        print('  ❌ 无法启动: %s' % e, file=sys.stderr)
        if fatal:
            sys.exit(1)
        return False
    if r.stdout:
        print(r.stdout.rstrip())
    if r.returncode != 0:
        print(f"  ❌ 返回码 {r.returncode}")
        if r.stderr:
            print('  STDERR:', r.stderr.rstrip())
        if fatal:
            print('\n❌ 流水线在 %s 处阻断，未产出可信结果。' % script, file=sys.stderr)
            sys.exit(1)
        return False
    return True


def find_file(d, patterns, exts=('.csv', '.xlsx', '.xls')):
    for p in patterns:
        hit = sorted(glob.glob(os.path.join(d, p)))
        hit = [h for h in hit if os.path.splitext(h)[1].lower() in exts]
        if hit:
            return hit[0]
    return None


def arg(args, i, flag):
    if i + 1 >= len(args) or args[i + 1].startswith('--'):
        sys.exit('❌ %s 缺少参数值' % flag)
    return args[i + 1]


def main():
    args = sys.argv[1:]
    in_dir = out_dir = forecast = aliases = md = content = report = None
    online_a = years = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--in':
            in_dir = arg(args, i, a); i += 2
        elif a == '--out':
            out_dir = arg(args, i, a); i += 2
        elif a == '--forecast':
            forecast = arg(args, i, a); i += 2
        elif a == '--aliases':
            aliases = arg(args, i, a); i += 2
        elif a == '--md':
            md = arg(args, i, a); i += 2
        elif a == '--content':
            content = arg(args, i, a); i += 2
        elif a == '--report':
            report = arg(args, i, a); i += 2
        elif a == '--online-a':
            online_a = arg(args, i, a); i += 2
        elif a == '--years':
            years = arg(args, i, a); i += 2
        else:
            i += 1
    if not out_dir:
        sys.exit('用法: orchestrate.py --in <源数据dir> --out <产出dir> '
                 '[--forecast <csv>] [--aliases <json>] [--md <9步MD>] '
                 '[--content <content.json>] [--report <最终HTML>]\n'
                 '或 A股 ONLINE 档: orchestrate.py --online-a 601869 --out <产出dir> [--years 10]')
    if not in_dir and not online_a:
        sys.exit('❌ 需提供 --in <源数据dir> 或 --online-a <A股代码>')
    os.makedirs(out_dir, exist_ok=True)

    if online_a:
        in_dir = os.path.join(out_dir, '_online_input')
        os.makedirs(in_dir, exist_ok=True)
        print('=== 模块 -1: A股 ONLINE 在线拉数 (东财 F10 年报三表) ===')
        a_pull = [online_a, '--out', in_dir]
        if years:
            a_pull += ['--years', years]
        run('build_online_puller.py', *a_pull)
        print('  ✅ 在线三表 → %s' % in_dir)

    tmp = os.path.join(out_dir, '_csv')
    os.makedirs(tmp, exist_ok=True)

    print('=== 模块0: 输入适配 (xlsx/xls/csv → 标准宽表) ===')
    bs = find_file(in_dir, ['*资产负债表*', '*balance*'])
    ist = find_file(in_dir, ['*利润表*', '*income*'])
    cf = find_file(in_dir, ['*现金流量表*', '*cash*'])
    if not (bs and ist and cf):
        sys.exit('❌ 三张报表缺失 (需 资产负债表/利润表/现金流量表)')
    for f in (bs, ist, cf):
        run('convert_input.py', f, '--out', tmp)
    bs_csv = os.path.join(tmp, os.path.splitext(os.path.basename(bs))[0] + '.csv')
    ist_csv = os.path.join(tmp, os.path.splitext(os.path.basename(ist))[0] + '.csv')
    cf_csv = os.path.join(tmp, os.path.splitext(os.path.basename(cf))[0] + '.csv')

    print('\n=== 模块1: 合并行防御 (仅合并行无子行才修) ===')
    run('merge_line_fix.py', bs_csv, '--out', tmp,
        '--report', os.path.join(out_dir, 'merge_report.json'), fatal=False)

    print('\n=== 核心: build_metrics (不动) ===')
    run('build_metrics.py', bs_csv, ist_csv, cf_csv, out_dir)
    output_csv = os.path.join(out_dir, 'output.csv')

    print('\n=== 模块2: 业务构成 + 口径衔接 ===')
    prod = find_file(in_dir, ['*按产品*', '*按项目*', '*segment*'])
    reg = find_file(in_dir, ['*按地区*', '*region*'])
    if prod and reg:
        a = [output_csv, '--product', prod, '--region', reg]
        if aliases:
            a += ['--aliases', aliases]
        a += ['--out', output_csv]
        run('build_segment.py', *a, fatal=False)
    else:
        print('  ⏭️  缺 按产品/按地区 文件, 跳过')

    print('\n=== 模块3: 员工构成注入 ===')
    emp = find_file(in_dir, ['*员工*', '*employee*', '*headcount*'])
    if emp:
        run('build_headcount.py', output_csv, '--emp', emp, '--out', output_csv, fatal=False)
    else:
        print('  ⏭️  缺 员工构成 文件, 跳过')

    print('\n=== 模块4: 前瞻一致预期 ===')
    if forecast and os.path.exists(forecast):
        run('build_forecast.py', forecast, '--out', out_dir, '--output-csv', output_csv, fatal=False)
    else:
        print('  ⏭️  缺 --forecast <forecast_input.csv>, 跳过')

    print('\n=== 模块5: 强校验 harness ===')
    run('validate_output.py', output_csv, '--src', tmp,
        '--report', os.path.join(out_dir, 'validate_report.md'))

    print('\n=== 模块6: 口径自证 (追加 data_status.md) ===')
    status_md = os.path.join(out_dir, 'data_status.md')
    if os.path.exists(status_md) and os.path.exists(bs_csv):
        run('build_caliber_note.py', '--bs', bs_csv, '--output', output_csv,
            '--status', status_md, fatal=False)
    else:
        print('  ⏭️  缺 data_status.md 或 资产负债表, 跳过口径说明')

    print('\n=== 模块7: 图表数据 (report_data.json + report_prefilled.html) ===')
    peer = find_file(out_dir, ['*peer_comparison*']) or find_file(in_dir, ['*peer_comparison*'])
    a7 = [output_csv, '--out', out_dir]
    if peer:
        a7 += ['--peer', peer]
    run('build_report_data.py', *a7)

    print('\n=== 模块8: 9 步正文内容质检 ===')
    if md and os.path.exists(md):
        run('validate_content.py', md, '--strict')
    else:
        print('  ⏭️  缺 --md <9步完整版.md>, 跳过内容质检（交付前建议补上）')

    print('\n=== 模块9: 最终 HTML (HYDRO PAPER 皮肤 + 交付门禁) ===')
    if content and os.path.exists(content):
        final = report or os.path.join(out_dir, '七步财报分析报告.html')
        run('render_report.py', '--data', content,
            '--prefilled', os.path.join(out_dir, 'report_prefilled.html'),
            '--out', final)
        print('\n✅ 流水线完成（含最终 HTML）: %s' % final)
    else:
        print('  ⏭️  缺 --content <content.json>，停在 report_prefilled.html（中间稿）')
        print('     生成最终报告：python3 render_report.py --data <content.json> '
              '--prefilled <report_prefilled.html> --out <报告.html>')
        print('\n✅ 流水线完成（中间产物）: %s' % out_dir)


if __name__ == '__main__':
    main()
