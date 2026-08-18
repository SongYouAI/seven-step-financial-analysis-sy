#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块5：强校验 harness (seven-step-metrics-csv v3.0)
===================================================
可选增强校验层, 对核心 build_metrics.py 自带校验(资产平衡/增长率/平均边界)做"补强",
不替代、不重复写 data_status 核心段。

覆盖:
  - 列数严格 13(数据行)/ 表头 14 / LF 行尾统一 / 无 BOM;
  - 第四步 明细和=合计(产品/地区, 分层阈值), 占比加总≈100%(弱告警);
  - 员工 职能合计=学历合计=职工总数, 技术≠研发相加;
  - 应收合并行口径一致(应收账款+应收票据 vs 应收票据及应收账款, 差异>1%告警,
    验证模块1未破坏子行结构)。
输出: 校验报告(打印 + 可选写 validate_report.md)。失败项供 data_status「校验异常」追加。
零回归: 只读校验, 不改写 output.csv / 核心逻辑。
"""
import csv
import sys
import os


def _read_csv(path):
    with open(path, encoding='utf-8-sig') as f:
        return [list(r) for r in csv.reader(f)]


def _get_row(rows, name):
    for r in rows:
        if r and r[0] == name:
            return r
    return None


def _num(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _years(rows):
    return [h for h in rows[0][1:] if h and str(h).strip().endswith('年年报')]


def check_structure(rows, raw_bytes):
    rep = []
    # 表头 14 列
    n = len(_years(rows))
    rep.append(('表头列数=N+4', len(rows[0]) == n + 4, f'实际{len(rows[0])} (N={n})'))
    # 数据行/标题行 N+3 列 (动态, 支持任意年份数)
    bad_rows = [i for i, r in enumerate(rows[1:], 1) if len(r) != n + 3]
    rep.append(('数据行/标题行均N+3列', len(bad_rows) == 0, f'异常行数{len(bad_rows)}' + (f':{bad_rows[:5]}' if bad_rows else '')))
    # BOM
    has_bom = raw_bytes[:3] == b'\xef\xbb\xbf'
    rep.append(('无BOM', not has_bom, '有BOM' if has_bom else 'ok'))
    # LF 行尾统一 (无 CRLF)
    crlf = b'\r\n' in raw_bytes
    rep.append(('LF行尾统一(无CRLF)', not crlf, '含CRLF' if crlf else 'ok'))
    return rep


def check_segment(rows, years):
    rep = []
    # 产品明细和=合计
    total_p = _get_row(rows, '营业收入合计(产品)')
    # 用更稳的方式: 收集所有 产品 -收入 行 (排除 合计 行与 地区行)
    # 地区行以 境内/境外 开头
    def sum_lines(prefix_filter):
        s = [0.0] * len(years)
        for r in rows:
            if not r:
                continue
            nm = r[0]
            if nm.endswith('-收入') and prefix_filter(nm):
                for i, y in enumerate(years):
                    v = _num(r[i + 1]) if i + 1 < len(r) else None
                    if v is not None:
                        s[i] += v
        return s

    def is_product(nm):
        return nm.endswith('-收入') and nm.split('-')[0] not in ('境内', '境外') and '合计' not in nm

    def is_region(nm):
        base = nm.split('-')[0]
        return nm.endswith('-收入') and base in ('境内', '境外') and '合计' not in nm

    sp = sum_lines(is_product)
    sr = sum_lines(is_region)
    if total_p:
        tp = [_num(total_p[i + 1]) or 0.0 for i in range(len(years))]
        dev = [abs(sp[i] - tp[i]) / abs(tp[i]) if tp[i] else 0 for i in range(len(years))]
        ok = max(dev) < 0.05 if dev else True
        rep.append(('第四步·产品明细和≈合计(<5%容差)', ok, f'最大偏差{round(max(dev)*100,3) if dev else 0}%' if dev else ''))
    if total_r := _get_row(rows, '营业收入合计(地区)'):
        tr = [_num(total_r[i + 1]) or 0.0 for i in range(len(years))]
        dev = [abs(sr[i] - tr[i]) / abs(tr[i]) if tr[i] else 0 for i in range(len(years))]
        ok = max(dev) < 0.05 if dev else True
        rep.append(('第四步·地区明细和≈合计(<5%容差)', ok, f'最大偏差{round(max(dev)*100,3) if dev else 0}%' if dev else ''))
    # 占比加总≈100% (弱告警)
    for label, prefix_filter in (('产品', is_product), ('地区', is_region)):
        pct_lines = [r for r in rows if r and r[0].endswith('-收入占比') and prefix_filter(r[0])]
        if pct_lines:
            n = len(years)
            tot = [0.0] * n
            for r in pct_lines:
                for i in range(n):
                    v = _num(r[i + 1])
                    if v is not None:
                        tot[i] += v
            dev = [abs(tot[i] - 100) for i in range(n)]
            warn = max(dev) > 5 if dev else False
            rep.append((f'第四步·{label}占比加总≈100%(>5%告警)', not warn, f'最大{round(max(dev),2) if dev else 0}%' if dev else ''))
    return rep


def check_employee(rows, years):
    rep = []
    emp = _get_row(rows, '员工构成（按专业 / 学历 / 人均派生）')
    if not emp:
        return rep  # 无员工块则跳过
    def getv(name):
        r = _get_row(rows, name)
        return [_num(r[i + 1]) if r and i + 1 < len(r) else None for i in range(len(years))]
    tot = getv('职工总数')
    # 守卫: 员工数据全空(注入失败/年份轴错位)必须判失败, 禁止"空对空"假通过
    if not any(t is not None for t in tot):
        rep.append(('员工·数据已注入(职工总数非空)', False, '职工总数全空, 注入失败/年份轴错位'))
        return rep
    func_keys = ['生产人员', '销售人员', '财务人员', '技术人员', '行政管理人员']
    edu_keys = ['博士', '硕士', '本科', '大专']
    fs = [0.0] * len(years)
    es = [0.0] * len(years)
    fs_present = [False] * len(years)
    es_present = [False] * len(years)
    for k in func_keys:
        v = getv(k)
        for i in range(len(years)):
            if v[i] is not None:
                fs[i] += v[i]
                fs_present[i] = True
    for k in edu_keys:
        v = getv(k)
        for i in range(len(years)):
            if v[i] is not None:
                es[i] += v[i]
                es_present[i] = True
    # 仅对"源提供了明细"的年份做闭合校验; 缺口年(明细全空)跳过, 不假失败
    fdev = [abs(fs[i] - tot[i]) / abs(tot[i]) for i in range(len(years))
            if tot[i] is not None and fs_present[i]]
    edev = [abs(es[i] - tot[i]) / abs(tot[i]) for i in range(len(years))
            if tot[i] is not None and es_present[i]]
    fgap = [years[i] for i in range(len(years)) if tot[i] is not None and not fs_present[i]]
    egap = [years[i] for i in range(len(years)) if tot[i] is not None and not es_present[i]]
    rep.append(('员工·职能合计=职工总数(<1%,源缺年跳过)', max(fdev) < 0.01 if fdev else True, f'最大{round(max(fdev)*100,3)}%' if fdev else '全部源缺跳过'))
    rep.append(('员工·学历合计=职工总数(<1%,源缺年跳过)', max(edev) < 0.01 if edev else True, f'最大{round(max(edev)*100,3)}%' if edev else '全部源缺跳过'))
    if fgap:
        rep.append(('员工·专业构成源缺(跳过校验)', True, f'源缺: {fgap}'))
    if egap:
        rep.append(('员工·学历构成源缺(跳过校验)', True, f'源缺: {egap}'))
    # 技术≠研发相加: 不应同时存在 技术人员 与 研发人员 行(同源时已排除研发)
    has_tech = _get_row(rows, '技术人员') is not None
    has_rd = _get_row(rows, '研发人员') is not None
    rep.append(('员工·技术≠研发重复相加(不同源才并列)', not (has_tech and has_rd), '技术/研发并存(同源应仅技术)' if (has_tech and has_rd) else 'ok'))
    return rep


def check_receivable(rows, src_csv_dir=None):
    rep = []
    ar = _get_row(rows, '应收账款')
    ar_note = _get_row(rows, '应收票据')
    ar_merged = _get_row(rows, '应收票据及应收账款')
    if ar and ar_note and ar_merged:
        # 取第一年对比 (左新)
        def vv(r):
            for i in range(1, len(r)):
                x = _num(r[i])
                if x is not None:
                    return x
            return None
        a = vv(ar); b = vv(ar_note); m = vv(ar_merged)
        if a is not None and b is not None and m is not None:
            diff = abs((a + b) - m) / abs(m) if m else 0
            rep.append(('应收·子行求和≈合并行(<1%,验证模块1未破坏子行)', diff < 0.01, f'偏差{round(diff*100,3)}%'))
    return rep


def validate(output_csv, src_dir=None):
    with open(output_csv, 'rb') as f:
        raw = f.read()
    rows = _read_csv(output_csv)
    years = _years(rows)
    report = {}
    report['structure'] = check_structure(rows, raw)
    report['segment'] = check_segment(rows, years)
    report['employee'] = check_employee(rows, years)
    report['receivable'] = check_receivable(rows, src_dir)
    return report


def print_report(report):
    all_ok = True
    for sec, items in report.items():
        print(f"[{sec}]")
        for name, ok, detail in items:
            mark = '✅' if ok else '⚠️ '
            if not ok:
                all_ok = False
            print(f"  {mark} {name}  ({detail})")
    print()
    print("  ✅ 全部通过" if all_ok else "  ⚠️  存在告警项(见上)")


def main():
    args = sys.argv[1:]
    out = src = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--src':
            src = args[i + 1]; i += 2
        elif a == '--report':
            out = args[i + 1]; i += 2
        else:
            if out is None and not a.startswith('--'):
                out = a
            i += 1
    if not out:
        sys.exit("用法: validate_output.py <output.csv> [--src <源csv目录>] [--report <md>]")
    # 重新取 output.csv 路径 (上面误把第一个非flag当 out)
    out_csv = None
    for a in args:
        if not a.startswith('--') and a.endswith('.csv'):
            out_csv = a
            break
    if not out_csv:
        sys.exit("用法: validate_output.py <output.csv> [--src <源csv目录>] [--report <md>]")
    report = validate(out_csv, src)
    print_report(report)
    if '--report' in args:
        idx = args.index('--report')
        rp = args[idx + 1]
        lines = ['# 强校验报告 (模块5)\n']
        for sec, items in report.items():
            lines.append(f'## {sec}\n')
            for name, ok, detail in items:
                lines.append(f'- {"✅" if ok else "⚠️"} {name} ({detail})\n')
        with open(rp, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"  报告已写: {rp}")


if __name__ == '__main__':
    main()
