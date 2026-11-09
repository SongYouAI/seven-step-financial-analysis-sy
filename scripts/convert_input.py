#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块0：输入适配层 (seven-step-metrics-csv v3.0)
=========================================================
自动识别 .csv / .xlsx / .xls，统一转成 build_metrics.py 要求的内部标准 CSV：
    表头: 科目, YYYY年年报, YYYY年年报, ...   (左新右旧, 仅保留年报列)
    数据: 科目名, 值1, 值2, ...
特性:
  - 年份标签归一: 2025年年报 / 2025-12-31 / 2025/12/31 / 2025  ->  YYYY年年报
  - 跳过半年报列 (06-30 / 半年度 / 中报 / H1 / Q2)
  - 跳过前导元数据行 (数据来源 / 单位 / 报告期 等) 与全空行
  - 依赖 openpyxl(xlsx) / xlrd==1.2.0(老xls)；离线缺失时明确提示降级
零回归: 本脚本只产出符合 build_metrics 契约的 CSV, 不改动核心。
"""
import csv
import os
import re
import sys
import glob


# ---------------------------------------------------------------------
# 读取层
# ---------------------------------------------------------------------
def read_sheet(path):
    low = path.lower()
    if low.endswith(('.xlsx', '.xlsm')):
        try:
            import openpyxl
        except ImportError:
            sys.exit("❌ 需要 openpyxl 读取 xlsx。请运行: pip install openpyxl")
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb.worksheets[0]
        return [[c for c in row] for row in ws.iter_rows(values_only=True)]
    if low.endswith('.xls'):
        try:
            import xlrd
        except ImportError:
            sys.exit("❌ 需要 xlrd==1.2.0 读取老 .xls。请运行: pip install xlrd==1.2.0")
        wb = xlrd.open_workbook(path)
        ws = wb.sheet_by_index(0)
        return [[ws.cell_value(r, c) for c in range(ws.ncols)] for r in range(ws.nrows)]
    if low.endswith('.csv'):
        with open(path, encoding='utf-8-sig') as f:
            raw = [list(r) for r in csv.reader(f)]
        # 理杏仁(lixinger)导出值带前导 '=' (如 =981400 / ="600436")，去除后还原为数值/文本
        for row in raw:
            for i, c in enumerate(row):
                if isinstance(c, str) and c.startswith('='):
                    row[i] = c[1:].strip().strip('"').strip("'")
        return raw
    sys.exit(f"❌ 不支持的文件类型: {path}")


# ---------------------------------------------------------------------
# 年份标签归一
# ---------------------------------------------------------------------
# 非年报期特征：一季报(03-31) / 半年报(06-30) / 三季报(09-30) 及其文字写法。
# 旧版只拦 06-30 / 09-30 / H1 / Q2，一季报列会被误判成年报，与真年报撞成重复列。
_NON_ANNUAL = (r'03[-/]31|06[-/]30|09[-/]30|3月31|6月30|9月30|'
               r'半年度|中报|半年报|一季|三季|前三季|季报|[HQ][1-4](?![0-9])')


def norm_year(cell):
    if cell is None:
        return None
    s = str(cell).strip()
    if not re.search(r'\d{4}', s):
        return None
    if re.search(_NON_ANNUAL, s, re.I):
        return None
    # 8 位纯日期 YYYYMMDD：仅 12 月视为年报，旧正则会回溯匹配出「0630年年报」
    m8 = re.fullmatch(r'(\d{4})(\d{2})(\d{2})', s)
    if m8:
        return f"{m8.group(1)}年年报" if m8.group(2) == '12' else None
    # 锚定行首年份，避免 20250630 之类的回溯误匹配
    m = re.match(r'^(\d{4})', s)
    if not m:
        return None
    return f"{m.group(1)}年年报"


def find_header(rows):
    best_i, best_n = -1, -1
    for i, row in enumerate(rows[:12]):
        n = sum(1 for c in row if norm_year(c))
        if n > best_n:
            best_n, best_i = n, i
    return best_i, best_n


META_HINTS = ('数据来源', '单位：', '单位:', '报告期', '币种', '合并报表',
              '上市公司', '证券代码', '证券简称', '报表类型', '说明：', '注：')


def is_meta(name):
    if not name:
        return False
    return any(h in name for h in META_HINTS)


def convert_one(path, out_dir):
    rows = read_sheet(path)
    hi, n_year = find_header(rows)
    if hi < 0:
        print(f"  ⚠️  {os.path.basename(path)}: 未找到年份表头, 跳过")
        return None
    header = rows[hi]
    # 同年多列去重：优先保留明确标「12-31 / 年报」的列，避免季报列覆盖真年报
    seen = {}
    for ci, c in enumerate(header):
        y = norm_year(c)
        if not y:
            continue
        explicit = bool(re.search(r'12[-/]31|1231|年年报|年报', str(c)))
        if y not in seen or (explicit and not seen[y][2]):
            seen[y] = (ci, y, explicit)
    year_cols = [(ci, y) for ci, y, _ in seen.values()]
    if not year_cols:
        print(f"  ⚠️  {os.path.basename(path)}: 表头无有效年份列, 跳过")
        return None
    year_cols.sort(key=lambda x: x[1], reverse=True)  # 左新右旧
    years = [y for _, y in year_cols]

    out_rows = []
    for ri in range(hi + 1, len(rows)):
        row = rows[ri]
        if not row:
            continue
        name = row[0]
        if name is None or str(name).strip() == '':
            continue
        name = str(name).strip()
        if is_meta(name):
            continue
        vals = []
        for ci, _ in year_cols:
            v = row[ci] if ci < len(row) else ''
            if v is None or v == '':
                vals.append('')
            else:
                try:
                    raw = str(v).strip().strip('"').replace(',', '').replace('%', '')
                    neg = raw.startswith('(') and raw.endswith(')')
                    if neg:
                        raw = raw[1:-1]
                    num = float(raw)
                    vals.append(str(-num if neg else num))
                except (ValueError, TypeError):
                    vals.append('')
        if all(v == '' for v in vals):
            continue
        out_rows.append([name] + vals)

    base = os.path.splitext(os.path.basename(path))[0]
    out_path = os.path.join(out_dir, base + '.csv')
    os.makedirs(out_dir, exist_ok=True)
    # BOM：Excel 直接打开中文表头不乱码；下游统一用 utf-8-sig 读取，兼容
    with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['科目'] + years)
        for r in out_rows:
            w.writerow(r)
    print(f"  ✅ {os.path.basename(path)} -> {os.path.basename(out_path)} "
          f"({len(out_rows)} 行, {len(years)} 年: {years[0]}..{years[-1]})")
    return out_path


def main():
    args = sys.argv[1:]
    out_dir = None
    files = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--out':
            if i + 1 >= len(args):
                sys.exit('❌ --out 缺少目录参数')
            out_dir = args[i + 1]
            i += 2
            continue
        if os.path.isdir(a):
            for ext in ('*.xlsx', '*.xls', '*.csv'):
                files.extend(sorted(glob.glob(os.path.join(a, ext))))
        else:
            files.append(a)
        i += 1
    if not files:
        sys.exit("用法: convert_input.py <文件1> [文件2...] [--out <目录>] | <目录>")
    if out_dir is None:
        out_dir = os.path.dirname(os.path.abspath(files[0])) or '.'
    print(f"模块0 输入适配: {len(files)} 个文件 -> {out_dir}")
    ok = 0
    for f in files:
        if not os.path.exists(f):
            print(f"  ⚠️  不存在: {f}")
            continue
        if convert_one(f, out_dir):
            ok += 1
    print(f"完成: {ok}/{len(files)} 成功转换")
    if ok == 0:
        print('❌ 全部文件转换失败', file=sys.stderr)
        sys.exit(1)
    if ok < len(files):
        print('  ⚠️  有 %d 个文件被跳过（多为辅助表/无年份表头），请确认不是三张主表'
              % (len(files) - ok), file=sys.stderr)


if __name__ == '__main__':
    main()
