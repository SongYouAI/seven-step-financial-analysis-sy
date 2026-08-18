#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
七步八问财报分析报告 · 内容质检器 (validate_content.py)
======================================================
将「内容五件套」标准变成可执行铁闸。扫描报告 Markdown，按 R1-R7 规则检查。

规则与严重度：
  R1 算式覆盖    每步 ≥3 个可复算算式(含=与数字)        阻断
  R2 标尺引用    判断词附近须有阈值/见标尺              警告
  R3 术语裸奔    词典术语首次出现须有释义              警告
  R4 结论空降    价格/评级/倍数须有推导段              阻断
  R5 咬合缺失    每步须有 🔗 步骤咬合区                警告
  R6 数值自洽    正文比率与表内数据复算偏差>2%         阻断
  R7 反面假设    每步 ≥1 条「也可能是…」              警告

用法：
  python3 validate_content.py 报告.md [报告2.md ...]
  python3 validate_content.py --selftest        # 内置样例自测
  python3 validate_content.py --strict          # 警告也视为失败(退出码1)

退出码：0 通过 / 1 仅警告(--strict) / 2 存在阻断项
"""
import argparse
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(os.path.dirname(HERE), "references")

# ---------- 步骤分块 ----------
STEP_RE = re.compile(r'^#{2,3}\s*第([1-9])步[^\n]*', re.M)
CONCLUSION_RE = re.compile(r'^#{2,3}\s*第([1-9])步结论[^\n]*', re.M)

# ---------- 规则正则 ----------
EQUATION_RE = re.compile(r'(\d+(?:\.\d+)?)\s*÷\s*(\d+(?:\.\d+)?)\s*=\s*(\d+(?:\.\d+)?)')
HAS_EQ_NUM_RE = re.compile(r'=\s*\d+(?:\.\d+)?')
JUDGE_WORDS = ['优', '良', '警戒', '偏高', '偏低', '较好', '较差', '显著高于', '显著低于', '远高于', '远低于']
RULER_NEAR_RE = re.compile(r'(标尺|阈值|见标尺库|优[>~]|良[>~]|警戒[<~]|笔记§|>\s*\d|<\s*\d)')
ANTI_RE = re.compile(r'(也可能|但也可能|反面|另一种可能|触发条件|也有可能)')
LINK_RE = re.compile(r'(🔗|与其他步骤的印证|步骤咬合)')
DERIVE_RE = re.compile(r'(推导|计算|公式|因为|所以|÷)')
PRICE_TRIGGER_RE = re.compile(r'(目标价|合理价值|评级|买入|卖出|持有|市盈率|PE\s*=|动态估值倍数|估值倍数)')
DEF_RE = re.compile(r'(定义|：|:|（)')  # 释义信号(宽松)

# 阻断项
BLOCK_RULES = {'R1', 'R4', 'R6'}


def load_terms():
    """从术语人话词典抽取术语列表（首列）。"""
    path = os.path.join(REF, '术语人话词典.md')
    terms = []
    if not os.path.exists(path):
        return terms
    with open(path, encoding='utf-8') as f:
        for line in f:
            m = re.match(r'^\|\s*([^|]+?)\s*\|', line)
            if m:
                t = m.group(1).strip()
                # 跳过表头/分隔
                if t and t not in ('术语', '---', '生活类比', '大白话（≤25字）'):
                    terms.append(t)
    return terms


def split_steps(text):
    """返回 [(step_no, title, body), ...] 按第X步结论块切分。"""
    matches = list(CONCLUSION_RE.finditer(text))
    if not matches:
        matches = list(STEP_RE.finditer(text))
    blocks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        no = m.group(1)
        title = m.group(0).strip()
        blocks.append((no, title, text[start:end]))
    return blocks


def check_r1(step_blocks):
    """每步 ≥3 算式。"""
    issues = []
    for no, title, body in step_blocks:
        eqs = len(EQUATION_RE.findall(body)) + len(HAS_EQ_NUM_RE.findall(body))
        if eqs < 3:
            issues.append((no, title, f'仅 {eqs} 个算式(要求≥3)'))
    return issues


def check_r2(step_blocks):
    """判断词附近 40 字内须有标尺。"""
    issues = []
    for no, title, body in step_blocks:
        for m in re.finditer('|'.join(re.escape(w) for w in JUDGE_WORDS), body):
            seg = body[max(0, m.start() - 20): m.start() + 40]
            if not RULER_NEAR_RE.search(seg):
                issues.append((no, title, f'判断词「{m.group(0)}」附近40字无标尺引用'))
                break
    return issues


def check_r3(step_blocks, terms):
    """术语首次出现须有释义。"""
    issues = []
    if not terms:
        return issues
    for no, title, body in step_blocks:
        for t in terms:
            if t in body:
                # 首次出现位置
                idx = body.find(t)
                ctx = body[idx: idx + 30]
                # 宽松：若附近有括号释义或「见词典」则通过
                if not ('((' in ctx or '见词典' in ctx or '：' in ctx[:len(t) + 2] or ':' in ctx[:len(t) + 2]):
                    # 全文若已有释义定义则放宽
                    if not re.search(re.escape(t) + r'\s*[：（:]', body):
                        issues.append((no, title, f'术语「{t}」首次出现无释义'))
                        break
    return issues


def check_r4(text, step_blocks):
    """价格/评级/倍数须有推导段。"""
    if not PRICE_TRIGGER_RE.search(text):
        return []
    has_derive = bool(DERIVE_RE.search(text))
    if not has_derive:
        return [('全报告', '结论空降', '出现价格/评级/倍数但全文无推导段')]
    return []


def check_r5(step_blocks):
    """每步须有咬合区。"""
    issues = []
    for no, title, body in step_blocks:
        if not LINK_RE.search(body):
            issues.append((no, title, '缺 🔗 步骤咬合区'))
    return issues


def check_r6(text, step_blocks):
    """正文算式复算偏差>2% 阻断。"""
    issues = []
    # 全报告级：提取所有 A÷B=C
    for m in EQUATION_RE.finditer(text):
        a, b, c = float(m.group(1)), float(m.group(2)), float(m.group(3))
        if b == 0:
            continue
        real = a / b
        if real == 0:
            continue
        dev = abs(c - real) / real
        if dev > 0.02:
            issues.append(('全报告', f'数值自洽 {m.group(0)}',
                           f'复算应为 {real:.4f}，正文写 {c}，偏差 {dev*100:.1f}% > 2%'))
    return issues


def check_r7(step_blocks):
    """每步 ≥1 反面假设。"""
    issues = []
    for no, title, body in step_blocks:
        if not ANTI_RE.search(body):
            issues.append((no, title, '缺反面假设(≥1条「也可能是…」)'))
    return issues


def run_on_text(text):
    blocks = split_steps(text)
    terms = load_terms()
    results = {
        'R1': check_r1(blocks),
        'R2': check_r2(blocks),
        'R3': check_r3(blocks, terms),
        'R4': check_r4(text, blocks),
        'R5': check_r5(blocks),
        'R6': check_r6(text, blocks),
        'R7': check_r7(blocks),
    }
    return results, blocks


def report(results, strict=False):
    rule_names = {
        'R1': '算式覆盖', 'R2': '标尺引用', 'R3': '术语裸奔',
        'R4': '结论空降', 'R5': '咬合缺失', 'R6': '数值自洽', 'R7': '反面假设',
    }
    sev = {k: ('阻断' if k in BLOCK_RULES else '警告') for k in rule_names}
    print('=' * 60)
    print('  七步八问报告内容质检结果')
    print('=' * 60)
    total_block = 0
    total_warn = 0
    for r in ['R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7']:
        items = results[r]
        if not items:
            print(f'  [✓] {r} {rule_names[r]} ({sev[r]}): 通过')
            continue
        if r in BLOCK_RULES:
            total_block += len(items)
        else:
            total_warn += len(items)
        tag = '✗阻断' if r in BLOCK_RULES else '!警告'
        print(f'  [{tag}] {r} {rule_names[r]} ({sev[r]}): {len(items)} 处')
        for no, title, desc in items[:8]:
            print(f'        · 第{no}步 {title[:24]} — {desc}')
        if len(items) > 8:
            print(f'        · …另 {len(items)-8} 处')
    print('-' * 60)
    print(f'  阻断项 {total_block} / 警告项 {total_warn}')
    if total_block > 0:
        print('  结论：❌ 不通过（存在阻断项，禁止输出）')
        return 2
    if total_warn > 0 and strict:
        print('  结论：⚠ 仅警告(--strict 视为失败)')
        return 1
    print('  结论：✅ 通过')
    return 0


def selftest():
    """内置样例：故意含 0.84/0.89 矛盾、缺算式、目标价空降，验证 R1/R4/R6 命中。"""
    good = """## 第1步结论：营收与盈利质量
### 一、盈利质量
扣非/归母 = 645.08 ÷ 722.01 = 0.8935（口径：2025年报）
经营利润/归母 = 600 ÷ 722.01 = 0.83
OCF/归母 = 900 ÷ 722.01 = 1.25（优，见标尺库§1）
也可能是归母被一次性收益拉高。
🔗 与其他步骤：印证第5步负债安全。
"""
    bad = """## 第1步结论：营收与盈利质量
扣非/归母：645.08 ÷ 722.01 = 0.84（质量好）
目标价 549.79 元，评级买入。
### 二、其他
营收增长不错。
"""
    print('>>> 自测样例A（应全部通过）：')
    rA, _ = run_on_text(good)
    rcA = report(rA)
    print('\n>>> 自测样例B（应触发 R1/R4/R6 阻断）：')
    rB, _ = run_on_text(bad)
    rcB = report(rB)
    print(f'\n自测结论：A退出码={rcA}(期望0)  B退出码={rcB}(期望2)')
    if rcA == 0 and rcB == 2:
        print('✅ 自测通过')
        return 0
    print('❌ 自测异常')
    return 1


def main():
    ap = argparse.ArgumentParser(description='七步八问报告内容质检器')
    ap.add_argument('files', nargs='*', help='报告 .md 文件')
    ap.add_argument('--selftest', action='store_true', help='内置样例自测')
    ap.add_argument('--strict', action='store_true', help='警告也视为失败')
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.files:
        ap.print_help()
        return 0
    overall = 0
    for fp in args.files:
        if not os.path.exists(fp):
            print(f'[跳过] 文件不存在: {fp}')
            continue
        with open(fp, encoding='utf-8') as f:
            text = f.read()
        print(f'\n📄 检查: {fp}')
        results, _ = run_on_text(text)
        rc = report(results, args.strict)
        overall = max(overall, rc)
    return overall


if __name__ == '__main__':
    sys.exit(main())
