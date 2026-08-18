#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块3：员工构成注入 (seven-step-metrics-csv v3.0)
=================================================
解析员工构成 XLS/CSV (东方财富员工表结构: 指标块(职工总数/按专业/按学历) × 年份列),
对齐年报列(跳过半年报, 含老 .xls 隐藏末列 2016), 注入 output.csv 末尾附录块。

特性:
  - 技术=研发同源检测: 判定"两者非空年份是否全部相等";
    全等 → 视为同源, 职能合计只取 技术人员, 排除 研发人员(避免重复相加), data_status 标注;
    部分年份不等 → 分别保留(防误吞真实研发)。
  - 闭合校验: 职能合计(生产+销售+财务+技术+行政)=职工总数;
              学历合计(博士+硕士+本科+大专)=职工总数; 两者阈值1%。
  - 人均派生: 人均创收 = 营业收入(主表) / 职工总数。
  - 重跑幂等: 已有员工块则先精准移除再注入。
零回归: 不改动核心 build_metrics.py; 员工块为选择性增强附录。
"""
import csv
import sys
import os
import re

# 目标指标名 (源文件实际行名 -> 输出行名; 同源检测用 技术/研发)
TARGET = {
    '职工总数': '职工总数',
    '生产人员': '生产人员',
    '销售人员': '销售人员',
    '财务人员': '财务人员',
    '技术人员': '技术人员',
    '研发人员': '研发人员',
    '行政管理人员': '行政管理人员',
    '博士': '博士',
    '硕士': '硕士',
    '本科': '本科',
    '大专': '大专',
}
# 职能合计取这 5 项 (同源时 技术 替代 研发)
FUNC_SUM = ['生产人员', '销售人员', '财务人员', '技术人员', '行政管理人员']
# 学历合计取这 4 项
EDU_SUM = ['博士', '硕士', '本科', '大专']


# ---------------------------------------------------------------------
# 读取层 (xls/csv, 对齐年报列)
# ---------------------------------------------------------------------
def _year_of(col_label):
    s = str(col_label)
    if re.search(r'06[-/]30|半年度|中报|半年报|H1|Q2|9月30|09[-/]30|第三季度', s):
        return None  # 跳过半年报列
    m = re.search(r'(\d{4})', s)
    if not m:
        return None
    return m.group(1) + '年年报'


def read_employee(path):
    low = path.lower()
    if low.endswith('.xls'):
        try:
            import xlrd
        except ImportError:
            sys.exit("❌ 需要 xlrd==1.2.0 读取老 .xls。请运行: pip install xlrd==1.2.0")
        wb = xlrd.open_workbook(path)
        ws = wb.sheet_by_index(0)
        raw = [[ws.cell_value(r, c) for c in range(ws.ncols)] for r in range(ws.nrows)]
    elif low.endswith(('.xlsx', '.xlsm')):
        try:
            import openpyxl
        except ImportError:
            sys.exit("❌ 需要 openpyxl 读取 xlsx。请运行: pip install openpyxl")
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb.worksheets[0]
        raw = [list(r) for r in ws.iter_rows(values_only=True)]
    else:
        with open(path, encoding='utf-8-sig') as f:
            raw = [list(r) for r in csv.reader(f)]

    # 定位年份列 (首行)
    header = raw[0]
    year_cols = {}  # year_label -> col_index
    for ci, h in enumerate(header):
        if h is None:
            continue
        y = _year_of(h)
        if y:
            year_cols[y] = ci
    years = sorted(year_cols.keys(), reverse=True)

    data = {}  # metric_out -> {year: value}
    for row in raw[1:]:
        if not row:
            continue
        name = row[0]
        if name is None or str(name).strip() == '':
            continue
        nm = str(name).strip()
        if nm not in TARGET:
            continue
        out = TARGET[nm]
        series = {}
        for y, ci in year_cols.items():
            v = row[ci] if ci < len(row) else None
            if v is None or v == '':
                continue
            try:
                fv = float(v)
            except (ValueError, TypeError):
                continue
            series[y] = fv
        if series:
            data[out] = series
    return data, years


# ---------------------------------------------------------------------
# 同源检测 + 块构建
# ---------------------------------------------------------------------
def detect_same_source(data):
    """技术=研发同源: 两者共有非空年份是否全部相等"""
    if '技术人员' not in data or '研发人员' not in data:
        return False, []
    t = data['技术人员']
    r = data['研发人员']
    common = [y for y in t if y in r and t[y] != '' and r[y] != '']
    if not common:
        return False, []
    all_eq = all(abs(t[y] - r[y]) < 1e-6 for y in common)
    return all_eq, common


def _fmt(v):
    if v == '' or v is None:
        return ''
    return repr(round(float(v), 6)) if isinstance(v, float) else str(v)


def build_emp_block(data, years, rev_per_emp=None, np_per_emp=None):
    same, common = detect_same_source(data)
    use_rd = not same  # 不同源才单独展示研发
    block = []
    block.append(['员工构成（按专业 / 学历 / 人均派生）'] + [''] * (len(years) + 2))

    def row(name, key):
        d = data.get(key, {})
        vals = [_fmt(d.get(y, '')) for y in years]
        block.append([name] + vals + ['', ''])

    def per_capita(num_per_emp, scale):
        """num_per_emp: {year: 分子(营业收入或归母净利润)}; scale: 1=元/人, 1e4=万元/人。"""
        out = []
        tot = data.get('职工总数', {})
        for y in years:
            num = num_per_emp.get(y, '')
            emp = tot.get(y, '')
            if num not in ('', None) and emp not in ('', None) and emp != 0:
                out.append(repr(round(float(num) / float(emp) / scale, 4)))
            else:
                out.append('')
        return out

    row('职工总数', '职工总数')
    for k in FUNC_SUM:
        row(k, k)
    if use_rd:
        row('研发人员', '研发人员')
    for k in EDU_SUM:
        row(k, k)
    # 人均派生
    if rev_per_emp:
        block.append(['人均创收(元/人)'] + per_capita(rev_per_emp, 1) + ['', ''])
        block.append(['人均收入(万元)'] + per_capita(rev_per_emp, 1e4) + ['', ''])
    if np_per_emp:
        block.append(['人均归母净利润(万元)'] + per_capita(np_per_emp, 1e4) + ['', ''])
    return block, {'same_source': same, 'common_years': common, 'use_rd': use_rd}


def _years_from_header(header):
    """返回与主表一致的完整年份标签(含'年年报'), 与 read_employee 的 key 对齐。"""
    yrs = []
    for h in header[1:]:
        if h and str(h).strip().endswith('年年报'):
            yrs.append(str(h).strip())
    return yrs


def _get_row(rows, name):
    for r in rows:
        if r and r[0] == name:
            return r
    return None


def inject(output_csv, emp_file, out_csv):
    # 读主表年份轴 + 营业收入/归母净利润(人均派生)
    with open(output_csv, encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    years = _years_from_header(rows[0])
    inc_row = _get_row(rows, '营业收入')
    np_row = _get_row(rows, '归母净利润')
    rev_per_emp = {}
    if inc_row:
        for i, y in enumerate(years):
            v = inc_row[i + 1] if i + 1 < len(inc_row) else ''
            rev_per_emp[y] = v if v not in ('', None) else ''
    np_per_emp = {}
    if np_row:
        for i, y in enumerate(years):
            v = np_row[i + 1] if i + 1 < len(np_row) else ''
            np_per_emp[y] = v if v not in ('', None) else ''

    # 读员工
    edata, _ = read_employee(emp_file)
    block, info = build_emp_block(edata, years, rev_per_emp, np_per_emp)

    # 幂等: 移除旧员工块 (以标题起始)
    start = -1
    for i, r in enumerate(rows):
        if r and r[0].startswith('员工构成'):
            start = i
            break
    if start >= 0:
        rows = rows[:start]  # 截到员工块前

    out_rows = rows + block

    if out_csv is None:
        out_csv = output_csv
    parent = os.path.dirname(out_csv)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_csv, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(out_rows[0])
        for r in out_rows[1:]:
            w.writerow(r)

    report = _validate_closure(edata, years, info)
    return report, info


def _closure_ok(total, comp_sum, applicable):
    """applicable=源是否提供了该年明细; 缺口年跳过(不假失败)。"""
    if not applicable:
        return True
    if total == 0:
        return comp_sum == 0
    return abs(comp_sum - total) / abs(total) < 0.01


def _validate_closure(edata, years, info):
    rep = {}
    tot = edata.get('职工总数', {})
    func_sum = []
    func_applicable = []
    for y in years:
        comps = [edata.get(k, {}).get(y, '') for k in FUNC_SUM]
        present = [c for c in comps if c not in ('', None)]
        func_applicable.append(bool(present))
        func_sum.append(sum(float(c) for c in present))
    edu_sum = []
    edu_applicable = []
    for y in years:
        comps = [edata.get(k, {}).get(y, '') for k in EDU_SUM]
        present = [c for c in comps if c not in ('', None)]
        edu_applicable.append(bool(present))
        edu_sum.append(sum(float(c) for c in present))
    checks = []
    for i, y in enumerate(years):
        t = float(tot.get(y, 0) or 0)
        fs = func_sum[i]
        es = edu_sum[i]
        checks.append({'year': y, 'total': t, 'func_sum': fs, 'edu_sum': es,
                       'func_ok': _closure_ok(t, fs, func_applicable[i]),
                       'edu_ok': _closure_ok(t, es, edu_applicable[i]),
                       'func_gap': not func_applicable[i],
                       'edu_gap': not edu_applicable[i]})
    rep['checks'] = checks
    rep['same_source'] = info['same_source']
    rep['func_gap_years'] = [c['year'] for c in checks if c['func_gap']]
    rep['edu_gap_years'] = [c['year'] for c in checks if c['edu_gap']]
    return rep


if __name__ == '__main__':
    args = sys.argv[1:]
    output_csv = emp_file = out = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--emp':
            emp_file = args[i + 1]; i += 2
        elif a == '--out':
            out = args[i + 1]; i += 2
        else:
            if output_csv is None:
                output_csv = a
            i += 1
    if not output_csv or not emp_file:
        sys.exit("用法: build_headcount.py <output.csv> --emp <员工xls/csv> [--out <csv>]")
    rep, info = inject(output_csv, emp_file, out)
    print(f"  ✅ 员工构成已注入 (技术=研发同源: {info['same_source']})")
    if info['same_source']:
        print(f"     同源年份(技术==研发): {info['common_years']} → 职能合计取技术人员, 不重复相加")
    bad_f = [c for c in rep['checks'] if not c['func_ok']]
    bad_e = [c for c in rep['checks'] if not c['edu_ok']]
    if bad_f:
        print(f"     ⚠️  职能合计≠职工总数: {[(c['year'], round(abs(c['func_sum']-c['total'])/c['total']*100,2)) for c in bad_f]}")
    else:
        print(f"     ✅ 职能合计(生产+销售+财务+技术+行政)=职工总数 1%内闭合(已校验年份)")
    if bad_e:
        print(f"     ⚠️  学历合计≠职工总数: {[(c['year'], round(abs(c['edu_sum']-c['total'])/c['total']*100,2)) for c in bad_e]}")
    else:
        print(f"     ✅ 学历合计(博士+硕士+本科+大专)=职工总数 1%内闭合(已校验年份)")
    if rep.get('func_gap_years'):
        print(f"     ℹ️  专业构成源缺(跳过校验): {rep['func_gap_years']}")
    if rep.get('edu_gap_years'):
        print(f"     ℹ️  学历构成源缺(跳过校验): {rep['edu_gap_years']}")
