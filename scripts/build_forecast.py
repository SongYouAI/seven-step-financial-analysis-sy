#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块4：前瞻一致预期 (seven-step-metrics-csv v3.0)
=================================================
双模式数据源:
  ① 接口模式(默认): 由 agent 经 westock `data_consensus` 抓取, 落盘为 forecast_input.csv;
  ② 手动 CSV 兜底: 用户直接提供 forecast_input.csv (列见下)。
本脚本消费 forecast_input.csv, 产出规范化的前瞻一致预期表。

forecast_input.csv 列 (机构级离散度明细, 一行=一机构一年预测):
  机构, 来源日期, 年份, 营收预测(元), 净利预测(元), EPS预测(元), 目标价(元), 口径标注

产出:
  - forecast_consensus.csv (汇总: 指标/最新A/E1/E2/E3/说明)
  - forecast_discrete.csv  (离散度明细: 机构/来源日期/年份/营收/净利/EPS/目标价/口径, 禁止"某券商"模糊标签)
  - forecast_report.md     (data_status 用「一致预期(前瞻)」专节文本)

口径处理:
  - EPS 列强制标注同源(聚合源), 与年报基本 EPS 差异单列说明, 避免误读 15.82 vs 16.14;
  - E3(如 2028E) 机构数=0 标注"外推非共识, 仅作趋势参考"。
零回归: 不改动核心; 前瞻块为选择性增强伴侣文件。
"""
import csv
import sys
import os
import re
import json
from collections import defaultdict


# ---------------------------------------------------------------------
# 读取 + 聚合
# ---------------------------------------------------------------------
def read_input(path):
    rows = []
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            # 归一化表头: 去掉 (元)/（元） 等后缀, 便于统一按 营收预测/净利预测/EPS预测/目标价 取值
            nr = {}
            for k, v in r.items():
                if k is None:
                    continue
                nk = re.sub(r'[（(][^）)]*[）)]', '', k).strip()
                nr[nk] = v
            rows.append(nr)
    return rows


def agg(rows):
    # 年份集合 (预测年, 形如 2026 / 2026E / 2027E ...)
    years = sorted({r['年份'].strip() for r in rows if r.get('年份', '').strip()})
    # E1/E2/E3 = 按年份升序
    e_order = years[:3]
    metrics = defaultdict(lambda: defaultdict(list))  # metric -> year -> [values]
    for r in rows:
        y = r['年份'].strip()
        for m in ('营收预测', '净利预测', 'EPS预测', '目标价'):
            v = r.get(m, '').strip()
            if v not in ('', None):
                try:
                    metrics[m][y].append(float(v))
                except ValueError:
                    pass
    return years, e_order, metrics


def mean(vals):
    return sum(vals) / len(vals) if vals else ''


def build_consensus(rows, latest):
    years, e_order, metrics = agg(rows)
    # e_order 映射到 E1/E2/E3
    e_map = {y: f'E{i+1}' for i, y in enumerate(e_order)}
    # 反查每个预测年的机构数
    yr_inst = defaultdict(set)
    for r in rows:
        yr_inst[r['年份'].strip()].add(r['机构'].strip())

    out = []
    # 指标顺序: 营业收入 / 归母净利润 / EPS / 目标价
    def line(name, metric_key, latest_a, note=''):
        cells = []
        for y in e_order:
            vals = metrics.get(metric_key, {}).get(y, [])
            cells.append(f'{mean(vals):.4f}' if vals else '')
        e3_flag = ''
        if len(e_order) >= 3:
            e3y = e_order[2]
            if len(yr_inst.get(e3y, [])) == 0:
                e3_flag = '; E3外推非共识,仅作趋势参考'
        out.append([name, latest_a, *cells, (note + e3_flag).strip('; ')])

    out.append(['营业收入(元)', latest.get('营收', ''),
                *[f'{mean(metrics.get("营收预测",{}).get(y,[])):.2f}' if metrics.get("营收预测",{}).get(y) else '' for y in e_order],
                '一致预期均值(元)'])
    out.append(['归母净利润(元)', latest.get('净利', ''),
                *[f'{mean(metrics.get("净利预测",{}).get(y,[])):.2f}' if metrics.get("净利预测",{}).get(y) else '' for y in e_order],
                '一致预期均值(元)'])
    out.append(['EPS(元,聚合源口径)', latest.get('eps', ''),
                *[f'{mean(metrics.get("EPS预测",{}).get(y,[])):.4f}' if metrics.get("EPS预测",{}).get(y) else '' for y in e_order],
                '聚合源口径; 与年报基本EPS差异单列说明'])
    out.append(['目标价(元)', '',
                *[f'{mean(metrics.get("目标价",{}).get(y,[])):.2f}' if metrics.get("目标价",{}).get(y) else '' for y in e_order],
                '机构目标价均值'])
    return out, e_order


def build_discrete(rows):
    out = [['机构', '来源日期', '年份', '营收预测(元)', '净利预测(元)', 'EPS预测(元)', '目标价(元)', '口径标注']]
    for r in rows:
        out.append([r.get('机构', '').strip(), r.get('来源日期', '').strip(),
                    r.get('年份', '').strip(), r.get('营收预测', '').strip(),
                    r.get('净利预测', '').strip(), r.get('EPS预测', '').strip(),
                    r.get('目标价', '').strip(), r.get('口径标注', '').strip()])
    return out


def build_report_md(rows, consensus, e_order, latest):
    yr_inst = defaultdict(set)
    for r in rows:
        yr_inst[r['年份'].strip()].add(r['机构'].strip())
    lines = []
    lines.append('## 一致预期（前瞻）\n')
    lines.append(f'- 覆盖机构数: {len({r["机构"].strip() for r in rows})}')
    lines.append(f'- 预测年份: {", ".join(e_order) if e_order else "无"}')
    lines.append(f'- 最新实际营收: {latest.get("营收","-")} 元; 最新实际归母净利: {latest.get("净利","-")} 元')
    lines.append('- EPS 口径: 一致预期 EPS 为聚合源口径，与年报基本 EPS 可能存在差异（本数据未含年报基本EPS），引用时须注明口径，勿混用。')
    if len(e_order) >= 3 and len(yr_inst.get(e_order[2], [])) == 0:
        lines.append(f'- ⚠️ {e_order[2]} 机构数=0，属外推非共识，仅作趋势参考。')
    lines.append('\n### 汇总（指标 / 最新A / ' + ' / '.join(e_order) + ' / 说明）\n')
    lines.append('| 指标 | 最新A | ' + ' | '.join(e_order) + ' | 说明 |')
    lines.append('| --- | --- | ' + ' | '.join(['---'] * len(e_order)) + ' | --- |')
    for c in consensus:
        lines.append('| ' + ' | '.join(c) + ' |')
    return '\n'.join(lines) + '\n'


def _latest_from_output(output_csv):
    latest = {}
    if not output_csv or not os.path.exists(output_csv):
        return latest
    with open(output_csv, encoding='utf-8-sig') as f:
        r = list(csv.reader(f))
    def g(n):
        for x in r:
            if x and x[0] == n:
                return x
        return None
    inc = g('营业收入')
    if inc and len(inc) > 1 and inc[1] not in ('', None):
        latest['营收'] = inc[1]
    np = g('归母净利润')
    if np and len(np) > 1 and np[1] not in ('', None):
        latest['净利'] = np[1]
    return latest


def main():
    args = sys.argv[1:]
    inp = out_dir = output_csv = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--input':
            inp = args[i + 1]; i += 2
        elif a == '--out':
            out_dir = args[i + 1]; i += 2
        elif a == '--output-csv':
            output_csv = args[i + 1]; i += 2
        else:
            if inp is None:
                inp = a
            i += 1
    if not inp:
        sys.exit("用法: build_forecast.py <forecast_input.csv> [--out <目录>] [--output-csv <output.csv>]")
    if out_dir is None:
        out_dir = os.path.dirname(os.path.abspath(inp))

    rows = read_input(inp)
    if not rows:
        sys.exit("❌ forecast_input.csv 为空或无有效行")
    # 字段完整性校验 (禁止"某券商"模糊标签)
    bad = [r for r in rows if not r.get('机构', '').strip() or '某券商' in r.get('机构', '') or '某机构' in r.get('机构', '')]
    if bad:
        print(f"  ⚠️  离散度存在 {len(bad)} 行机构名缺失/模糊(禁止'某券商'), 已跳过: {[b.get('机构','') for b in bad][:5]}")
        rows = [r for r in rows if r.get('机构', '').strip() and '某券商' not in r.get('机构', '') and '某机构' not in r.get('机构', '')]
    latest = _latest_from_output(output_csv)
    consensus, e_order = build_consensus(rows, latest)
    discrete = build_discrete(rows)
    md = build_report_md(rows, consensus, e_order, latest)

    os.makedirs(out_dir, exist_ok=True)
    p1 = os.path.join(out_dir, 'forecast_consensus.csv')
    p2 = os.path.join(out_dir, 'forecast_discrete.csv')
    p3 = os.path.join(out_dir, 'forecast_report.md')
    with open(p1, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['指标', '最新A'] + [f'E{i+1}' for i in range(len(e_order))] + ['说明'])
        for c in consensus:
            w.writerow(c)
    with open(p2, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        for c in discrete:
            w.writerow(c)
    with open(p3, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f"  ✅ 前瞻一致预期已生成: {p1}")
    print(f"     机构数={len({r['机构'].strip() for r in rows})}, 预测年={e_order}")
    print(f"     离散度明细: {p2}")
    print(f"     报告: {p3}")


if __name__ == '__main__':
    main()
