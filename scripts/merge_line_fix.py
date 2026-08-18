#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块1：合并行识别 (防御性) (seven-step-metrics-csv v3.0)
=========================================================
输入预处理 (在 convert_input 产出之后、build_metrics 之前) 对资产负债表 CSV 做
合并行口径防御。仅覆盖 应收/应付 (决策#4: 先收敛防误伤)。

实证结论 (监理 Round 2):
  核心 get_series 对 `应收账款`/`应收票据` 用精确匹配优先(score3)。
  当报表同时含 合并行(`应收票据及应收账款`) 与 嵌套子行(`应收账款(元)`/`应收票据(元)`) 时,
  核心取子行求和 = 合并值 (单倍), 已正确, 无需修复。
真实风险 (需防御):
  仅当报表【只有合并行、无嵌套子行】时, 核心子串匹配会让 应收票据/应收账款 两个关键词
  都命中合并行 -> `应收 = 合并值 + 合并值 = 2×` (真实双重计数, 边缘结构)。

机制 (条件触发, 绝不破坏已正确的子行结构):
  合并行 与 嵌套子行 共存  ->  不改动 (core 已正确)
  仅合并行、无子行        ->  触发修复: 删除合并行, 注入 应收账款(元)(=合并值)、应收票据(元)(=0)
  无合并行                ->  不改动 (core 按原逻辑)

零回归: 本脚本只修"仅合并行无子行"边缘结构; 宁德式子行共存结构保持不动。
"""
import csv
import sys
import os
import json

# 合并科目 -> (子科目1, 子科目2); 仅应收/应付 (决策#4)
MERGED_MAP = {
    "应收票据及应收账款": ("应收账款", "应收票据"),
    "应付票据及应付账款": ("应付账款", "应付票据"),
}


def _nm(x):
    return str(x).replace('(元)', '').replace('（元）', '').strip()


def merge_fix(path, out_path=None, report_path=None):
    with open(path, encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    if not rows:
        return []
    header = rows[0]
    data = rows[1:]
    ncol = max(len(header) - 1, 0)

    triggered = []          # 实际触发修复的合并科目
    coexisting = []         # 子行共存 (未改动)
    skipped = []            # 无合并行 (未改动)

    for mkw, (c1, c2) in MERGED_MAP.items():
        merged_row = None
        child_rows = []
        for r in data:
            if not r or not r[0].strip():
                continue
            n = _nm(r[0])
            if n == mkw:
                merged_row = r
            elif n == c1 or n == c2:
                child_rows.append(r)
        if merged_row is None:
            skipped.append(mkw)
            continue
        if child_rows:
            coexisting.append(mkw)
            continue
        # 仅合并行、无子行 -> 触发修复
        data = [r for r in data if r is not merged_row]
        vals = merged_row[1:1 + ncol] if len(merged_row) > 1 else [''] * ncol
        zeros = [''] * ncol
        data.append([c1 + '(元)'] + list(vals))
        data.append([c2 + '(元)'] + list(zeros))
        triggered.append(mkw)

    if out_path is None:
        out_path = path
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        for r in data:
            w.writerow(r)

    report = {
        "file": os.path.basename(path),
        "triggered_fix": triggered,
        "child_coexisting": coexisting,
        "no_merged_row": skipped,
        "income_repaired": bool(triggered),
    }
    if report_path:
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def _resolve_out(out_path, src_path):
    if out_path is None:
        return src_path
    if os.path.isdir(out_path) or out_path.endswith(os.sep):
        return os.path.join(out_path, os.path.basename(src_path))
    return out_path


def main():
    args = sys.argv[1:]
    out_path = None
    report_path = None
    files = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--out':
            out_path = args[i + 1]; i += 2; continue
        if a == '--report':
            report_path = args[i + 1]; i += 2; continue
        files.append(a); i += 1
    if not files:
        sys.exit("用法: merge_line_fix.py <资产负债表.csv> [--out <dir>] [--report <json>]")
    for f in files:
        if not os.path.exists(f):
            print(f"  ⚠️  不存在: {f}"); continue
        rep = merge_fix(f, _resolve_out(out_path, f), report_path)
        if rep["income_repaired"]:
            print(f"  🔧 {rep['file']}: 触发修复 {rep['triggered_fix']} (仅合并行无子行)")
        else:
            print(f"  ✅ {rep['file']}: 无需修复 (共存={rep['child_coexisting']} 无合并行={rep['no_merged_row']})")


if __name__ == '__main__':
    main()
