#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
七步财务分析法 —— 通用生成器 (SOP v2)
====================================
输入: 任意 A 股公司 资产负债表/利润表/现金流量表 CSV
      (东方财富/同花顺/Wind 导出的合并报表, N 年, 左新右旧)
输出: output.csv (主数据, 动态 N+3 列标准格式, N=年份数) + data_status.md (数据完整性说明)

严格遵循 references/SOP_七步财报分析指标公式.md 的硬约束:
  - 动态 N+3 列数据行 (N=年份数) / 7 步固定标题 / 平均算法 / 增长率边界 / 空值当 0
  - 取数防坑: 同名空行 / 小计行陷阱 (收集候选→跳空行→按 (合计)/减： 优先级→歧义报警)

用法:
  python build_metrics.py [资产负债表.csv] [利润表.csv] [现金流量表.csv] [输出目录]
  # 不带参数: 在「当前工作目录」按文件名模式自动匹配三张表, 输出到当前目录

不适用: 银行/保险/证券 (科目结构差异大)、母公司报表。
"""

import csv
import os
import re
import sys
import glob
import datetime

# =====================================================================
# 配置区 (按公司行业可调整, 详见 SOP §2.5 经营/金融资产负债划分)
# =====================================================================
# 金融资产 = 以下科目之和 (不直接参与主营、用于投资获利的资产)
FIN_ASSET_ITEMS = [
    "交易性金融资产", "长期股权投资", "其他权益工具投资",
    "投资性房地产", "应收股利",
]
# 金融负债 = 以下科目之和 (主要为融资目的的负债)
# 标准口径默认含 "应付债券" (纯融资性质公司债); 个别养殖业/重资产公司将应付债券
# 记为融资租赁性质时, 可把 "应付债券" 从此列表移除 (并同步调低 有息债务 判定)。
FIN_LIAB_ITEMS = [
    "短期借款", "交易性金融负债", "应付股利", "应付债券",
    "一年内到期的非流动负债", "租赁负债", "长期应付款", "递延收益",
]
# 经营性负债 (无息债务) = 以下科目之和 (占用上下游/经营相关的负债)
OP_LIAB_ITEMS = [
    "应付票据及应付账款", "预收款项", "合同负债",
    "应付职工薪酬", "应交税费", "其他应付款合计", "其他流动负债",
]


WARNINGS = []  # 取数歧义等警告


# ---------- 归一化 ----------
def normalize(name: str) -> str:
    name = name.replace('　', '').replace(' ', '').replace('\t', '')
    if name.startswith('其中：'):
        name = name[3:]
    return name.strip()


def load(path):
    with open(path, 'r', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    headers = [h.strip() for h in rows[0]]
    year_cols = {}
    for i, h in enumerate(headers):
        if h.endswith('年年报'):
            year_cols[h.replace('年年报', '')] = i
    data = {}
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        nm = normalize(row[0])
        if nm == '数据来源：妙想Choice':
            continue
        vals = {}
        for y, idx in year_cols.items():
            v = row[idx].strip() if idx < len(row) else ''
            try:
                vals[y] = float(v) if v else 0.0
            except ValueError:
                vals[y] = 0.0
        data[nm] = vals
    return data, sorted(year_cols.keys(), reverse=True)


# ---------- 取数 (防同名空行/小计行陷阱) ----------
# 科目别名表: 简称 -> 全称候选 (解决用户 CSV 写简称、引擎找全称的匹配失败)
ALIASES = {
    "归母净利润": ["归属于母公司股东的净利润", "归属于母公司所有者的净利润", "归属于母公司普通股股东的净利润"],
    "扣非净利润": ["扣除非经常性损益后的净利润", "扣除非经常性损益后归属于母公司股东的净利润"],
    "净利润": ["归属于母公司股东的净利润"],  # 仅作兜底, 优先级低于精确匹配
    "经营净现金流": ["经营活动产生的现金流量净额", "经营活动现金流量净额", "经营活动现金净流量"],
    "经营活动产生的现金流量净额": ["经营活动现金流量净额", "经营活动现金净流量", "经营净现金流"],
    "资本开支": ["购建固定资产、无形资产和其他长期资产支付的现金", "购建固定资产无形资产支付的现金", "资本性支出"],
    "营收增长率": ["营业收入增长率", "营业总收入增长率"],
    "归母净资产": ["归属于母公司股东权益合计", "归属于母公司所有者权益合计", "所有者权益(或股东权益)合计"],
    "股东权益合计": ["所有者权益合计", "所有者权益(或股东权益)合计", "股东权益"],
    "总资产": ["资产总计", "资产总额"],
    "总负债": ["负债合计", "负债总额"],
}

def prio(name: str) -> int:
    s = 0
    if '(合计)' in name:
        s += 100
    if '减：' in name:
        s += 50
    if name.startswith('其中：'):
        s -= 100
    if '总收入' in name:
        s -= 10
    return s


def get_series(data, kws):
    """在 data 中按关键词匹配科目, 返回 {year: value}。规避全空行与小计行。

    匹配优先级: 精确相等(3) > 别名命中(2) > 关键词在科目名中(正向,1) > 科目名在关键词中(反向,0.5)。
    别名命中: 若数据科目名 == 某别名, 或数据科目名包含某别名, 即按别名对应关键词命中
    (解决: 引擎关键词用全称「归属于母公司股东的净利润」, 用户 CSV 写简称「归母净利润」)。
    """
    # 预处理: 收集所有别名 -> 归属关键词 的映射 (含反查: 数据名是别名时能命中对应关键词)
    alias_to_kw = {}
    for kw, aliases in ALIASES.items():
        for a in aliases:
            alias_to_kw.setdefault(a, []).append(kw)

    cands = []
    for name, vals in data.items():
        best = 0
        for kw in kws:
            if name == kw or name.replace('(元)', '') == kw:
                best = max(best, 3)
            # 别名反查: 数据科目名是某关键词的别名 -> 命中该关键词
            elif name in alias_to_kw and kw in alias_to_kw[name]:
                best = max(best, 2)
            elif any(a in name for a in alias_to_kw.get(kw, [])):
                best = max(best, 2)
            elif kw in name:
                best = max(best, 1)
            elif name in kw:
                best = max(best, 0.5)
        if best:
            cands.append((name, vals, best))
    if not cands:
        return None
    non_empty = [c for c in cands if any(abs(v) > 1e-9 for v in c[1].values())]
    pool = non_empty if non_empty else cands
    pool.sort(key=lambda c: (prio(c[0]), c[2]), reverse=True)
    best = pool[0]
    top = [c for c in pool if prio(c[0]) == prio(best[0]) and c[2] == best[2]]
    if len(top) > 1:
        WARNINGS.append(f"取数歧义 {kws} -> 候选 {[c[0] for c in top]}，已取 {best[0]}")
    return best[1]


YEARS = None


def series_to_arr(series):
    return [series.get(y, 0.0) for y in YEARS]


def arr(data, kws):
    s = get_series(data, kws)
    if s is None:
        WARNINGS.append(f"未找到科目: {kws}")
        return [0.0] * len(YEARS)
    return series_to_arr(s)


def sum_items(data, items):
    """对多个科目分别取序列后按年求和 (用于金融/经营资产负债划分)。"""
    out = [0.0] * len(YEARS)
    for it in items:
        s = get_series(data, [it])
        if s is None:
            WARNINGS.append(f"未找到科目(划分用): {it}")
            continue
        for i, y in enumerate(YEARS):
            out[i] += s.get(y, 0.0)
    return out


# ---------- 计算辅助 ----------
def avg_arr(a):
    n = len(a)
    out = []
    for i in range(n):
        if i < n - 1:
            out.append((a[i] + a[i + 1]) / 2)
        else:
            out.append(a[i] / 2)
    return out


def growth_arr(a):
    n = len(a)
    out = []
    for i in range(n):
        if i < n - 1:
            d = a[i + 1]
            out.append((a[i] - d) / d if abs(d) > 1e-9 else '')
        else:
            out.append('除数为零。')
    return out


def div(a, b):
    return [x / y if abs(y) > 1e-9 else '' for x, y in zip(a, b)]


def safe_div(num, den):
    """除数保护除法。den 为数字(>1e-9)正常除；den 为缺失串(''/'除数为零。')或0 返回 ''。"""
    try:
        return num / den if abs(den) > 1e-9 else ''
    except TypeError:
        return ''


# ---------- 文件匹配 ----------
def find_default_files(base_dir):
    pats = {
        'bs': ['*资产负债表*.csv'],
        'is': ['*利润表*.csv'],
        'cf': ['*现金流量表*.csv', '*现金流*.csv'],
    }
    found = {}
    for key, gl in pats.items():
        for p in gl:
            hits = sorted(glob.glob(os.path.join(base_dir, p)))
            if hits:
                found[key] = hits[0]
                break
    return found.get('bs'), found.get('is'), found.get('cf')


def company_from_name(path):
    base = os.path.basename(path)
    base = re.sub(r'[（(].*?[)）]', '', base)          # 去括号内容
    for suf in ['资产负债表', '利润表', '现金流量表', '现金流']:
        base = base.replace(suf, '')
    base = base.replace('.csv', '').strip(' _-')
    return base or '未知公司'


# =====================================================================
# 主流程
# =====================================================================
def main():
    args = sys.argv[1:]
    if len(args) >= 3:
        bs_file, is_file, cf_file = args[0], args[1], args[2]
        out_dir = args[3] if len(args) >= 4 else os.path.dirname(os.path.abspath(bs_file))
    else:
        base_dir = os.getcwd()
        bs_file, is_file, cf_file = find_default_files(base_dir)
        out_dir = base_dir

    if not (bs_file and is_file and cf_file):
        sys.exit("❌ 找不到三张报表 CSV。请传入路径, 或在工作目录放置 "
                 "*资产负债表*.csv / *利润表*.csv / *现金流量表*.csv")

    for f in (bs_file, is_file, cf_file):
        if not os.path.exists(f):
            sys.exit(f"❌ 文件不存在: {f}")

    company = company_from_name(bs_file)
    os.makedirs(out_dir, exist_ok=True)
    out_csv = os.path.join(out_dir, 'output.csv')
    out_md = os.path.join(out_dir, 'data_status.md')

    global YEARS
    bs, yrs_bs = load(bs_file)
    ist, yrs_is = load(is_file)
    cf, yrs_cf = load(cf_file)
    if not (yrs_bs == yrs_is == yrs_cf):
        sys.exit(f"❌ 三张表年份范围不一致: 资产负债表={yrs_bs} 利润表={yrs_is} 现金流量表={yrs_cf}")
    YEARS = yrs_bs
    N = len(YEARS)

    # ---------- 抽取基础数据 ----------
    营业收入 = arr(ist, ["营业收入"])
    营业成本 = arr(ist, ["营业成本"])
    净利润 = arr(ist, ["净利润"])
    归母净利润 = arr(ist, ["归属于母公司股东的净利润"])
    扣非净利润 = arr(ist, ["扣除非经常性损益后的净利润"])
    投资收益 = arr(ist, ["投资收益"])
    公允价值变动 = arr(ist, ["公允价值变动"])
    利息收入 = arr(ist, ["减：利息收入", "利息收入"])  # 优先取"减：利息收入"真实值行
    研发费用 = arr(ist, ["研发费用"])
    管理费用 = arr(ist, ["管理费用"])
    销售费用 = arr(ist, ["销售费用"])
    财务费用 = arr(ist, ["财务费用"])

    OCF = arr(cf, ["经营活动产生的现金流量净额", "经营活动净现金流", "OCF"])
    CAPEX = arr(cf, ["购建固定资产"])

    # 资产负债
    货币资金 = arr(bs, ["货币资金"])
    存货 = arr(bs, ["存货"])
    应收账款 = arr(bs, ["应收账款"])
    应收票据 = arr(bs, ["应收票据"])
    预付款项 = arr(bs, ["预付款项", "预付账款"])
    应付账款 = arr(bs, ["应付账款"])
    应付票据 = arr(bs, ["应付票据"])
    预收款项 = arr(bs, ["预收款项", "预收账款"])
    合同负债 = arr(bs, ["合同负债"])
    应付职工薪酬 = arr(bs, ["应付职工薪酬"])
    应交税费 = arr(bs, ["应交税费"])
    其他应付款合计 = arr(bs, ["其他应付款合计"])
    其他流动负债 = arr(bs, ["其他流动负债"])
    应付票据及应付账款 = arr(bs, ["应付票据及应付账款"])

    短期借款 = arr(bs, ["短期借款"])
    长期借款 = arr(bs, ["长期借款"])
    应付债券 = arr(bs, ["应付债券"])
    长期应付款 = arr(bs, ["长期应付款"])
    交易性金融负债 = arr(bs, ["交易性金融负债"])
    应付股利 = arr(bs, ["应付股利"])
    一年内到期非流动负债 = arr(bs, ["一年内到期的非流动负债"])
    租赁负债 = arr(bs, ["租赁负债"])
    递延收益 = arr(bs, ["递延收益"])

    交易性金融资产 = arr(bs, ["交易性金融资产"])
    长期股权投资 = arr(bs, ["长期股权投资"])
    其他权益工具投资 = arr(bs, ["其他权益工具投资"])
    投资性房地产 = arr(bs, ["投资性房地产"])
    应收股利 = arr(bs, ["应收股利"])
    可供出售金融资产 = arr(bs, ["可供出售金融资产"])

    固定资产 = arr(bs, ["固定资产"])
    在建工程 = arr(bs, ["在建工程"])
    无形资产 = arr(bs, ["无形资产"])
    使用权资产 = arr(bs, ["使用权资产"])
    商誉 = arr(bs, ["商誉"])
    长期待摊费用 = arr(bs, ["长期待摊费用"])

    流动资产合计 = arr(bs, ["流动资产合计"])
    非流动资产合计 = arr(bs, ["非流动资产合计"])
    资产总计 = arr(bs, ["资产总计"])
    负债合计 = arr(bs, ["负债合计"])
    归母净资产 = arr(bs, ["归属于母公司股东权益合计"])
    股东权益合计 = arr(bs, ["股东权益合计"])

    # ---------- 派生: 第一步 ----------
    金融利润 = [a + b + c for a, b, c in zip(投资收益, 公允价值变动, 利息收入)]
    经营利润 = [a - b for a, b in zip(归母净利润, 金融利润)]
    净利润率 = div(净利润, 营业收入)
    自由现金流 = [a - b for a, b in zip(OCF, CAPEX)]
    扣非净利润率 = div(扣非净利润, 净利润)
    经营现金流比率 = div(OCF, 归母净利润)
    经营利润占比 = div(经营利润, 归母净利润)

    # ---------- 派生: 第二步 ----------
    毛利率 = [(r - c) / r if abs(r) > 1e-9 else '' for r, c in zip(营业收入, 营业成本)]
    净利率 = div(净利润, 营业收入)
    研发费用率 = div(研发费用, 营业收入)
    管理费用率 = div(管理费用, 营业收入)
    销售费用率 = div(销售费用, 营业收入)
    财务费用率 = div(财务费用, 营业收入)
    毛利减净利 = [(g - n) if isinstance(g, float) and isinstance(n, float) else '' for g, n in zip(毛利率, 净利率)]

    # ---------- 派生: 第三步 ----------
    营收增长率 = growth_arr(营业收入)
    归母增长率 = growth_arr(归母净利润)
    扣非增长率 = growth_arr(扣非净利润)

    # ---------- 派生: 第五步 ----------
    无息债务 = sum_items(bs, OP_LIAB_ITEMS)
    有息债务 = [a + b + c + d for a, b, c, d in zip(短期借款, 长期借款, 应付债券, 长期应付款)]
    资产负债率 = div(负债合计, 资产总计)

    金融资产 = sum_items(bs, FIN_ASSET_ITEMS)
    可供出售 = 可供出售金融资产  # 0 或空(多数公司无此科目)
    经营资产 = [ta - fa - av for ta, fa, av in zip(资产总计, 金融资产, 可供出售)]
    净营运资产 = [a - b for a, b in zip(经营资产, 无息债务)]
    金融负债 = sum_items(bs, FIN_LIAB_ITEMS)
    净金融资产 = [a - b for a, b in zip(金融资产, 金融负债)]
    净经营资产收益率 = div(经营利润, 净营运资产)

    # ---------- 派生: 第六步 ----------
    应收 = [a + b for a, b in zip(应收账款, 应收票据)]
    应付 = [a + b for a, b in zip(应付账款, 应付票据)]
    WC期末 = [a + b + c + d - e - f - g - h for a, b, c, d, e, f, g, h in zip(
        应收账款, 应收票据, 预付款项, 存货, 应付账款, 应付票据, 预收款项, 合同负债)]
    WC期初 = [WC期末[i + 1] if i < N - 1 else 0.0 for i in range(N)]
    ΔWC = [a - b for a, b in zip(WC期末, WC期初)]
    每元收入WC = div(WC期末, 营业收入)
    应收占收 = div(应收, 营业收入)
    预付占收 = div(预付款项, 营业收入)
    存货占收 = div(存货, 营业收入)
    应付占收 = div(应付, 营业收入)
    预收占收 = div(预收款项, 营业收入)
    合同负债占收 = div(合同负债, 营业收入)
    固定资产合计 = [a + b for a, b in zip(固定资产, 在建工程)]
    长期资产合计 = [a + b + c + d + e for a, b, c, d, e in zip(固定资产, 无形资产, 使用权资产, 商誉, 长期待摊费用)]
    每元收入固定资产 = div(固定资产合计, 营业收入)
    每元收入长期资产 = div(长期资产合计, 营业收入)

    # ---------- 派生: 第七步 ----------
    平均总资产 = avg_arr(资产总计)
    平均流动资产 = avg_arr(流动资产合计)
    平均固定资产 = avg_arr(固定资产)
    平均存货 = avg_arr(存货)
    平均WC = avg_arr(WC期末)
    平均应收 = avg_arr(应收)
    平均归母净资产 = avg_arr(归母净资产)
    平均股东权益合计 = avg_arr(股东权益合计)

    ROA = div(净利润, 平均总资产)
    ROIC = [safe_div(n, e + d) for n, e, d in zip(净利润, 股东权益合计, 有息债务)]
    ROE = div(净利润, 平均股东权益合计)
    销售净利率 = div(净利润, 营业收入)
    总资产周转率 = div(营业收入, 平均总资产)
    权益乘数 = div(平均总资产, 平均股东权益合计)

    总资产周转天数 = [safe_div(365, t) for t in 总资产周转率]
    流动资产周转天数 = [safe_div(365 * ac, rev) for ac, rev in zip(平均流动资产, 营业收入)]
    WC周转天数 = [safe_div(365 * wc, rev) for wc, rev in zip(平均WC, 营业收入)]
    应收周转天数 = [safe_div(365 * ar, rev) for ar, rev in zip(平均应收, 营业收入)]
    存货周转天数 = [safe_div(365 * inv, rev) for inv, rev in zip(平均存货, 营业收入)]
    固定资产周转天数 = [safe_div(365 * fa, rev) for fa, rev in zip(平均固定资产, 营业收入)]

    # ---------- 写出 CSV ----------
    def fmt(v):
        if isinstance(v, str):
            return v
        if isinstance(v, float):
            return repr(round(v, 6))
        return str(v)

    def row_title(title):
        return ['title', title]

    def row_data(name, a):
        return ['data', [name] + [fmt(v) for v in a]]

    rows_out = []
    header = [''] + [f"{y}年年报" for y in YEARS] + ['', '', '']
    rows_out.append(['header', header])

    # 第一步
    rows_out.append(row_title('第一步：看营收数据 (建立基本面轮廓，评估盈利质量)'))
    rows_out.append(row_data('营业收入', 营业收入))
    rows_out.append(row_data('归母净利润', 归母净利润))
    rows_out.append(row_data('净利润率', 净利润率))
    rows_out.append(row_data('扣非净利润', 扣非净利润))
    rows_out.append(row_data('经营活动净现金流', OCF))
    rows_out.append(row_data('自由现金流FCF', 自由现金流))
    rows_out.append(row_data('资本开支CAPEX', CAPEX))
    rows_out.append(row_data('扣非净利润/净利润', 扣非净利润率))
    rows_out.append(row_data('经营净现金流/归母净利润', 经营现金流比率))
    rows_out.append(row_data('金融利润', 金融利润))
    rows_out.append(row_data('经营利润', 经营利润))
    rows_out.append(row_data('经营利润/归母净利润', 经营利润占比))

    # 第二步
    rows_out.append(row_title('第二步：看成本费用构成 (理解盈利结构，识别效率变化)'))
    rows_out.append(row_data('毛利率', 毛利率))
    rows_out.append(row_data('净利率', 净利率))
    rows_out.append(row_data('研发费用', 研发费用))
    rows_out.append(row_data('管理费用', 管理费用))
    rows_out.append(row_data('销售费用', 销售费用))
    rows_out.append(row_data('财务费用', 财务费用))
    rows_out.append(row_data('研发费用率', 研发费用率))
    rows_out.append(row_data('管理费用率', 管理费用率))
    rows_out.append(row_data('销售费用率', 销售费用率))
    rows_out.append(row_data('财务费用率', 财务费用率))
    rows_out.append(row_data('毛利率-净利率', 毛利减净利))

    # 第三步
    rows_out.append(row_title('第三步：看增长 (把握核心趋势，评估未来潜力)'))
    rows_out.append(row_data('营收增长率', 营收增长率))
    rows_out.append(row_data('归母净利润增长率', 归母增长率))
    rows_out.append(row_data('扣非净利润增长率', 扣非增长率))

    # 第四步: 未提供分业务数据 -> 整段跳过 (用户提供独立分业务 CSV 后再补)

    # 第五步
    rows_out.append(row_title('第五步：看资产负债 (评估资产效率和财务风险)'))
    rows_out.append(row_data('流动资产', 流动资产合计))
    rows_out.append(row_data('货币资金', 货币资金))
    rows_out.append(row_data('存货', 存货))
    rows_out.append(row_data('非流动资产', 非流动资产合计))
    rows_out.append(row_data('总资产', 资产总计))
    rows_out.append(row_data('归母净资产', 归母净资产))
    rows_out.append(row_data('无息债务', 无息债务))
    rows_out.append(row_data('有息债务', 有息债务))
    rows_out.append(row_data('资产负债率', 资产负债率))
    rows_out.append(row_data('经营资产', 经营资产))
    rows_out.append(row_data('经营性负债', 无息债务))
    rows_out.append(row_data('净营运资产', 净营运资产))
    rows_out.append(row_data('金融资产', 金融资产))
    rows_out.append(row_data('金融负债', 金融负债))
    rows_out.append(row_data('净金融资产', 净金融资产))
    rows_out.append(row_data('净经营资产收益率', 净经营资产收益率))

    # 第六步
    rows_out.append(row_title('第六步：看投入产出 (核心视角，理解商业模式本质)'))
    wc_formula = ("营运资本-期末\n"
                  "WC = (应收账款+应收票据+预付账款+存货)-(应付账款+应付票据+预收款项+合同负债)")
    rows_out.append(['data', [wc_formula] + [fmt(v) for v in WC期末]])
    rows_out.append(row_data('营运资本-期初', WC期初))
    rows_out.append(row_data('ΔWC', ΔWC))
    rows_out.append(row_data('1元收入需要的WC', 每元收入WC))
    rows_out.append(row_data('应收账款占收入比', 应收占收))
    rows_out.append(row_data('预付款项占收入比', 预付占收))
    rows_out.append(row_data('存货占收入比', 存货占收))
    rows_out.append(row_data('应付账款占收入比', 应付占收))
    rows_out.append(row_data('预收款项占收入比', 预收占收))
    rows_out.append(row_data('合同负债占收入比', 合同负债占收))
    rows_out.append(row_data('固定资产合计', 固定资产合计))
    rows_out.append(row_data('长期资产合计', 长期资产合计))
    rows_out.append(row_data('1元收入需要的固定资产', 每元收入固定资产))
    rows_out.append(row_data('1元收入需要的长期资产', 每元收入长期资产))

    # 第七步
    rows_out.append(row_title('第七步：看收益率 (综合评估股东回报和资产效率)'))
    rows_out.append(row_data('总资产', 资产总计))
    rows_out.append(row_data('平均总资产', 平均总资产))
    rows_out.append(row_data('流动资产', 流动资产合计))
    rows_out.append(row_data('平均流动资产', 平均流动资产))
    rows_out.append(row_data('固定资产', 固定资产))
    rows_out.append(row_data('平均固定资产', 平均固定资产))
    rows_out.append(row_data('存货', 存货))
    rows_out.append(row_data('平均存货', 平均存货))
    rows_out.append(row_data('营运资本', WC期末))
    rows_out.append(row_data('平均营运资本', 平均WC))
    rows_out.append(row_data('应收', 应收))
    rows_out.append(row_data('平均应收', 平均应收))
    rows_out.append(row_data('归母净资产', 归母净资产))
    rows_out.append(row_data('平均归母净资产', 平均归母净资产))
    rows_out.append(row_data('股东权益合计', 股东权益合计))
    rows_out.append(row_data('平均股东权益合计', 平均股东权益合计))
    rows_out.append(row_data('ROA', ROA))
    rows_out.append(row_data('ROIC', ROIC))
    rows_out.append(row_data('ROE', ROE))
    rows_out.append(row_data('销售净利率', 销售净利率))
    rows_out.append(row_data('总资产周转率', 总资产周转率))
    rows_out.append(row_data('权益乘数', 权益乘数))
    rows_out.append(row_data('总资产周转天数', 总资产周转天数))
    rows_out.append(row_data('流动资产周转天数', 流动资产周转天数))
    rows_out.append(row_data('WC周转天数', WC周转天数))
    rows_out.append(row_data('应收账款周转天数', 应收周转天数))
    rows_out.append(row_data('存货周转天数', 存货周转天数))
    rows_out.append(row_data('固定资产周转天数', 固定资产周转天数))

    with open(out_csv, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        for rtype, content in rows_out:
            if rtype == 'header':
                w.writerow(content)
            elif rtype == 'title':
                w.writerow([content] + [''] * (N + 2))
            elif rtype == 'data':
                name = content[0]
                vals = content[1:]
                w.writerow([name] + vals + ['', ''])

    # ---------- 校验 ----------
    def approx(a, b, tol=0.01):
        return abs(a - b) <= max(abs(a), abs(b)) * tol + 1.0

    checks = []
    for i, y in enumerate(YEARS):
        资产 = 资产总计[i]
        负债 = 负债合计[i]
        权益 = 股东权益合计[i]
        ok = approx(资产, 负债 + 权益)
        checks.append((y, '资产平衡', f"{资产:.2f} = {负债:.2f} + {权益:.2f}", '✅' if ok else '❌'))

    增长边界_ok = (营收增长率[-1] == '除数为零。' and 归母增长率[-1] == '除数为零。' and 扣非增长率[-1] == '除数为零。')

    # ---------- data_status.md ----------
    today = datetime.date.today().isoformat()
    md = []
    md.append("# 数据完整性说明\n")
    md.append(f"生成时间：{today}")
    md.append("对应 CSV：output.csv")
    md.append(f"公司：{company}")
    md.append(f"源数据范围：{YEARS[-1]}-{YEARS[0]} 年报\n")
    md.append("---\n")
    md.append("## ✅ 已完整生成（基于源 CSV 自动计算）\n")
    md.append("| 步骤 | 内容 | 数据来源 |")
    md.append("|---|---|---|")
    md.append("| 第一步 | 营业收入、归母净利润、净利润率、扣非净利润、OCF、FCF、CAPEX、扣非/净利润、经营现金流/归母、金融/经营利润及派生比率（13 项） | 利润表、现金流量表 |")
    md.append("| 第二步 | 毛利率、净利率、4 项费用及费用率、毛利-净利（11 项） | 利润表 |")
    md.append("| 第三步 | 营收/归母/扣非 同比增长率（3 项） | 第一步派生 |")
    md.append("| 第五步 | 资产负债基础项（9 项）+ 经营/金融资产负债划分（7 项） | 资产负债表 |")
    md.append("| 第六步 | 营运资本、各项占收入比、固定资产/长期资产周转（14 项） | 资产负债表 + 利润表 |")
    md.append("| 第七步 | ROA/ROIC/ROE、各项平均与周转率/天数（23 项） | 全表派生 |\n")
    md.append("---\n")
    md.append("## ⚠️ 部分缺失（依赖外部数据）\n")
    md.append("| 项目 | 数据来源 | 如何补充 |")
    md.append("|---|---|---|")
    md.append("| 第一步：营业收入预测（未来 3 年） | 券商一致预期/业绩预告 | 用户提供预测值后填入对应列 |")
    md.append("| 第一步：归母净利润预测（未来 3 年） | 同上 | 同上 |")
    md.append("| 第三步：券商预测增长率 | 由第一步预测值计算 | 提供预测值即可 |\n")
    md.append("---\n")
    md.append("## ❌ 整段缺失（数据未提供）\n")
    md.append("| 步骤 | 内容 | 数据来源 | 如何补充 |")
    md.append("|---|---|---|---|")
    md.append("| 第四步 | 业务构成（分行业/分产品收入、占比、毛利率） | 年报\"主营业务分行业/分产品\"章节 | 用户提供独立分业务 CSV 后按实际业务名生成 |")
    md.append("| 第六步 | 员工总人数及分工种（生产/销售/财务/技术/研发/行政） | 年报\"员工情况\" | 用户提供员工总数即可 |")
    md.append("| 第六步 | 人均指标（人均收入/利润/扣非利润/薪酬/固定资产） | 由员工数据派生 | 员工数据补全后自动计算 |\n")
    md.append("---\n")
    md.append("## ⚠️ 校验异常\n")
    md.append("| 校验项 | 期望 | 实际 | 状态 |")
    md.append("|---|---|---|---|")
    for y, name, actual, st in checks:
        md.append(f"| 资产平衡({y}) | 总资产 = 负债 + 权益 | {actual} | {st} |")
    md.append(f"| 增长率边界 | 最右列 = `除数为零。` | {'✅ 通过' if 增长边界_ok else '❌ 失败'} | {'✅' if 增长边界_ok else '❌'} |")
    md.append(f"| 营收一致（第四步） | 第四步合计 ≈ 营业收入 | 跳过（无第四步） | — |\n")
    md.append("---\n")
    md.append("## 数据精度说明\n")
    md.append("- 金额单位：保持源表原始单位（元）")
    md.append("- 比率：保留为小数（0.xxxx），不转百分比")
    md.append("- 平均算法：`(本年期末 + 上年期末) / 2`；最旧年用 `本年期末 / 2`")
    md.append("- 增长率除数为零：写 `除数为零。`")
    md.append("- 空值处理：源 CSV 空 → 当作 0\n")
    md.append("---\n")
    md.append("## 金融资产负债划分（本次实际采用的科目）\n")
    md.append(f"**金融资产**：{', '.join(FIN_ASSET_ITEMS)}")
    md.append(f"**金融负债**：{', '.join(FIN_LIAB_ITEMS)}（默认含应付债券；养殖业等记为融资租赁性质时可移除）")
    md.append(f"**经营性负债（无息债务）**：{', '.join(OP_LIAB_ITEMS)}")
    md.append("**经营资产**：`总资产 - 金融资产 - 可供出售金融资产`（应收股利已计入金融资产，不再单独加回）\n")
    if WARNINGS:
        md.append("---\n")
        md.append("## ⚠️ 取数警告\n")
        for wmsg in WARNINGS:
            md.append(f"- {wmsg}")

    with open(out_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md) + '\n')

    print("生成完成。")
    print(f"公司: {company}")
    print(f"年份范围: {YEARS[-1]} -> {YEARS[0]} (N={N})")
    print(f"输出: {out_csv}")
    print(f"取数警告数: {len(WARNINGS)}")
    for wmsg in WARNINGS:
        print("  -", wmsg)
    print(f"资产平衡校验: {sum(1 for c in checks if c[3]=='✅')}/{len(checks)} 通过")
    print(f"增长率边界: {'通过' if 增长边界_ok else '失败'}")
    print(f"output.csv 行数: {len(rows_out)}")


if __name__ == '__main__':
    main()
