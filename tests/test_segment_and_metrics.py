#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
七步财报分析 skill — 最小回归测试 (免 pytest, 直接 `python tests/test_segment_and_metrics.py`)
=================================================================================================
锁定本次优化最易回归的两处:
  1. build_segment._read_segment_stacked  — 东财分业务表 CSV 堆叠块解析
     (修复前: 只注入第四步标题, 无数据; 因原解析器只认 xlsx 全角空格格式)
  2. build_report_data 图表数据自动生成 — 必须读取第四步业务板块填充 CHART7/CHART8
  3. build_fourth_block 动态列宽 — 必须为 N+3 (N=年份数), 不再硬编码 13 列

所有 fixture 内嵌, 不依赖外部数据/桌面路径。退出码非 0 = 失败。
"""
import os
import sys
import csv
import json
import tempfile
import subprocess

SK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts')
sys.path.insert(0, SK)

import build_segment as bs


def _write_csv(path, rows):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        for r in rows:
            w.writerow(r)


def _ok(name):
    print(f"  ✅ {name}")


# ---------------------------------------------------------------------------
# 测试 1: 堆叠块解析 (模拟宁德 分产品 CSV: 营业收入 总/境内/境外 + 毛利率 + 收入占比)
# ---------------------------------------------------------------------------
def test_segment_stacked():
    rows = [
        ['科目', '2025年年报', '2024年年报'],
        ['合计', 1000.0, 800.0],          # 营业收入 总
        ['动力电池系统', 700.0, 600.0],
        ['储能电池系统', 300.0, 200.0],
        ['合计', 600.0, 500.0],          # 营业收入 境内 (应被忽略, 只取首个=总)
        ['动力电池系统', 400.0, 350.0],
        ['储能电池系统', 200.0, 150.0],
        ['合计', 26.0, 25.0],            # 毛利率 总
        ['动力电池系统', 23.0, 22.0],
        ['储能电池系统', 28.0, 27.0],
        ['合计', 100.0, 100.0],          # 收入占比 总
        ['动力电池系统', 70.0, 75.0],
        ['储能电池系统', 30.0, 25.0],
    ]
    p = tempfile.mktemp(suffix='.csv')
    _write_csv(p, rows)
    try:
        data, years = bs._read_segment(p)
        assert years == ['2025', '2024'], f"年份轴错误: {years}"
        # 合计(总) 收入
        assert abs(data['合计']['收入']['2025'] - 1000.0) < 1e-6
        # 产品收入取 总块 (700), 而非 境内块 (400)
        assert abs(data['动力电池系统']['收入']['2025'] - 700.0) < 1e-6
        # 毛利率 / 收入占比
        assert abs(data['动力电池系统']['毛利率']['2025'] - 23.0) < 1e-6
        assert abs(data['动力电池系统']['收入占比']['2025'] - 70.0) < 1e-6
        # 境内块未被采纳: 储能电池系统 收入应为 300 (总块) 而非 200 (境内块)
        assert abs(data['储能电池系统']['收入']['2025'] - 300.0) < 1e-6
        # 业务线集合
        assert '动力电池系统' in data and '储能电池系统' in data
    finally:
        os.remove(p)
    _ok("test_segment_stacked (堆叠块: 总块采纳/境内块忽略/毛利率/占比)")


# ---------------------------------------------------------------------------
# 测试 2: 动态列宽 (N=2 年 -> 标题 N+3=5 列, 数据行 N+3=5 列)
# ---------------------------------------------------------------------------
def test_fourth_block_width():
    rows = [
        ['科目', '2025年年报', '2024年年报'],
        ['合计', 1000.0, 800.0],
        ['动力电池系统', 700.0, 600.0],
        ['储能电池系统', 300.0, 200.0],
        ['合计', 26.0, 25.0],
        ['动力电池系统', 23.0, 22.0],
        ['储能电池系统', 28.0, 27.0],
        ['合计', 100.0, 100.0],
        ['动力电池系统', 70.0, 75.0],
        ['储能电池系统', 30.0, 25.0],
    ]
    p = tempfile.mktemp(suffix='.csv')
    _write_csv(p, rows)
    try:
        data, years = bs._read_segment(p)
        block = bs.build_fourth_block(
            data, years,
            '第四步：看业务构成', '合计', '产品',
            ['动力电池系统', '储能电池系统'])
        # 标题行 + 每个产品 3 行 (收入/占比/毛利率)
        # 标题: 1 + (N+2) = N+3 = 5
        assert len(block[0]) == 5, f"标题行列宽应为5, 实际{len(block[0])}"
        for r in block[1:]:
            assert len(r) == 5, f"数据行列宽应为5, 实际{len(r)}"
        assert block[0][0].startswith('第四步')
        # 动力电池系统-收入 行首位 + 2 年值 + 2 空 (block[1]=合计行, block[2]=首产品收入行)
        inc_row = block[2]
        assert inc_row[0] == '动力电池系统-收入'
        assert abs(float(inc_row[1]) - 700.0) < 1e-6
        assert inc_row[3] == '' and inc_row[4] == ''
    finally:
        os.remove(p)
    _ok("test_fourth_block_width (动态 N+3 列)")


# ---------------------------------------------------------------------------
# 测试 3: build_report_data 读取第四步填充 CHART7/CHART8/业务板块
# ---------------------------------------------------------------------------
def test_report_data_segment():
    # 构造最小 output.csv: 表头(N+4=6) + 第三步 + 第四步块 + 第五步
    years_hdr = ['2025年年报', '2024年年报']   # 表头用年年报格式
    years_key = ['2025', '2024']              # 第四步块内部用年份键
    header = ['科目'] + years_hdr + ['', '', '', '']  # 名称 + 2年 + 4空 = 6 (N+4)
    step3 = ['第三步：看增长'] + [''] * 5
    rev_row = ['营业收入'] + ['1000', '800'] + ['', '', '', '']
    step5 = ['第五步：看资产'] + [''] * 5

    seg_rows = [
        ['科目', '2025年年报', '2024年年报'],
        ['合计', 1000.0, 800.0],
        ['动力电池系统', 700.0, 600.0],
        ['储能电池系统', 300.0, 200.0],
        ['合计', 26.0, 25.0],
        ['动力电池系统', 23.0, 22.0],
        ['储能电池系统', 28.0, 27.0],
        ['合计', 100.0, 100.0],
        ['动力电池系统', 70.0, 75.0],
        ['储能电池系统', 30.0, 25.0],
    ]
    sp = tempfile.mktemp(suffix='.csv')
    _write_csv(sp, seg_rows)
    data, _ = bs._read_segment(sp)
    fourth = bs.build_fourth_block(
        data, years_key, '第四步：看业务构成', '合计', '产品',
        ['动力电池系统', '储能电池系统'])

    out_dir = tempfile.mkdtemp()
    out_csv = os.path.join(out_dir, 'output.csv')
    with open(out_csv, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        w.writerow(step3)
        w.writerow(rev_row)
        for r in fourth:
            w.writerow(r)
        w.writerow(step5)

    # 调用 build_report_data CLI
    r = subprocess.run(
        [sys.executable, os.path.join(SK, 'build_report_data.py'), out_csv, '--out', out_dir],
        capture_output=True, text=True)
    assert r.returncode == 0, f"build_report_data 失败: {r.stderr}"

    jpath = os.path.join(out_dir, 'report_data.json')
    assert os.path.exists(jpath), "report_data.json 未生成"
    d = json.load(open(jpath, encoding='utf-8'))
    names = d.get('BUSINESS_SEGMENT_NAMES')
    assert names and '动力电池系统' in names and '储能电池系统' in names, \
        f"业务板块缺失: {names}"
    c7 = d.get('CHART7_DATA_SEGMENTS')   # 收入占比 (已是百分比单位, 不×100)
    c8 = d.get('CHART8_DATA_SEGMENTS')   # 毛利率 (已是百分比单位, 不×100)
    assert c7 and c8, "CHART7/CHART8 为空 (第四步数据未读入图表)"
    # 动力电池系统 收入占比 2025 = 70.0 (已是%单位, parse_segments 用 as_is 不再×100)
    assert abs(c7[0][0] - 70.0) < 1e-6, f"CHART7 首值应为70.0(百分比单位), 实际{c7[0][0]}"
    # 动力电池系统 毛利率 2025 = 23.0 (已是%单位, parse_segments 用 as_is 不再×100)
    assert abs(c8[0][0] - 23.0) < 1e-6, f"CHART8 首值应为23.0(百分比单位), 实际{c8[0][0]}"
    os.remove(sp)
    _ok("test_report_data_segment (图表自动读取第四步业务板块)")


def main():
    print("=== 七步财报分析 skill 回归测试 ===")
    test_segment_stacked()
    test_fourth_block_width()
    test_report_data_segment()
    print("\n✅ 全部回归测试通过")


if __name__ == '__main__':
    main()
