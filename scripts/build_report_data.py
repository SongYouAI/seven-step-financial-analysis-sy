#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块7：图表数据自动生成 (seven-step-financial-analysis v6.6 新增)
===============================================================
读 Phase 0 产出的 output.csv (+ 可选 forecast_consensus.csv 伴侣文件),
自动生成报告模板所需的全部图表 JSON 占位符值, 根除"AI 手填 16+ 组图表数组"这一最高频故障。

产出:
  - report_data.json      : {占位符名: JSON 值} 映射, AI 直接读取粘贴
  - report_prefilled.html : 图表/年份/板块占位符已填的模板副本, 仅叙事占位符待填

单位换算在本脚本一处完成 (与模板标签对齐):
  金额(元) -> 亿 (÷1e8); 比率小数 -> % (×100); 万元 保持; 周转天数 保持。

设计原则: 只读 output.csv, 不改写主表; 缺数据填 null (图表自动断点), 不编造。
"""
import csv
import sys
import os
import json


SK = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------
# 读取 output.csv
# ---------------------------------------------------------------------
def load_output(path):
    with open(path, encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], {}
    years = []
    for h in rows[0][1:]:
        if h and str(h).strip().endswith('年年报'):
            years.append(str(h).strip().replace('年年报', ''))
    metrics = {}
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        name = r[0]
        vals = []
        for i, y in enumerate(years):
            v = r[i + 1] if i + 1 < len(r) else ''
            vals.append(_num(v))
        metrics[name] = vals
    return years, metrics


def _num(v):
    if v is None or v == '' or v == '除数为零。':
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def series(metrics, name):
    return metrics.get(name, [None] * len(next(iter(metrics.values()), [])))


# ---------------------------------------------------------------------
# 单位换算 (None 透传)
# ---------------------------------------------------------------------
def to_pct(arr, nd=2):
    return [round(x * 100, nd) if x is not None else None for x in arr]


def to_yi(arr, nd=2):
    return [round(x / 1e8, nd) if x is not None else None for x in arr]


def to_wan(arr, nd=4):
    return [round(x / 1e4, nd) if x is not None else None for x in arr]


def as_is(arr, nd=4):
    return [round(x, nd) if x is not None else None for x in arr]


def head(arr, nd=4):
    """取最新年(N=0)单值。"""
    if not arr:
        return None
    return round(arr[0], nd) if arr[0] is not None else None


def drop_last(arr):
    """增长率图丢弃最旧年的 '除数为零。' 占位。"""
    return arr[:-1] if len(arr) > 1 else arr


# ---------------------------------------------------------------------
# 分业务板块 (第四步块)
# ---------------------------------------------------------------------
def parse_segments(metrics):
    """返回 (names, seg7_占比, seg8_毛利率)。

    单位说明：build_segment.py 写入 output.csv 时业务占比/毛利率已经是百分比单位
    (如 23.84 代表 23.84%)，不是小数 (0.2384)。这里必须用 as_is() 而非 to_pct()，否则会双重换算
    (23.84 → 2384) 导致毛利率显示成几千%的 bug。
    """
    names = []
    for nm in metrics:
        if nm.endswith('-收入占比') and '合计' not in nm and not nm.startswith(('境内', '境外')):
            seg = nm[:-len('-收入占比')]
            if seg not in names:
                names.append(seg)
    seg7, seg8 = [], []
    for seg in names:
        pct_row = series(metrics, seg + '-收入占比')
        gm_row = series(metrics, seg + '-毛利率')
        seg7.append(as_is(pct_row))   # 已是百分比单位，不 ×100
        seg8.append(as_is(gm_row))    # 已是百分比单位，不 ×100
    return names, seg7, seg8


# ---------------------------------------------------------------------
# 前瞻一致预期 (forecast_consensus.csv)
# ---------------------------------------------------------------------
def parse_forecast(path):
    """返回 (exp_rev_cagr, exp_np_cagr) 或 (None, None)。"""
    if not path or not os.path.exists(path):
        return None, None
    with open(path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    d = {}
    for r in rows:
        key = (r.get('指标') or '').strip()
        e = {}
        for col in ('E1', 'E2', 'E3'):
            v = r.get(col, '').strip() if r.get(col) else ''
            try:
                e[col] = float(v) if v else None
            except ValueError:
                e[col] = None
        d[key] = e
    return _cagr(d.get('营业收入(元)', {})), _cagr(d.get('归母净利润(元)', {}))


def _cagr(e):
    a, b, c = e.get('E1'), e.get('E2'), e.get('E3')
    if a and c and a > 0 and c > 0:
        n = 2  # E1->E3 跨 2 年
        return round((pow(c / a, 1.0 / n) - 1) * 100, 2)
    return None


def hist_cagr(arr):
    a, b = arr[0], arr[-1]
    if a and b and a > 0 and b > 0 and len(arr) > 1:
        n = len(arr) - 1
        return round((pow(a / b, 1.0 / n) - 1) * 100, 2)
    return None


# ---------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------
def build(output_csv, forecast_csv=None):
    years, metrics = load_output(output_csv)
    if not years:
        sys.exit("❌ output.csv 为空或无法解析年份")
    n = len(years)
    M = lambda name: series(metrics, name)

    data = {}
    data['CHART_YEARS'] = years

    # 图1 营收/归母净利润(亿)
    data['CHART1_DATA_REVENUE'] = to_yi(M('营业收入'))
    data['CHART1_DATA_NET_PROFIT'] = to_yi(M('归母净利润'))

    # 图2 盈利质量(小数, 不转%)
    data['CHART2_DATA_CF_RATIO'] = as_is(M('经营净现金流/归母净利润'))
    data['CHART2_DATA_DEDUCT_RATIO'] = as_is(M('扣非净利润/净利润'))

    # 图3 毛利/净利率(%)
    data['CHART3_DATA_GROSS_MARGIN'] = to_pct(M('毛利率'))
    data['CHART3_DATA_NET_MARGIN'] = to_pct(M('净利率'))

    # 图4 费用率(%)
    data['CHART4_DATA_RD_RATIO'] = to_pct(M('研发费用率'))
    data['CHART4_DATA_ADMIN_RATIO'] = to_pct(M('管理费用率'))
    data['CHART4_DATA_SALES_RATIO'] = to_pct(M('销售费用率'))

    # 图5 增长率(%)——丢弃最旧年
    data['CHART5_DATA_REV_GROWTH'] = to_pct(drop_last(M('营收增长率')))
    data['CHART5_DATA_NET_PROFIT_GROWTH'] = to_pct(drop_last(M('归母净利润增长率')))

    # 图6 历史 vs 预期 CAGR(%)
    rev_cagr = hist_cagr(M('营业收入'))
    np_cagr = hist_cagr(M('归母净利润'))
    data['CHART6_DATA_HIST_CAGR'] = [rev_cagr, np_cagr]
    exp_rev, exp_np = parse_forecast(forecast_csv)
    data['CHART6_DATA_EXP_CAGR'] = [exp_rev, exp_np]

    # 图7/8 板块
    seg_names, seg7, seg8 = parse_segments(metrics)
    data['BUSINESS_SEGMENT_NAMES'] = seg_names
    data['CHART7_DATA_SEGMENTS'] = seg7
    data['CHART8_DATA_SEGMENTS'] = seg8

    # 图9 资产结构(亿)——output.csv 实际指标名是「流动资产/非流动资产」(无"合计"后缀)
    data['CHART9_DATA_CURRENT_ASSETS'] = to_yi(M('流动资产'))
    data['CHART9_DATA_NON_CURRENT_ASSETS'] = to_yi(M('非流动资产'))

    # 图10 资产负债率(%)
    data['CHART10_DATA_DEBT_RATIO'] = to_pct(M('资产负债率'))

    # 图11 WC/收入(小数)
    data['CHART11_DATA_WC_RATIO'] = as_is(M('1元收入需要的WC'))

    # 图12 人均(万元, 来自 headcount 注入; 缺则 [])
    data['CHART12_DATA_REV_PER_CAPITA'] = to_wan(M('人均收入(万元)')) if '人均收入(万元)' in metrics else []
    data['CHART12_DATA_PROFIT_PER_CAPITA'] = to_wan(M('人均归母净利润(万元)')) if '人均归母净利润(万元)' in metrics else []

    # 图13 ROE/ROA/ROIC(%)
    data['CHART13_DATA_ROE'] = to_pct(M('ROE'))
    data['CHART13_DATA_ROA'] = to_pct(M('ROA'))
    data['CHART13_DATA_ROIC'] = to_pct(M('ROIC'))

    # 图14 杜邦(最新年)
    data['CHART14_DATA_DUPONT'] = [
        to_pct([head(M('销售净利率'))], 2)[0],
        as_is([head(M('总资产周转率'))], 3)[0],
        as_is([head(M('权益乘数'))], 3)[0],
    ]

    # 图15 周转天数(天)
    data['CHART15_DATA_TOTAL_ASSET_DAYS'] = as_is(M('总资产周转天数'), 1)
    data['CHART15_DATA_INVENTORY_DAYS'] = as_is(M('存货周转天数'), 1)

    # 图16 同行 (AI 补, 留空)
    data['CHART16_DATA_PEER_NAMES'] = []
    data['CHART16_DATA_GROSS_MARGIN'] = []
    data['CHART16_DATA_NET_MARGIN'] = []
    data['CHART16_DATA_DEBT_RATIO'] = []

    return data, n


def prefill_template(template_path, data):
    with open(template_path, encoding='utf-8') as f:
        html = f.read()
    for key, val in data.items():
        placeholder = '{{' + key + '}}'
        if placeholder in html:
            html = html.replace(placeholder, json.dumps(val, ensure_ascii=False))
    return html


def main():
    args = sys.argv[1:]
    inp = out_dir = forecast = template = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--input':
            inp = args[i + 1]; i += 2
        elif a == '--out':
            out_dir = args[i + 1]; i += 2
        elif a == '--forecast':
            forecast = args[i + 1]; i += 2
        elif a == '--template':
            template = args[i + 1]; i += 2
        else:
            if inp is None:
                inp = a
            i += 1
    if not inp:
        sys.exit("用法: build_report_data.py <output.csv> [--out <目录>] [--forecast <forecast_consensus.csv>] [--template <report_template.html>]")

    out_dir = out_dir or os.path.dirname(os.path.abspath(inp))
    os.makedirs(out_dir, exist_ok=True)

    # 自动探测同目录 forecast_consensus.csv
    if forecast is None:
        cand = os.path.join(out_dir, 'forecast_consensus.csv')
        if os.path.exists(cand):
            forecast = cand
    if template is None:
        template = os.path.join(SK, '..', 'report_template.html')
    if not os.path.exists(template):
        template = None

    data, n = build(inp, forecast)

    json_path = os.path.join(out_dir, 'report_data.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    filled = None
    if template:
        html = prefill_template(template, data)
        filled = os.path.join(out_dir, 'report_prefilled.html')
        with open(filled, 'w', encoding='utf-8') as f:
            f.write(html)

    print(f"  ✅ 图表数据已生成: {json_path}")
    print(f"     年份数 N={n}, X轴={data['CHART_YEARS']}")
    print(f"     业务板块: {data['BUSINESS_SEGMENT_NAMES'] or '无(未注入第四步)'}")
    print(f"     人均指标: {'已注入' if data['CHART12_DATA_REV_PER_CAPITA'] else '未注入(缺 headcount)'}")
    if data['CHART6_DATA_EXP_CAGR'][0] is not None:
        print(f"     预期CAGR: 营收={data['CHART6_DATA_EXP_CAGR'][0]}% 归母={data['CHART6_DATA_EXP_CAGR'][1]}%")
    else:
        print(f"     预期CAGR: 未提供 forecast_consensus.csv (图6右柱留空)")
    if filled:
        print(f"     预填模板: {filled} (仅叙事占位符待填)")


if __name__ == '__main__':
    main()
