#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""七步财报分析 · v2.1.4 来源可核查回归测试。

覆盖 v2.1.4 新增的：
  - check_html.split_source_refs / is_pure_domain / source_domains（P0-3 白名单 + P0-13 辅助）
  - verify_links.collect / probe（链接验活，mock 掉 _request_code）
  - render_report.ref / build_source_summary / apply_link_patches（角标与六元组汇总）
  - P0-13 静态门禁集成（合规文档不报 P0-13；逐项破坏必报 P0-13）
  - P0-3 远程资源仍阻断 / 合规来源角标放行

运行：python3 -m unittest discover -s tests -v
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SK = Path(__file__).resolve().parent.parent
SCRIPTS = SK / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import check_html as ch            # noqa: E402
import render_report as rr         # noqa: E402
import verify_links as vl          # noqa: E402


def _run_gate(html_text):
    """把片段交给真实门禁脚本，返回合并输出（复用 test_regressions 的 _run_gate 思路）。"""
    with tempfile.TemporaryDirectory(prefix='sevenstep_sources_') as d:
        p = Path(d) / 'r.html'
        p.write_text(html_text, encoding='utf-8')
        r = subprocess.run([sys.executable, str(SCRIPTS / 'check_html.py'),
                            str(p), '--strict-p1', '--no-js'],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace')
        return r.stdout + r.stderr


# ---------------------------------------------------------------------------
# 最小合规文档构造：只针对 P0-13，其他 P0（皮肤/16 图等）会失败，不做整体通过断言
# ---------------------------------------------------------------------------
DOMAINS = ('d1.example.com', 'd2.example.com', 'd3.example.com',
           'd4.example.com', 'd5.example.com', 'd6.example.com')


def make_urls(n_refs, n_domains):
    """n_refs 个唯一、带路径、非纯域名、无查询串的 URL，分布在 n_domains 个域名。"""
    return ['https://%s/page/%d' % (DOMAINS[i % n_domains], i)
            for i in range(n_refs)]


def _compliant_doc(n_refs=12, n_domains=6):
    """含全部 P0-13 要素的最小 HTML：≥12 合规角标 / ≥5 域名 / 六元组表 /
    每条 URL 在 id="src-summary" 之后登记 / 取数日期 / source-meta /
    source-box / status-badge / href="#src-summary" 页内跳转。"""
    urls = make_urls(n_refs, n_domains)
    refs = ''.join(
        '<a class="ref" href="%s" target="_blank" rel="noopener" title="来源%d">↗</a>'
        % (u, i) for i, u in enumerate(urls))
    rows = ''.join(
        '<tr><td>值%d</td><td>年报口径</td><td>页面标题%d</td>'
        '<td>2025-01-01</td><td>%s</td><td>2026-11-09</td></tr>'
        % (i, i, u) for i, u in enumerate(urls))
    header = ('<thead><tr><th>数值</th><th>口径</th><th>页面标题</th>'
              '<th>发布日期</th><th>可核查链接</th><th>抓取日期</th></tr></thead>')
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><title>t</title></head><body>\n'
        '<header class="hero">数据截至 2026-11-09</header>\n'
        '<p>正文关键数据 ' + refs + '</p>\n'
        '<div class="source-box">数据来源 '
        '<span class="status-badge status-resolved">已验证</span> '
        '<a href="#src-summary">核查来源汇总（六元组）</a></div>\n'
        '<div id="src-summary" class="src-summary">\n'
        '<div id="source-meta" data-fetched-at="2026-11-09" '
        'data-tier="L1" data-online-checked="6/6"></div>\n'
        '<table>' + header + '<tbody>' + rows + '</tbody></table>\n'
        '</div>\n'
        '</body></html>\n')


class TestSplitSourceRefs(unittest.TestCase):
    def test_compliant_ref_allowed(self):
        allowed, bad = ch.split_source_refs(
            '<a class="ref" href="https://x.example/a" target="_blank" '
            'rel="noopener">↗</a>')
        self.assertIn('https://x.example/a', allowed)
        self.assertEqual(bad, [])

    def test_missing_target_rejected(self):
        allowed, _ = ch.split_source_refs(
            '<a class="ref" href="https://x.example/a" rel="noopener">↗</a>')
        self.assertNotIn('https://x.example/a', allowed)

    def test_missing_rel_rejected(self):
        allowed, _ = ch.split_source_refs(
            '<a class="ref" href="https://x.example/a" target="_blank">↗</a>')
        self.assertNotIn('https://x.example/a', allowed)

    def test_class_without_ref_skipped(self):
        allowed, bad = ch.split_source_refs(
            '<a class="reference" href="https://x.example/a" '
            'target="_blank" rel="noopener">x</a>')
        self.assertEqual(allowed, set())
        self.assertEqual(bad, [])

    def test_relative_href_skipped(self):
        allowed, bad = ch.split_source_refs(
            '<a class="ref" href="/local/page" target="_blank" '
            'rel="noopener">x</a>')
        self.assertEqual(allowed, set())
        self.assertEqual(bad, [])

    def test_ampersand_unescaped(self):
        allowed, _ = ch.split_source_refs(
            '<a class="ref" href="https://x.example/a?b=1&amp;c=2" '
            'target="_blank" rel="noopener">↗</a>')
        self.assertIn('https://x.example/a?b=1&c=2', allowed)


class TestDomainHelpers(unittest.TestCase):
    def test_is_pure_domain_true(self):
        self.assertTrue(ch.is_pure_domain('https://www.eastmoney.com/'))

    def test_is_pure_domain_with_path_query_fragment_false(self):
        for u in ('https://www.eastmoney.com/a/b.html',
                  'https://www.eastmoney.com/?code=600900',
                  'https://www.eastmoney.com/#page=7'):
            with self.subTest(u=u):
                self.assertFalse(ch.is_pure_domain(u))

    def test_source_domains_dedup_sorted(self):
        urls = ['https://www.eastmoney.com/a', 'https://www.eastmoney.com/b',
                'https://x.example.com/p', 'https://b.example.com/p']
        self.assertEqual(
            ch.source_domains(urls),
            sorted(['www.eastmoney.com', 'x.example.com', 'b.example.com']))


class TestVerifyLinks(unittest.TestCase):
    def test_collect_unescape_and_dedup(self):
        text = ('<a href="https://x.example/a?b=1&amp;c=2">1</a>'
                '<a href=\'https://x.example/a?b=1&amp;c=2\'>2</a>'
                '<a href="https://y.example/p">3</a>'
                '<a href="https://y.example/p">4</a>')
        self.assertEqual(vl.collect(text),
                         ['https://x.example/a?b=1&c=2', 'https://y.example/p'])

    def test_probe_head_404_get_200_ok(self):
        with patch.object(vl, '_request_code', side_effect=[404, 200]) as m:
            st, _ = vl.probe('https://x.example/a', 3)
        self.assertEqual(st, 'ok')
        self.assertEqual(m.call_count, 2)

    def test_probe_head_403_skip(self):
        with patch.object(vl, '_request_code', side_effect=[403]) as m:
            st, _ = vl.probe('https://x.example/a', 3)
        self.assertEqual(st, 'skip')
        self.assertEqual(m.call_count, 1)

    def test_probe_head_200_ok(self):
        with patch.object(vl, '_request_code', side_effect=[200]) as m:
            st, _ = vl.probe('https://x.example/a', 3)
        self.assertEqual(st, 'ok')
        self.assertEqual(m.call_count, 1)

    def test_probe_network_none_skip(self):
        with patch.object(vl, '_request_code', side_effect=[None]) as m:
            st, _ = vl.probe('https://x.example/a', 3)
        self.assertEqual(st, 'skip')
        self.assertEqual(m.call_count, 1)

    def test_probe_head_500_get_500_dead(self):
        with patch.object(vl, '_request_code', side_effect=[500, 500]) as m:
            st, _ = vl.probe('https://x.example/a', 3)
        self.assertEqual(st, 'dead')
        self.assertEqual(m.call_count, 2)


class TestRenderSources(unittest.TestCase):
    def test_ref_ampersand_escaped(self):
        out = rr.ref({'k': {'url': 'https://x.example/a?b=1&c=2',
                            'title': 'T'}}, 'k')
        self.assertIn('href="https://x.example/a?b=1&amp;c=2"', out)

    def test_ref_required_attributes(self):
        out = rr.ref({'k': {'url': 'https://x.example/a'}}, 'k')
        self.assertIn('class="ref"', out)
        self.assertIn('target="_blank"', out)
        self.assertIn('rel="noopener"', out)

    def test_ref_missing_url_empty(self):
        self.assertEqual(rr.ref({'k': {'title': 'T'}}, 'k'), '')
        self.assertEqual(rr.ref({}, 'k'), '')

    def test_build_source_summary_contract(self):
        cfg = {
            'sources': {'k': {'url': 'https://x.example/a', 'title': '页面标题A',
                              'value': '862.42', 'caliber': '年报', 'org': 'X',
                              'published_at': '2025-01-01',
                              'fetched_at': '2026-11-09', 'level': 'L1'}},
            'source_meta': {'fetched_at': '2026-11-09', 'tier': 'L1',
                            'online_checked': {'a': True}},
        }
        out = rr.build_source_summary(cfg)
        for kw in ('id="src-summary"', 'id="source-meta"', 'data-fetched-at',
                   'data-online-checked', '口径', '页面标题', '发布日期', '抓取日期'):
            with self.subTest(kw=kw):
                self.assertIn(kw, out)
        self.assertNotIn('class="step-card"', out)


class TestP013Integration(unittest.TestCase):
    def _assert_p013(self, doc, keyword):
        out = _run_gate(doc)
        self.assertIn('P0-13', out)
        self.assertIn(keyword, out)

    def test_compliant_doc_no_p013(self):
        # 最小 HTML 会触发其他 P0（皮肤 / 16 图等），只针对 P0-13 断言，不断言整体通过
        self.assertNotIn('P0-13', _run_gate(_compliant_doc()))

    def test_break_remove_src_summary(self):
        doc = _compliant_doc().replace(
            '<div id="src-summary" class="src-summary">',
            '<div class="src-summary">', 1)
        self._assert_p013(doc, '来源汇总锚点区')

    def test_break_refs_to_11(self):
        self._assert_p013(_compliant_doc(n_refs=11), '可点击来源角标仅 11 个')

    def test_break_domains_to_4(self):
        self._assert_p013(_compliant_doc(n_domains=4), '独立来源域名仅 4 个')

    def test_break_pure_domain(self):
        u0 = make_urls(12, 6)[0]
        doc = _compliant_doc().replace(u0, 'https://pure.example.com/')
        self._assert_p013(doc, '纯域名首页')

    def test_break_unregistered_url(self):
        u0 = make_urls(12, 6)[0]
        doc = _compliant_doc().replace('<td>%s</td>' % u0, '<td>—</td>', 1)
        self._assert_p013(doc, '未在 src-summary 六元组表登记')

    def test_break_remove_source_meta(self):
        doc = _compliant_doc().replace(
            '<div id="source-meta" data-fetched-at="2026-11-09" '
            'data-tier="L1" data-online-checked="6/6"></div>', '')
        self._assert_p013(doc, '本轮联网核实留痕')

    def test_break_remove_status_badge(self):
        doc = _compliant_doc().replace('status-badge status-resolved', '', 1)
        self._assert_p013(doc, '缺状态徽章')

    def test_break_remove_jump(self):
        doc = _compliant_doc().replace('href="#src-summary"',
                                       'href="#appendix"', 1)
        self._assert_p013(doc, '页内跳转')

    def test_break_missing_column_header(self):
        doc = _compliant_doc().replace('<th>抓取日期</th>',
                                       '<th>颗粒度</th>', 1)
        self._assert_p013(doc, '缺六元组列「抓取日期」')

    def test_remote_script_blocked_by_p03(self):
        doc = _compliant_doc().replace(
            '<body>', '<body>\n<script src="https://cdn.example/a.js"></script>', 1)
        self.assertIn('P0-3 远程资源依赖', _run_gate(doc))

    def test_compliant_refs_not_blocked_by_p03(self):
        out = _run_gate(_compliant_doc())
        self.assertNotIn('P0-3 远程资源依赖', out)
        self.assertNotIn('来源角标缺 target', out)


class TestApplyLinkPatches(unittest.TestCase):
    def test_patch_only_text_not_script(self):
        frag = '<p>862.42</p><script>var x="862.42";</script>'
        patches = [{'step': 1, 'after': '862.42', 'src': 'k'}]
        sources = {'k': {'url': 'https://x.example/a', 'title': '来源'}}
        out = rr.apply_link_patches(frag, 1, patches, sources)
        self.assertIn('<p>862.42<a class="ref"', out)
        self.assertIn('<script>var x="862.42";</script>', out)
        self.assertNotIn('<script>var x="862.42<a class="ref"', out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
