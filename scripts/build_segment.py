#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块2：业务构成 + 口径衔接 (seven-step-metrics-csv v3.0)
=========================================================
直接解析原始「按产品(项目)分类 / 按地区分类」XLSX/CSV (东方财富分业务表结构)。
兼容两种格式:
  - 东财 xlsx 风格: 指标父行(无全角空格) + 业务行(全角空格缩进);
  - 东财分业务表 CSV 导出 (纵向堆叠块): 多个'合计'行分隔的块, 依次对应
    营业收入(总/境内/境外)/毛利率/收入占比, 行业务线无全角空格, 由块位置+数值特征判定。
产出第四步, 注入 output.csv 的 第三步 与 第五步 之间, 保留动态 N+3 列结构。

特性:
  - 口径别名字典 (references/segment_aliases.json): 种子含宁德映射
    {新名: [旧名...]}; 仅当 新名与旧名同年均存在 时, 旧名同期空值并入新名
    (新名优先); 合并后删除旧名, 避免重复展示; 无字典/未命中时降级不强行映射。
  - 闭合校验 (分层): 产品"合计"行营业总收入 对 利润表营业收入 阈值1%;
    各明细和=合计行 阈值放宽至5%仅告警不阻断 (分业务与合并营收常有抵销差异)。
  - 重跑幂等: 若 output.csv 已有第四步块, 先精准移除(只删第四步块, 保留第三步指标)再注入。
零回归: 不改动核心 build_metrics.py; 注入为选择性增强。
"""
import csv
import sys
import os
import json

# 产品展示优先级 (含 其他(补充) 作为兜底业务线)
PRODUCT_PRIORITY = ['动力电池系统', '储能电池系统', '电池材料及回收',
                    '电池矿产资源', '其他(补充)']
# 地区只展示境内/境外 (排除 境内地区/境外地区 重复口径)
REGION_PRIORITY = ['境内', '境外']
# 两类表共用跳过行
SKIP_LINES = {'合计', '其他业务', '平衡项目'}


# ---------------------------------------------------------------------
# 解析层 (直接读 xlsx)
# ---------------------------------------------------------------------
def _metric_key(a):
    s = a
    if '毛利率' in s:
        return '毛利率'
    if ('收入' in s and '比例' in s) or '收入构成' in s or '营业收入比例' in s:
        return '收入占比'
    if ('成本' in s and '比例' in s) or '成本构成' in s:
        return '成本占比'
    if '营业收入' in s:
        return '收入'
    if '营业成本' in s or '成本' in s:
        return '成本'
    if '毛利' in s:
        return '毛利'
    return None


def _load_rows(path):
    """按扩展名加载分业务表为行列表 (xlsx/xls/csv 通用)。"""
    low = path.lower()
    if low.endswith(('.xlsx', '.xlsm')):
        try:
            import openpyxl
        except ImportError:
            sys.exit("❌ 需要 openpyxl 读取分业务 xlsx。请运行: pip install openpyxl")
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb.worksheets[0]
        return list(ws.iter_rows(values_only=True))
    if low.endswith('.xls'):
        try:
            import xlrd
        except ImportError:
            sys.exit("❌ 需要 xlrd==1.2.0 读取分业务老 .xls。请运行: pip install xlrd==1.2.0")
        wb = xlrd.open_workbook(path)
        ws = wb.sheet_by_index(0)
        return [[ws.cell_value(r, c) for c in range(ws.ncols)] for r in range(ws.nrows)]
    if low.endswith('.csv'):
        with open(path, encoding='utf-8-sig') as f:
            return [list(r) for r in csv.reader(f)]
    sys.exit(f"❌ 不支持的分业务文件类型: {path}（支持 xlsx/xls/csv）")


def _to_float(v):
    """CSV/xlsx 单元格 -> float, 失败返回 None (兼容字符串/空值)。"""
    if v is None or v == '':
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _block_latest_total(block):
    """取块合计最新年份值 (年份字符串降序, 取最大)。"""
    if not block['total']:
        return 0.0
    y = max(block['total'].keys())  # '2025' > '2024' 字典序成立(4位年)
    return block['total'][y]


def _classify_blocks(blocks):
    """按数值特征+位置把堆叠块分成 营业收入 / 毛利率 / 收入占比。

    - 营业收入块: 合计为大额绝对值。东财分业务表默认 元 单位, 营收合计 > 100
      (百分比块 ≤ 100, 故以 100 为分界); 若所有块合计均 ≤ 100 (亿元单位小值,
      营收也可能 ≤100), 降级走位置判定: 首个块=营业收入(总)。
    - 毛利率块: 合计为 0~100 百分比且业务线和 ≠ 100。
    - 收入占比块: 合计 ≈ 100 且业务线和 ≈ 100。
    多个营业收入子块(总/境内/境外)只取第一个(总)。"""
    revenue, margin, share = [], None, None
    for b in blocks:
        tl = _block_latest_total(b)
        if tl > 100:
            revenue.append(b)
            continue
        s = sum(yv[max(yv.keys())] for _, yv in b['lines'] if yv)
        if abs(tl - 100) < 0.5 or abs(s - 100) < 3:
            if share is None:
                share = b
        else:
            if margin is None:
                margin = b
    # 亿元单位兜底: 完全没识别到营收块(营收也≤100)时, 位置判定
    if not revenue and blocks:
        revenue = [blocks[0]]
        for b in blocks[1:]:
            tl = _block_latest_total(b)
            s = sum(yv[max(yv.keys())] for _, yv in b['lines'] if yv)
            if abs(tl - 100) < 0.5 or abs(s - 100) < 3:
                if share is None:
                    share = b
            else:
                if margin is None:
                    margin = b
    return revenue, margin, share


def _read_segment_xlsx(rows, year_cols):
    """东财 xlsx 风格: 指标父行(无全角空格) + 业务行(全角空格缩进)。"""
    metric = None
    data = {}  # biz -> metric -> {year: value}
    for row in rows[1:]:
        if not row or row[0] is None:
            continue
        a = str(row[0])
        if '　' not in a and _metric_key(a):
            metric = _metric_key(a)
            continue
        if metric is None:
            continue
        if a.startswith('　'):
            biz = a.replace('　', '').strip()
            vals = {}
            for y, idx in year_cols.items():
                fv = _to_float(row[idx] if idx < len(row) else None)
                if fv is not None:
                    vals[y] = fv
            if vals:
                data.setdefault(biz, {}).setdefault(metric, {})
                for y, v in vals.items():
                    data[biz][metric].setdefault(y, v)
    return data


def _read_segment_stacked(rows, year_cols):
    """纵向堆叠块格式 (东财分业务表 CSV 导出): 多个'合计'行分隔的块,
    依次对应 营业收入(总/境内/境外)/毛利率/收入占比。行业务线无全角空格,
    指标由块位置+数值特征判定。返回 data[biz][metric][year]。"""
    blocks = []
    cur = None
    for row in rows[1:]:
        if not row or row[0] is None:
            continue
        a = str(row[0]).strip()
        if a == '':
            continue
        if a == '合计':
            if cur is not None:
                blocks.append(cur)
            cur = {'total': {}, 'lines': []}
            for y, idx in year_cols.items():
                fv = _to_float(row[idx] if idx < len(row) else None)
                if fv is not None:
                    cur['total'][y] = fv
        else:
            if cur is None:
                continue
            vals = {}
            for y, idx in year_cols.items():
                fv = _to_float(row[idx] if idx < len(row) else None)
                if fv is not None:
                    vals[y] = fv
            if vals:
                cur['lines'].append((a, vals))
    if cur is not None:
        blocks.append(cur)

    revenue, margin, share = _classify_blocks(blocks)
    data = {}
    if revenue:
        rev = revenue[0]
        data.setdefault('合计', {})['收入'] = dict(rev['total'])
        for biz, yv in rev['lines']:
            if biz in SKIP_LINES:
                continue
            data.setdefault(biz, {})['收入'] = yv
    if margin:
        for biz, yv in margin['lines']:
            if biz in SKIP_LINES:
                continue
            data.setdefault(biz, {})['毛利率'] = yv
    if share:
        for biz, yv in share['lines']:
            if biz in SKIP_LINES:
                continue
            data.setdefault(biz, {})['收入占比'] = yv
    return data


def _read_segment(path):
    rows = _load_rows(path)
    header = rows[0]
    year_cols = {}
    for i, h in enumerate(header):
        if h and str(h).strip().endswith('年年报'):
            year_cols[str(h).strip().replace('年年报', '')] = i
    years = sorted(year_cols.keys(), reverse=True)
    # 格式检测: 是否存在 指标父行 (东财 xlsx 风格)?
    has_metric_parent = any(
        row and row[0] is not None and '　' not in str(row[0]) and _metric_key(str(row[0]))
        for row in rows[1:]
    )
    if has_metric_parent:
        return _read_segment_xlsx(rows, year_cols), years
    return _read_segment_stacked(rows, year_cols), years


# ---------------------------------------------------------------------
# 口径字典合并 (合并后删除旧名, 避免重复展示)
# ---------------------------------------------------------------------
def apply_aliases(data, alias_path):
    if not alias_path or not os.path.exists(alias_path):
        return data, {}
    with open(alias_path, encoding='utf-8') as f:
        aliases = json.load(f)
    used = {}
    for new, olds in aliases.items():
        for old in olds:
            # 仅当 新名与旧名同年均存在 才合并 (旧名空值补入新名, 新名优先)
            if old in data and new in data:
                tgt = data[new]
                for m, yv in data[old].items():
                    tm = tgt.setdefault(m, {})
                    for y, v in yv.items():
                        if y not in tm:
                            tm[y] = v
                used.setdefault(new, []).append(old)
                del data[old]  # 合并后删旧名, 防止重复展示
    return data, used


def _series(biz_data, metric, years):
    out = []
    md = biz_data.get(metric, {})
    for y in years:
        out.append('' if y not in md else md[y])
    return out


def _fmt(v):
    if v == '' or v is None:
        return ''
    return repr(round(float(v), 6)) if isinstance(v, float) else str(v)


def build_fourth_block(data, years, title, total_line, label, lines):
    # 返回纯 CSV 行 (与 output.csv 数据行一致: N+3列 = 名称 + N年值 + 2空, N=年份数)
    n = len(years)
    block = []
    block.append([title] + [''] * (n + 2))  # 标题行 N+3列
    total = _series(data.get(total_line, {}), '收入', years)
    block.append(['营业收入合计(' + label + ')'] + [_fmt(v) for v in total] + ['', ''])
    for ln in lines:
        if ln not in data:
            continue
        bd = data[ln]
        inc = _series(bd, '收入', years)
        pct = _series(bd, '收入占比', years)
        gm = _series(bd, '毛利率', years)
        block.append([ln + '-收入'] + [_fmt(v) for v in inc] + ['', ''])
        block.append([ln + '-收入占比'] + [_fmt(v) for v in pct] + ['', ''])
        block.append([ln + '-毛利率'] + [_fmt(v) for v in gm] + ['', ''])
    return block


def _select_lines(data, priority, append_others=True):
    lines = [l for l in priority if l in data]
    if append_others:
        for b in data:
            if b in SKIP_LINES or b in priority:
                continue
            if b not in lines:
                lines.append(b)
    return lines


# ---------------------------------------------------------------------
# output.csv 注入
# ---------------------------------------------------------------------
def _years_from_header(header):
    yrs = []
    for h in header[1:]:
        if h and str(h).strip().endswith('年年报'):
            yrs.append(str(h).strip().replace('年年报', ''))
    return yrs


def inject(output_csv, product_xlsx, region_xlsx, alias_path, out_csv):
    # 1) 解析 + 口径合并
    pdata, _ = _read_segment(product_xlsx)
    rdata, _ = _read_segment(region_xlsx)
    pdata, pused = apply_aliases(pdata, alias_path)
    rdata, rused = apply_aliases(rdata, alias_path)

    plines = _select_lines(pdata, PRODUCT_PRIORITY, append_others=True)
    rlines = _select_lines(rdata, REGION_PRIORITY, append_others=False)

    # 2) 读 output.csv, 确定年份轴(主表为准)
    with open(output_csv, encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    years = _years_from_header(rows[0])

    pblock = build_fourth_block(pdata, years, '第四步：看业务构成 (分产品/分地区收入、占比、毛利率)', '合计', '产品', plines)
    rblock = build_fourth_block(rdata, years, '　▶ 按地区', '合计', '地区', rlines)
    new_block = pblock + rblock

    # 3) 精准移除旧第四步块: 第三步 与 第五步 之间、以 '第四步' 标题起始的区间
    #    仅删该区间, 不碰第三步自身指标; 幂等 (无旧块则跳过)
    def find_title(prefix):
        for i, r in enumerate(rows):
            if r and r[0].startswith(prefix):
                return i
        return -1
    t3 = find_title('第三步')
    t5 = find_title('第五步')
    start = -1
    if t3 >= 0 and t5 > t3:
        for i in range(t3 + 1, t5):
            if rows[i] and rows[i][0].startswith('第四步'):
                start = i
                break
    if start >= 0:
        rows = rows[:start] + rows[t5:]   # 删除 [start, t5) 整段第四步块
    ins = find_title('第五步')
    if ins < 0:
        ins = len(rows)
    out_rows = rows[:ins] + new_block + rows[ins:]

    if out_csv is None:
        out_csv = output_csv
    parent = os.path.dirname(out_csv)
    if parent:
        os.makedirs(parent, exist_ok=True)
    # 写回: 与核心格式一致 (表头14列, 数据/标题行13列, LF)
    header = out_rows[0]
    with open(out_csv, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        for r in out_rows[1:]:
            w.writerow(r)

    # 4) 闭合校验
    report = _validate_closure(out_rows, pdata, rdata, years, pused, rused)
    return report


def _get_row(rows, name):
    for r in rows:
        if r and r[0] == name:
            return r
    return None


def _validate_closure(rows, pdata, rdata, years, pused, rused):
    rep = {'product': {}, 'region': {}, 'aliases_used': {'product': pused, 'region': rused}}
    inc_row = _get_row(rows, '营业收入')
    ist_rev = []
    if inc_row:
        for i in range(len(years)):
            v = inc_row[i + 1] if i + 1 < len(inc_row) else ''
            ist_rev.append(float(v) if v not in ('', None) else 0.0)
    else:
        ist_rev = [0.0] * len(years)

    def closure(data, label, total_line='合计'):
        total = _series(data.get(total_line, {}), '收入', years)
        total = [v if v != '' else 0.0 for v in total]
        detail = [0.0] * len(years)
        prio = PRODUCT_PRIORITY if label == 'product' else REGION_PRIORITY
        add = (label == 'product')
        for ln in _select_lines(data, prio, append_others=add):
            if ln not in data:
                continue
            s = _series(data[ln], '收入', years)
            for i, v in enumerate(s):
                if v != '':
                    detail[i] += float(v)
        checks = []
        for i, y in enumerate(years):
            t = total[i]
            d = detail[i]
            ist = ist_rev[i] if i < len(ist_rev) else 0.0
            total_vs_ist = (abs(t - ist) / abs(ist) < 0.01) if ist else True
            detail_vs_total = (abs(d - t) / abs(t) < 0.05) if t else True
            checks.append({'year': y, 'total': t, 'detail_sum': d,
                           'total_vs_ist_ok': total_vs_ist,
                           'detail_vs_total_ok': detail_vs_total})
        rep[label] = checks

    closure(pdata, 'product')
    closure(rdata, 'region')
    return rep


if __name__ == '__main__':
    args = sys.argv[1:]
    output_csv = None
    product = region = alias = out = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--product':
            product = args[i + 1]; i += 2
        elif a == '--region':
            region = args[i + 1]; i += 2
        elif a == '--aliases':
            alias = args[i + 1]; i += 2
        elif a == '--out':
            out = args[i + 1]; i += 2
        else:
            if output_csv is None:
                output_csv = a
            i += 1
    if not output_csv or not product or not region:
        sys.exit("用法: build_segment.py <output.csv> --product <产品xlsx> --region <地区xlsx> [--aliases <json>] [--out <csv>]")
    # 默认口径字典: 未显式传 --aliases 时, 用 skill 自带 references/segment_aliases.json
    if not alias:
        dft = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'references', 'segment_aliases.json')
        if os.path.exists(dft):
            alias = dft
    rep = inject(output_csv, product, region, alias, out)
    print(f"  ✅ 第四步已注入 (产品 {len(rep['product'])} 年校验 / 地区 {len(rep['region'])} 年校验)")
    for side in ('product', 'region'):
        if rep['aliases_used'][side]:
            print(f"     口径衔接({side}): {rep['aliases_used'][side]}")
    for side in ('product', 'region'):
        bad_ist = [c for c in rep[side] if not c['total_vs_ist_ok']]
        bad_det = [c for c in rep[side] if not c['detail_vs_total_ok']]
        if bad_ist:
            print(f"     ⚠️  {side} 合计vs利润表营收 偏差>1%: {[c['year'] for c in bad_ist]}")
        else:
            print(f"     ✅ {side} 合计vs利润表营收 1%内闭合")
        if bad_det:
            print(f"     ⚠️  {side} 明细和vs合计 偏差>5%: {[(c['year'], round(abs(c['detail_sum']-c['total'])/c['total']*100, 2)) for c in bad_det]}")
        else:
            print(f"     ✅ {side} 明细和vs合计 5%内")
