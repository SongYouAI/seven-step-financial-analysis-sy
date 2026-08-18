#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块6：口径自证 (seven-step-metrics-csv v3.0)
=============================================
向核心生成的 data_status.md **追加**「口径说明」专节 (append-only, 零回归):
  - 应收标准口径(合并行/子行求和, 取自 output.csv 应收行) vs
    应收宽口径(标准 + 应收款项融资, 取自资产负债表 CSV);
  - EPS 双口径(聚合源 vs 年报基本) 引用说明。
不修改核心 build_metrics.py 已生成的任何段落, 仅追加, 可重跑幂等。

用法:
  build_caliber_note.py --bs <资产负债表.csv> --output <output.csv> --status <data_status.md>
"""
import csv
import sys
import os


def _num(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _read_csv(path):
    with open(path, encoding='utf-8-sig') as f:
        return [list(r) for r in csv.reader(f)]


def _years(header):
    """返回 [(year_label, col_index), ...] 逆序(新->旧)。"""
    out = []
    for i, h in enumerate(header[1:], 1):
        if h and str(h).strip().endswith('年年报'):
            out.append((str(h).strip().replace('年年报', ''), i))
    return out


def _latest(row, years):
    """取某行最新非空年份 (year_label, value)。"""
    for yl, ci in years:
        if ci < len(row):
            v = _num(row[ci])
            if v is not None:
                return yl, v
    return None, None


def _norm(name):
    """去 (元)/(元) 后缀, 便于跨来源行名匹配。"""
    return str(name).replace('（元）', '').replace('(元)', '').strip()


def _find_row(rows, name):
    n = _norm(name)
    for r in rows:
        if r and _norm(r[0]) == n:
            return r
    # 前缀容错 (如 '应收款项融资(元)' 仍命中 '应收款项融资')
    for r in rows:
        if r and _norm(r[0]).startswith(n):
            return r
    return None


def main():
    args = sys.argv[1:]
    bs = status = output = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--bs':
            bs = args[i + 1]; i += 2
        elif a == '--status':
            status = args[i + 1]; i += 2
        elif a == '--output':
            output = args[i + 1]; i += 2
        else:
            i += 1
    if not (bs and output and status):
        sys.exit("用法: build_caliber_note.py --bs <资产负债表.csv> --output <output.csv> --status <data_status.md>")

    # 1) 应收标准口径 (output.csv 应收行)
    orows = _read_csv(output)
    oyears = _years(orows[0])
    ar_row = _find_row(orows, '应收')
    ar_yl, ar_val = _latest(ar_row, oyears) if ar_row else (None, None)

    # 2) 应收款项融资 (资产负债表)
    brows = _read_csv(bs)
    byears = _years(brows[0])
    fin_row = _find_row(brows, '应收款项融资')
    fin_yl, fin_val = _latest(fin_row, byears) if fin_row else (None, None)

    # 3) 宽口径
    wide = (ar_val + fin_val) if (ar_val is not None and fin_val is not None) else None

    # 4) 组装「口径说明」专节 (幂等: 若已存在则跳过)
    section_title = "## 口径说明（模块6 自证）"
    if os.path.exists(status):
        with open(status, encoding='utf-8') as f:
            existing = f.read()
        if section_title in existing:
            print("  ℹ️  口径说明专节已存在, 跳过追加 (幂等)")
            return

    lines = [section_title, ""]
    if ar_val is not None:
        lines.append(f"- **应收·标准口径**（合并行/子行求和，核心资产平衡校验一致）：{ar_val:,.0f} 元（最新年 {ar_yl}）。")
    else:
        lines.append("- **应收·标准口径**：未能从 output.csv 提取「应收」行，请检查主表。")
    if fin_val is not None and wide is not None:
        lines.append(f"- **应收·宽口径** = 标准口径 + 应收款项融资（{fin_val:,.0f} 元，最新年 {fin_yl}）= **{wide:,.0f} 元（≈{wide/1e8:.0f} 亿）**。宽口径含应收款项融资，分析周转/信用敞口时需注意与标准口径差异。")
    else:
        lines.append("- **应收·宽口径**：未从资产负债表提取「应收款项融资」科目，宽口径暂不可计算；标准口径如上。")
    lines.append("- **EPS 双口径**：前瞻一致预期采用**聚合源口径**（见 `forecast_report.md`），与年报基本 EPS 可能存在差异，引用时须注明口径、勿混用。")
    lines.append("")

    with open(status, 'a', encoding='utf-8') as f:
        f.write("\n" + "\n".join(lines) + "\n")
    print(f"  ✅ 口径说明专节已追加 → {status} (标准口径≈{ar_val/1e8:.0f}亿, 宽口径≈{ (wide/1e8) if wide else 0:.0f}亿)")


if __name__ == '__main__':
    main()
