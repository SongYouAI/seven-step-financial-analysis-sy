#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
orchestrate.py — 七步财报分析 端到端编排 (v3.0)
=============================================
串联: 输入适配(模块0) → 合并行防御(模块1) → 核心主表(不动) →
      业务构成(模块2) → 员工构成(模块3) → 前瞻一致预期(模块4) → 强校验(模块5)

可选模块优雅跳过: 缺某输入文件/无接口时跳过对应模块, 不报错、不污染主表。
核心 build_metrics.py 一字不改(含其自带校验)。

用法:
  orchestrate.py --in <源数据dir> --out <产出dir> [--forecast <forecast_input.csv>] [--aliases <json>]
"""
import os
import sys
import glob
import subprocess


SK = os.path.dirname(os.path.abspath(__file__))


def run(script, *args):
    cmd = [sys.executable, os.path.join(SK, script)] + list(args)
    print(f"\n$ python {script} {' '.join(args)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout:
        print(r.stdout.rstrip())
    if r.returncode != 0:
        print(f"  ⚠️  返回码 {r.returncode}")
        if r.stderr:
            print("  STDERR:", r.stderr.rstrip())
    return r.returncode == 0


def find_file(d, patterns):
    for p in patterns:
        hit = sorted(glob.glob(os.path.join(d, p)))
        if hit:
            return hit[0]
    return None


def main():
    args = sys.argv[1:]
    in_dir = out_dir = forecast = aliases = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--in':
            in_dir = args[i + 1]; i += 2
        elif a == '--out':
            out_dir = args[i + 1]; i += 2
        elif a == '--forecast':
            forecast = args[i + 1]; i += 2
        elif a == '--aliases':
            aliases = args[i + 1]; i += 2
        else:
            i += 1
    if not in_dir or not out_dir:
        sys.exit("用法: orchestrate.py --in <源数据dir> --out <产出dir> [--forecast <csv>] [--aliases <json>]")
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, '_csv')
    os.makedirs(tmp, exist_ok=True)

    print("=== 模块0: 输入适配 (xlsx/xls → 标准CSV) ===")
    bs = find_file(in_dir, ['*资产负债表*', '*balance*'])
    ist = find_file(in_dir, ['*利润表*', '*income*'])
    cf = find_file(in_dir, ['*现金流量表*', '*cash*'])
    if not (bs and ist and cf):
        sys.exit("❌ 三张报表缺失 (需 资产负债表/利润表/现金流量表)")
    for f in (bs, ist, cf):
        run('convert_input.py', f, '--out', tmp)
    bs_csv = os.path.join(tmp, os.path.splitext(os.path.basename(bs))[0] + '.csv')
    ist_csv = os.path.join(tmp, os.path.splitext(os.path.basename(ist))[0] + '.csv')
    cf_csv = os.path.join(tmp, os.path.splitext(os.path.basename(cf))[0] + '.csv')

    print("\n=== 模块1: 合并行防御 (仅合并行无子行才修) ===")
    run('merge_line_fix.py', bs_csv, '--out', tmp, '--report', os.path.join(out_dir, 'merge_report.json'))

    print("\n=== 核心: build_metrics (不动) ===")
    run('build_metrics.py', bs_csv, ist_csv, cf_csv, out_dir)
    output_csv = os.path.join(out_dir, 'output.csv')

    print("\n=== 模块2: 业务构成 + 口径衔接 ===")
    prod = find_file(in_dir, ['*按产品*', '*按项目*', '*segment*'])
    reg = find_file(in_dir, ['*按地区*', '*region*'])
    if prod and reg:
        a = [output_csv, '--product', prod, '--region', reg]
        if aliases:
            a += ['--aliases', aliases]
        a += ['--out', output_csv]
        run('build_segment.py', *a)
    else:
        print("  ⏭️  缺 按产品/按地区 文件, 跳过")

    print("\n=== 模块3: 员工构成注入 ===")
    emp = find_file(in_dir, ['*员工*', '*employee*', '*headcount*'])
    if emp:
        run('build_headcount.py', output_csv, '--emp', emp, '--out', output_csv)
    else:
        print("  ⏭️  缺 员工构成 文件, 跳过")

    print("\n=== 模块4: 前瞻一致预期 ===")
    if forecast and os.path.exists(forecast):
        run('build_forecast.py', forecast, '--out', out_dir, '--output-csv', output_csv)
    else:
        print("  ⏭️  缺 --forecast <forecast_input.csv>, 跳过")

    print("\n=== 模块5: 强校验 harness ===")
    run('validate_output.py', output_csv, '--src', tmp, '--report', os.path.join(out_dir, 'validate_report.md'))

    print("\n=== 模块7: 图表数据自动生成 (report_data.json + report_prefilled.html) ===")
    run('build_report_data.py', output_csv, '--out', out_dir)

    print("\n=== 模块6: 口径自证 (追加 data_status.md 口径说明专节) ===")
    status_md = os.path.join(out_dir, 'data_status.md')
    if os.path.exists(status_md) and os.path.exists(bs_csv):
        run('build_caliber_note.py', '--bs', bs_csv, '--output', output_csv, '--status', status_md)
    else:
        print("  ⏭️  缺 data_status.md 或 资产负债表, 跳过口径说明")

    print(f"\n✅ 流水线完成. 产出目录: {out_dir}")


if __name__ == '__main__':
    main()
