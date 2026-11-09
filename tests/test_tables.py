#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""七步财报分析 · v2.1.5 / v2.1.6 表格排版回归测试。

覆盖：
  - render_report.enhance_tables（内容感知列宽 / 幂等 / 不误伤 JS）
  - v2.1.6 列级对齐语义（th 与 td 同列同类、角标数字列、年份窄列、
    表头括注保护、ISO 日期不算数值列、宽表不再裁末列）
  - render_report.relax_bar_headroom（柱状图顶部留白）
  - BOOT 数据标签 align:'top' + layout.padding.top
  - sevenstep-adapt.css 表格系统关键规则
  - check_html P0-14 静态门禁（合规文档不报；逐项破坏必报）

运行：python3 -m unittest discover -s tests -v
"""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parent.parent
SCRIPTS = SK / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import render_report as rr         # noqa: E402


ANOMALY = (
    '<div class="table-wrap table-scroll"><table><thead><tr>'
    '<th>年份</th><th>异常点</th><th>状态</th><th>依据</th>'
    '</tr></thead><tbody>'
    '<tr><td>2023</td><td>营收 +50.04%，超过 ±30% 阈值</td>'
    '<td><span class="src-tag a">已闭环</span> 已验证</td>'
    '<td>2023-01-10 云川电力过户并表；股本从 227.42 亿股增至 244.68 亿股，'
    '属报表范围变化，不是内生增长；见 KNOWLEDGE_INDEX.md 并表条目。</td></tr>'
    '<tr><td>2016—2017</td><td>研发费用率为 0</td>'
    '<td><span class="src-tag a">已闭环</span> 已解释</td>'
    '<td>源利润表未单列该科目，属披露口径，不是零投入。</td></tr>'
    '</tbody></table></div>')

NINE_COL = (
    '<table><thead><tr>' + ''.join('<th>指标%d</th>' % i for i in range(9)) +
    '</tr></thead><tbody><tr>' + ''.join('<td>61.67%</td>' for _ in range(9)) +
    '</tr><tr>' + ''.join('<td>0.0769</td>' for _ in range(9)) +
    '</tr></tbody></table>')


def widths(out):
    return [float(x) for x in re.findall(r'<col style="width:([\d.]+)%">', out)]


def min_width(out):
    m = re.search(r'<table[^>]*min-width:(\d+)px', out)
    return int(m.group(1)) if m else 0


def _run_gate(html_text):
    with tempfile.TemporaryDirectory(prefix='sevenstep_tables_') as d:
        p = Path(d) / 'r.html'
        p.write_text(html_text, encoding='utf-8')
        r = subprocess.run([sys.executable, str(SCRIPTS / 'check_html.py'),
                            str(p), '--strict-p1', '--no-js'],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace')
        return r.stdout + r.stderr


def _doc(tables, css_ok=True, boot_ok=True, css_extra=True):
    css = ('table-layout:fixed;.cell-tight{};td.num{};'
           '.src-tag{white-space:nowrap;flex:none;}' +
           ('text-align:left;.data-table thead th.cell-key{};'
            '.data-table tbody td.num.cell-tight{};'
            '.data-table thead th .unit{};' if css_extra else '')
           ) if css_ok else ''
    js = "Chart.defaults.plugins.datalabels.align='top';Chart.defaults.layout.padding.top=22;" \
        if boot_ok else ''
    return ('<html><head><style>%s</style></head><body>%s'
            '<script>%s</script></body></html>' % (css, tables, js))


class TestEnhanceTables(unittest.TestCase):

    def test_01_anomaly_table_has_four_controlled_columns(self):
        out = rr.enhance_tables(ANOMALY)
        self.assertEqual(len(widths(out)), 4)
        self.assertAlmostEqual(sum(widths(out)), 100.0, places=2)
        self.assertIn('data-table table-anomaly', out)
        self.assertGreaterEqual(min_width(out), 680)

    def test_02_long_evidence_column_wider_than_year_column(self):
        """核心回归：依据列必须明显宽于年份列，否则中文被压成竖排。"""
        w = widths(rr.enhance_tables(ANOMALY))
        self.assertGreater(w[-1], w[0] * 1.8)

    def test_03_semantic_cell_markers(self):
        out = rr.enhance_tables(ANOMALY)
        for role in ('cell-status', 'cell-tight', 'cell-key', 'cell-year', 'num'):
            self.assertIn(role, out)
        # v2.1.6：列类按「首列 → 年份 → 数值 → 短列」的固定顺序打，
        # 且 th 与 td 必须是同一组（见 TestColumnAlignment）。
        self.assertIn('class="cell-key cell-year num cell-tight"', out)

    def test_04_badge_column_gets_extra_weight(self):
        w_badge = widths(rr.enhance_tables(ANOMALY))
        plain = ANOMALY.replace('<span class="src-tag a">已闭环</span> ', '')
        w_plain = widths(rr.enhance_tables(plain))
        self.assertGreater(w_badge[2], w_plain[2])

    def test_05_idempotent(self):
        once = rr.enhance_tables(ANOMALY)
        self.assertEqual(rr.enhance_tables(once), once)
        self.assertEqual(once.count('class="table-wrap table-scroll"'), 1)
        self.assertEqual(once.count('<colgroup>'), 1)

    def test_06_existing_wrapper_not_nested(self):
        out = rr.enhance_tables('<div class="table-scroll">' + NINE_COL + '</div>')
        self.assertEqual(out.count('class="table-wrap table-scroll"'), 1)
        self.assertNotIn('table-scroll"><div class="table-wrap', out)

    def test_07_nine_column_table_fits_body_width(self):
        out = rr.enhance_tables(NINE_COL)
        self.assertEqual(len(widths(out)), 9)
        # v2.1.6：宽表收紧到正文宽度内，末列不再被横向裁掉半截
        self.assertGreaterEqual(min_width(out), 680)
        self.assertLessEqual(min_width(out), 900)
        self.assertIn('table-wide', out)
        self.assertGreaterEqual(out.count('class="num'), 9)

    def test_08_src_table_class_preserved(self):
        src = NINE_COL.replace('<table>', '<table class="src-table">', 1)
        out = rr.enhance_tables(src)
        self.assertIn('src-table data-table', out)

    def test_09_colspan_row_does_not_change_column_count(self):
        t = ('<table><thead><tr><th>A</th><th>B</th><th>C</th><th>D</th></tr></thead>'
             '<tbody><tr><td colspan="4">未登记来源</td></tr>'
             '<tr><td>2025</td><td>1.41</td><td>L3</td><td>东财</td></tr>'
             '</tbody></table>')
        out = rr.enhance_tables(t)
        self.assertEqual(len(widths(out)), 4)

    def test_10_script_and_style_untouched(self):
        frag = ('<script>var s="<table><tr><td>X</td></tr></table>";</script>'
                '<style>.x{content:"<table>";}</style>' + ANOMALY)
        out = rr.enhance_tables(frag)
        self.assertIn('var s="<table><tr><td>X</td></tr></table>";', out)
        self.assertIn('.x{content:"<table>";}', out)
        self.assertEqual(out.count('data-table'), 1)   # 只有正文那张表被增强

    def test_11_empty_table_does_not_crash(self):
        self.assertIn('<table', rr.enhance_tables('<table></table>'))

    def test_12_no_colgroup_when_table_has_no_rows(self):
        out = rr.enhance_tables('<table><tbody></tbody></table>')
        self.assertNotIn('<colgroup>', out)

    def test_13_widths_are_finite_and_positive(self):
        for frag in (ANOMALY, NINE_COL):
            w = widths(rr.enhance_tables(frag))
            self.assertTrue(all(0 < x < 100 for x in w))

    def test_14_existing_inline_style_preserved(self):
        t = NINE_COL.replace('<table>', '<table style="font-size:12px;">', 1)
        out = rr.enhance_tables(t)
        self.assertIn('font-size:12px;', out)
        self.assertIn('min-width:', out)

    def test_15_code_and_ref_markup_survives(self):
        t = ANOMALY.replace('属报表范围变化',
                            '<code>KNOWLEDGE_INDEX.md</code><a class="ref" href="https://x">↗</a>属报表范围变化')
        out = rr.enhance_tables(t)
        self.assertIn('<code>KNOWLEDGE_INDEX.md</code>', out)
        self.assertIn('<a class="ref"', out)


class TestChartHeadroom(unittest.TestCase):

    BAR = ("<script>window.__reg('chart16',{type:'bar',"
           "options:{scales:{y:{ticks:{callback:v=>v+'%'}}}}});</script>")

    def test_16_bar_without_explicit_max_gets_grace(self):
        out = rr.relax_bar_headroom([self.BAR])[0]
        self.assertIn("grace:'12%'", out)
        self.assertIn("scales:{y:{grace:'12%',ticks:", out)

    def test_17_bar_with_explicit_max_untouched(self):
        s = self.BAR.replace('scales:{y:{', 'scales:{y:{max:300,')
        self.assertNotIn('grace', rr.relax_bar_headroom([s])[0])

    def test_18_line_chart_untouched(self):
        s = self.BAR.replace("type:'bar'", "type:'line'")
        self.assertNotIn('grace', rr.relax_bar_headroom([s])[0])

    def test_19_idempotent(self):
        once = rr.relax_bar_headroom([self.BAR])[0]
        self.assertEqual(rr.relax_bar_headroom([once])[0], once)

    def test_20_empty_scripts(self):
        self.assertEqual(rr.relax_bar_headroom([]), [])
        self.assertEqual(rr.relax_bar_headroom(None), [])

    def test_21_boot_moves_labels_outside_bars(self):
        for token in ("align='top'", 'offset=3', 'clamp=false', 'padding.top=22'):
            self.assertIn(token, rr.BOOT)


class TestTableCSS(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.css = (SK / 'assets' / 'sevenstep-adapt.css').read_text(encoding='utf-8')

    def test_22_fixed_layout_and_nowrap_rules(self):
        for rule in ('table-layout:fixed', 'td.cell-tight{white-space:nowrap;}',
                     'td.num{', 'font-variant-numeric:tabular-nums'):
            self.assertIn(rule, self.css)

    def test_23_badge_never_wraps(self):
        self.assertIn('white-space:nowrap;flex:none', self.css)

    def test_24_overflow_wrap_and_scrollbar(self):
        self.assertIn('overflow-wrap:anywhere', self.css)
        self.assertIn('::-webkit-scrollbar', self.css)


class TestP014Gate(unittest.TestCase):

    def setUp(self):
        self.good = rr.enhance_tables(ANOMALY)

    def test_25_compliant_table_no_p014(self):
        out = _run_gate(_doc(self.good))
        self.assertNotIn('P0-14', out)

    def test_26_bare_table_blocked(self):
        bare = re.sub(r'<table[^>]*>', '<table>', self.good)
        bare = re.sub(r'<colgroup>.*?</colgroup>', '', bare, flags=re.S)
        out = _run_gate(_doc(bare))
        self.assertIn('P0-14', out)
        self.assertIn('裸 table', out)

    def test_27_missing_colgroup_blocked(self):
        out = _run_gate(_doc(re.sub(r'<colgroup>.*?</colgroup>', '',
                                    self.good, flags=re.S)))
        self.assertIn('列宽契约', out)

    def test_28_bad_width_sum_blocked(self):
        bad = re.sub(r'<col style="width:[\d.]+%">',
                     '<col style="width:1%">', self.good, count=1)
        out = _run_gate(_doc(bad))
        self.assertIn('列宽契约', out)

    def test_29_missing_min_width_blocked(self):
        out = _run_gate(_doc(re.sub(r'min-width:\d+px;', '', self.good)))
        self.assertIn('缺 min-width', out)

    def test_30_missing_css_rule_blocked(self):
        out = _run_gate(_doc(self.good, css_ok=False))
        self.assertIn('缺表格规则', out)

    def test_31_missing_chart_label_config_blocked(self):
        out = _run_gate(_doc(self.good, boot_ok=False))
        self.assertIn('图表数据标签', out)

    def test_32_col_count_mismatch_blocked(self):
        # 删掉一个 col，制造列数不符
        bad = re.sub(r'(<colgroup>)<col [^>]*>', r'\1', self.good, count=1)
        out = _run_gate(_doc(bad))
        self.assertIn('P0-14', out)


# ---------------------------------------------------------------------------
# v2.1.6 列级对齐（用户反馈「表头与数据没对齐」的根因回归）
# ---------------------------------------------------------------------------
MIXED = (
    '<table><thead><tr><th>年份</th><th>营业收入(亿元)</th><th>净利率</th>'
    '</tr></thead><tbody>'
    '<tr><td>2025</td><td>862.42<a class="ref" href="https://x">↗</a></td>'
    '<td>40.52%</td></tr>'
    '<tr><td>2024</td><td>844.92</td><td>38.97%</td></tr>'
    '</tbody></table>')

DATES = (
    '<table><thead><tr><th>项目</th><th>抓取日期</th><th>颗粒度</th></tr></thead>'
    '<tbody><tr><td>一致预期</td><td>2026-11-09</td><td>L3</td></tr>'
    '<tr><td>行情快照</td><td>2026-11-09</td><td>L2</td></tr>'
    '</tbody></table>')


def col_classes(out):
    """返回 (thead 各列 class 集合, tbody 首行各列 class 集合)。"""
    h = re.search(r'<thead[^>]*>(.*?)</thead>', out, re.S)
    b = re.search(r'<tbody[^>]*>\s*<tr[^>]*>(.*?)</tr>', out, re.S)

    def grab(seg, tag):
        out_cols = []
        for attrs in re.findall(r'<%s\b([^>]*)>' % tag, seg, re.I):
            m = re.search(r'class="([^"]*)"', attrs)
            out_cols.append(set(m.group(1).split()) if m else set())
        return out_cols
    return grab(h.group(1), 'th'), grab(b.group(1), 'td')


class TestColumnAlignment(unittest.TestCase):

    def test_33_th_and_td_share_exact_column_classes(self):
        """根因回归：表头与数据同一列必须是同一组语义类。"""
        th, td = col_classes(rr.enhance_tables(MIXED))
        self.assertEqual(len(th), len(td))
        self.assertEqual(th, td)

    def test_34_annotated_number_and_plain_number_same_column_role(self):
        """「862.42↗」带角标与「844.92」纯数字，整列都必须是 num。"""
        out = rr.enhance_tables(MIXED)
        rows = re.findall(r'<tbody[^>]*>(.*?)</tbody>', out, re.S)[0]
        tds = [re.findall(r'<td\b([^>]*)>', r, re.I)
               for r in re.findall(r'<tr\b[^>]*>(.*?)</tr>', rows, re.S)]
        self.assertIn('num', tds[0][1])
        self.assertIn('num', tds[1][1])
        self.assertIn('num', col_classes(out)[0][1])

    def test_35_year_column_is_narrower_than_text_column(self):
        w = widths(rr.enhance_tables(ANOMALY))
        out = rr.enhance_tables(ANOMALY)
        self.assertIn('cell-year', out)
        self.assertLess(w[0], w[-1] / 2)

    def test_36_header_unit_never_split(self):
        """「财务费用(亿元)」的括注必须整体 nowrap，不能被拆成两半。"""
        t = ('<table><thead><tr><th>年份</th><th>财务费用(亿元)</th></tr></thead>'
             '<tbody><tr><td>2025</td><td>93.71</td></tr>'
             '<tr><td>2024</td><td>111.31</td></tr></tbody></table>')
        out = rr.enhance_tables(t)
        self.assertIn('<span class="unit">(亿元)</span>', out)
        self.assertEqual(out.count('class="unit"'), 1)
        # 幂等：二次增强不会重复包 span
        self.assertEqual(rr.enhance_tables(out), out)

    def test_37_iso_date_is_label_not_number(self):
        th, td = col_classes(rr.enhance_tables(DATES))
        self.assertNotIn('num', th[1])
        self.assertNotIn('num', td[1])

    def test_38_first_column_keeps_cell_key_on_both_rows(self):
        th, td = col_classes(rr.enhance_tables(MIXED))
        self.assertIn('cell-key', th[0])
        self.assertIn('cell-key', td[0])

    def test_39_wide_table_min_width_fits_body(self):
        self.assertLessEqual(min_width(rr.enhance_tables(NINE_COL)), 900)

    def test_40_column_roles_helper_detects_mismatch(self):
        """helper 自身有效性：手工破坏后必须能看出不一致（防止测试恒真）。"""
        broken = rr.enhance_tables(MIXED).replace(
            'class="cell-key cell-year', 'class="cell-keyX cell-year', 1)
        th, td = col_classes(broken)
        self.assertNotEqual(th, td)


class TestP014AlignmentGate(unittest.TestCase):

    def setUp(self):
        self.good = rr.enhance_tables(MIXED)

    def test_41_compliant_alignment_no_p014(self):
        self.assertNotIn('P0-14', _run_gate(_doc(self.good)))

    def test_42_header_missing_num_blocked(self):
        bad = self.good.replace('<th class="cell-key cell-year num cell-tight">',
                                '<th class="cell-key cell-year cell-tight">', 1)
        out = _run_gate(_doc(bad))
        self.assertIn('P0-14', out)
        self.assertIn('列类不一致', out)

    def test_43_body_missing_num_blocked(self):
        bad = re.sub(r'(<td class=")num cell-tight(">40\.52%)',
                     r'\1cell-tight\2', self.good, count=1)
        out = _run_gate(_doc(bad))
        self.assertIn('P0-14', out)

    def test_44_missing_column_alignment_css_blocked(self):
        out = _run_gate(_doc(self.good, css_extra=False))
        self.assertIn('缺表格规则', out)

    def test_45_real_css_has_all_alignment_rules(self):
        css = (SK / 'assets' / 'sevenstep-adapt.css').read_text(encoding='utf-8')
        for rule in ('text-align:left;', '.data-table thead th.cell-key',
                     '.data-table tbody td.num.cell-tight',
                     '.data-table thead th .unit',
                     '.data-table thead th.num{text-align:right;letter-spacing:0;}'):
            self.assertIn(rule, css)


if __name__ == '__main__':
    unittest.main(verbosity=2)
