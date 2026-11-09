#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""七步财报分析 skill · v2.1.3 缺陷回归测试。

覆盖 2026-11-09 全量审计中可复现的 P0 / P1 缺陷：
  - 单位量纲归一（整图统一尺度 / 1.0 阈值 / 脏值 null / 混合形态告警）
  - Phase 0 员工块（技术 / 研发四种源形态不再误阻断）
  - HTML 门禁（body 变量污染、重复 ID、远程资源、库特征串、提示卡属性顺序）
  - 生成器（16 容器幂等注入、ticks.callback null 安全）
  - 前瞻短行、版本与资产清单

运行：python3 -m unittest discover -s tests -v
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parent.parent
SCRIPTS = SK / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import build_forecast as bf            # noqa: E402
import build_headcount as bhc          # noqa: E402
import build_report_data as brd        # noqa: E402
import check_html as ch                # noqa: E402
import render_report as rr             # noqa: E402
import validate_output as vo           # noqa: E402


def _run_gate(html_text):
    """把片段交给真实门禁脚本，返回合并输出。"""
    with tempfile.TemporaryDirectory(prefix='sevenstep_gate_') as d:
        p = Path(d) / 'r.html'
        p.write_text(html_text, encoding='utf-8')
        r = subprocess.run([sys.executable, str(SCRIPTS / 'check_html.py'),
                            str(p), '--strict-p1', '--no-js'],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace')
        return r.stdout + r.stderr


class TestUnitNormalization(unittest.TestCase):
    def test_fraction_form_scaled(self):
        self.assertEqual(brd.normalize_pct_matrix([[0.6579, 0.62]]), [[65.79, 62.0]])

    def test_percent_form_untouched(self):
        self.assertEqual(brd.normalize_pct_matrix([[23.0, 25.0]]), [[23.0, 25.0]])

    def test_real_small_percent_not_scaled(self):
        # 阈值 1.5 会把真实的 1.2% 占比 ×100 成 120%（图7 y 轴 max:100 直接裁掉）
        self.assertEqual(brd.normalize_pct_matrix([[1.2, 2.3]]), [[1.2, 2.3]])

    def test_all_null_and_dirty_values(self):
        self.assertEqual(brd.normalize_pct_matrix([[None, None]]), [[None, None]])
        self.assertEqual(brd.normalize_pct_matrix([['N/A', 0.5]]), [[None, 50.0]])

    def test_cross_segment_single_scale(self):
        # 旧逻辑逐板块判定，同一张图会同时出现 65.79 和 0.23 两套量纲
        rows = [[0.6579, 0.62], [0.23, 0.25]]
        self.assertEqual(brd.normalize_pct_matrix(rows), [[65.79, 62.0], [23.0, 25.0]])

    def test_parse_segments_both_forms(self):
        names, seg7, seg8 = brd.parse_segments({
            '电力-收入占比': [0.8799, 0.88], '电力-毛利率': [0.6579, 0.65],
            '其他-收入占比': [0.1201, 0.12], '其他-毛利率': [0.3154, 0.31],
        })
        self.assertEqual(names, ['电力', '其他'])
        self.assertEqual(seg7[0][0], 87.99)
        self.assertEqual(seg8[0][0], 65.79)

    def test_peer_dirty_value_is_null_not_zero(self):
        with tempfile.TemporaryDirectory(prefix='sevenstep_peer_') as d:
            p = Path(d) / 'peer.csv'
            p.write_text('报告期,公司,代码,毛利率_pct,净利率_pct,资产负债率_pct\n'
                         '2025年报,A,600000.SH,,N/A,58.2\n', encoding='utf-8')
            out = brd.parse_peer(str(p))
        self.assertEqual(out['CHART16_DATA_GROSS_MARGIN'], [None])
        self.assertEqual(out['CHART16_DATA_NET_MARGIN'], [None])
        self.assertEqual(out['CHART16_DATA_DEBT_RATIO'], [58.2])

    def test_hist_cagr_empty(self):
        self.assertIsNone(brd.hist_cagr([]))


class TestEmployeeBlock(unittest.TestCase):
    YEARS = ['2025年年报', '2024年年报']

    def _data(self, tech=None, rd=None):
        d = {
            '职工总数': {y: 100 for y in self.YEARS},
            '生产人员': {y: 20 for y in self.YEARS},
            '销售人员': {y: 10 for y in self.YEARS},
            '财务人员': {y: 5 for y in self.YEARS},
            '行政管理人员': {y: 5 for y in self.YEARS},
            '博士': {y: 10 for y in self.YEARS},
            '硕士': {y: 20 for y in self.YEARS},
            '本科': {y: 30 for y in self.YEARS},
            '大专': {y: 40 for y in self.YEARS},
        }
        if tech is not None:
            d['技术人员'] = {y: tech for y in self.YEARS}
        if rd is not None:
            d['研发人员'] = {y: rd for y in self.YEARS}
        return d

    def _names(self, tech, rd):
        block, _ = bhc.build_emp_block(self._data(tech, rd), self.YEARS)
        return [r[0] for r in block]

    def test_no_rd_no_empty_placeholder(self):
        names = self._names(60, None)
        self.assertIn('技术人员', names)
        self.assertNotIn('研发人员', names)

    def test_only_rd_replaces_tech(self):
        names = self._names(None, 60)
        self.assertIn('研发人员', names)
        self.assertNotIn('技术人员', names)

    def test_same_source_drops_rd(self):
        names = self._names(60, 60)
        self.assertIn('技术人员', names)
        self.assertNotIn('研发人员', names)

    def test_different_source_keeps_both(self):
        names = self._names(60, 30)
        self.assertIn('技术人员', names)
        self.assertIn('研发人员', names)

    def _validate_rows(self, tech, rd):
        d = self._data(tech, rd)
        rows = [['员工构成（按专业 / 学历 / 人均派生）'] + [''] * 4]
        for k in ('职工总数', '生产人员', '销售人员', '财务人员',
                  '技术人员', '研发人员', '行政管理人员', '博士', '硕士', '本科', '大专'):
            if k not in d:
                continue
            rows.append([k] + [d[k][y] for y in self.YEARS] + ['', ''])
        return vo.check_employee(rows, self.YEARS)

    def _dup_flag(self, tech, rd):
        for label, ok, _ in self._validate_rows(tech, rd):
            if label.startswith('员工·技术≠研发重复相加'):
                return ok
        self.fail('未产出技术/研发判定项')

    def test_validator_allows_different_source(self):
        self.assertTrue(self._dup_flag(60, 30))

    def test_validator_allows_only_rd(self):
        self.assertTrue(self._dup_flag(None, 60))

    def test_validator_blocks_true_duplicate(self):
        self.assertFalse(self._dup_flag(60, 60))

    def test_validator_closure_with_only_rd(self):
        # 只有研发时职能合计必须把研发算进去，否则合计=40 vs 总数=100
        for label, ok, _ in self._validate_rows(None, 60):
            if label.startswith('员工·职能合计=职工总数'):
                self.assertTrue(ok)
                return
        self.fail('未产出职能合计判定项')


class TestForecastShortRows(unittest.TestCase):
    def test_missing_institution_column_no_keyerror(self):
        rows = [
            {'年份': '2026E', '营收预测': '100', '机构': 'A',
             '口径标注': '权威主源', '来源日期': '2026-11-01'},
            {'年份': '2027E', '营收预测': '110',
             '口径标注': '权威主源', '来源日期': '2026-11-01'},
        ]
        bf.build_consensus(rows, {'营收': 86241940222.0, '归母': 34502809176.0})
        # 旧版 r['机构'] 直接 KeyError

    def test_alt_date_formats_parsed(self):
        self.assertEqual(len(bf.stale_rows([
            {'机构': 'A', '来源日期': '2020/01/01'}], 30)), 1)
        self.assertEqual(len(bf.stale_rows([
            {'机构': 'A', '来源日期': '2020.01.01'}], 30)), 1)


class TestHtmlGate(unittest.TestCase):
    LIBS = ('<!-- chart.umd.min.js (inlined, 120010 bytes) -->'
            '<script>/* Chart v4 */ var Chart=function(){};' + 'x' * 120000 + '</script>'
            '<!-- chartjs-plugin-datalabels.min.js (inlined, 9000 bytes) -->'
            '<script>/* ChartDataLabels */' + 'y' * 9000 + '</script>')

    def test_empty_note_attribute_order(self):
        self.assertEqual(
            ch.empty_note_ids('<div data-chart="chart7" class="chart-empty-note"></div>'),
            {'chart7'})

    def test_body_pollution_fixed(self):
        # 旧版 body 被内联库源码覆盖，P1-1 / P1-2 恒不触发
        out = _run_gate('<html><head></head><body><div class="step-card">'
                        '**粗体** 😀 |---|</div>' + self.LIBS + '</body></html>')
        self.assertIn('P1-1', out)
        self.assertIn('P1-2', out)

    def test_duplicate_canvas_ids_rejected(self):
        cv = ''.join('<canvas id="chart1"></canvas>' for _ in range(16))
        regs = ''.join("<script>window.__reg('chart1',{});</script>" for _ in range(16))
        out = _run_gate('<html><body>' + cv + regs + self.LIBS + '</body></html>')
        self.assertIn('canvas ID 重复', out)

    def test_single_quote_remote_resource_rejected(self):
        out = _run_gate('<html><body><script src=\'https://evil.example/a.js\'></script>'
                        + self.LIBS + '</body></html>')
        self.assertIn('P0-3 远程资源', out)

    def test_fake_inlined_lib_rejected(self):
        fake = ('<!-- chart.umd.min.js (inlined, 120010 bytes) -->'
                '<script>' + 'z' * 120010 + '</script>'
                '<!-- chartjs-plugin-datalabels.min.js (inlined, 9000 bytes) -->'
                '<script>' + 'y' * 9000 + '</script>')
        out = _run_gate('<html><body>' + fake + '</body></html>')
        self.assertIn('不含特征串 Chart', out)

    def test_unsafe_ticks_callback_rejected(self):
        reg = ("<script>window.__reg('chart8',{options:{scales:{y:"
               "{ticks:{callback:v=>v.toFixed(1)+'%'}}}}});</script>")
        out = _run_gate('<html><body>' + reg + self.LIBS + '</body></html>')
        self.assertIn('P0-12', out)


class TestRenderer(unittest.TestCase):
    def test_inject_containers_idempotent(self):
        cfg = {'steps': [{'html': '<p>step</p>'} for _ in range(9)]}
        rr.inject_chart_containers(cfg)
        html = '\n'.join(s['html'] for s in cfg['steps'])
        self.assertEqual(len(re.findall(r'<canvas id="chart\d+"></canvas>', html)), 16)
        self.assertEqual(html.count('class="chart-card"'), 16)
        self.assertEqual(html.count('class="chart-idx"'), 16)
        rr.inject_chart_containers(cfg)
        html2 = '\n'.join(s['html'] for s in cfg['steps'])
        self.assertEqual(len(re.findall(r'<canvas id="chart\d+"></canvas>', html2)), 16)

    def test_existing_containers_not_duplicated(self):
        cfg = {'steps': [{'html': '<canvas id="chart1"></canvas>' if i == 0 else ''}
                         for i in range(9)]}
        rr.inject_chart_containers(cfg)
        html = '\n'.join(s['html'] for s in cfg['steps'])
        self.assertEqual(html.count('<canvas id="chart1"'), 1)
        self.assertEqual(len(re.findall(r'<canvas id="chart\d+"></canvas>', html)), 16)

    def test_custom_caption_override(self):
        cfg = {'steps': [{'html': ''} for _ in range(9)],
               'chart_captions': {'16': '自定义同行标题'}}
        rr.inject_chart_containers(cfg)
        self.assertIn('自定义同行标题', cfg['steps'][8]['html'])

    def test_harden_null_formatters_covers_callback(self):
        src = ("<script>window.__reg('chart8',{options:{scales:{y:{ticks:"
               "{callback:v=>Number(v.toFixed(1))+'%'}}}}});</script>")
        out = rr.harden_null_formatters([src])[0]
        self.assertIn('v===null', out)
        self.assertNotIn('v.toFixed(', out)

    def test_harden_null_formatters_covers_v_plus_percent(self):
        src = "<script>window.__reg('chart3',{callback:v=>v+'%'});</script>"
        out = rr.harden_null_formatters([src])[0]
        self.assertIn('v===null', out)


class TestPackageIntegrity(unittest.TestCase):
    def test_version_and_brand(self):
        skill_md = (SK / 'SKILL.md').read_text(encoding='utf-8')
        m = re.search(r'^version:\s*(\S+)', skill_md, re.M)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), '2.1.3')
        self.assertNotIn('松幽Ai提效', skill_md)
        brand = json.loads((SK / 'assets' / 'brand.json').read_text(encoding='utf-8'))
        self.assertEqual(brand['video'], '松幽AI')

    def test_runtime_assets_present(self):
        required = [
            'assets/hydro-base.css', 'assets/hydro-skin.css', 'assets/sevenstep-adapt.css',
            'assets/chart.umd.min.js', 'assets/chartjs-plugin-datalabels.min.js',
            'assets/brand.json', 'report_template.html',
            'scripts/render_report.py', 'scripts/check_html.py',
            'scripts/build_report_data.py', 'scripts/orchestrate.py',
            'scripts/capture.py', 'references/hydro-design-spec.md',
        ]
        missing = [r for r in required if not (SK / r).exists()]
        self.assertEqual(missing, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
