#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块0.5：在线拉数适配层 (七步财报分析 · 港股/美股)
=========================================================
把 global-stock-data 的东财 datacenter 港/美三表接口，转换成
build_metrics.py 能吃的标准宽表 CSV（科目, YYYY年年报, ... 左新右旧）。

设计:
- 零第三方 Python 依赖（仅标准库 + 系统 curl，curl 自动走环境 HTTP(S)_PROXY）
- 仅拉年报期 (REPORT_TYPE="年报")，避开季报/中报噪声
- 币种按东财 CURRENCY 字段原样保留，写入 _meta.json 供报告标注
- 不改动 build_metrics.py / convert_input.py 核心（零回归）
- 美股财年在 9 月末结束（如 AAPL 2025-09-27），列标签取 fiscal year "2025年年报"

数据源归属: 东财 datacenter (global-stock-data by Simon 林, Apache-2.0)
整合进七步财报分析 skill (松幽, MIT) — 仅作在线拉数调用，保留上游 attribution。

用法:
  python3 build_online_puller.py <secucode> [--out <目录>]
    secucode: 00700.HK (港股) / AAPL.O (NASDAQ) / BABA.N (NYSE)
    输出: 默认 <cwd>/01_中间产物_CSV输入/{资产负债表,利润表,现金流量表}.csv + _meta.json
          （对齐七步分析 00→01→02 布局；--out 可覆盖）
    后续: build_metrics.py 01_中间产物_CSV输入/资产负债表.csv ... → output.csv
"""
import sys
import os
import json
import time
import subprocess
import urllib.parse

DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 报表名映射 (balance/income/cashflow × hk/us)
REPORT_MAP = {
    "balance":  {"hk": "RPT_HKF10_FN_BALANCE",  "us": "RPT_USF10_FN_BALANCE"},
    "income":   {"hk": "RPT_HKF10_FN_INCOME",   "us": "RPT_USF10_FN_INCOME"},
    "cashflow": {"hk": "RPT_HKSK_FN_CASHFLOW",  "us": "RPT_USSK_FN_CASHFLOW"},
}
OUT_NAME = {"balance": "资产负债表", "income": "利润表", "cashflow": "现金流量表"}

# 跨准则科目名映射 (港股IFRS / 美股US GAAP → A股中国企业准则 build_metrics 期望名)
# 仅做精确改名, 避免模糊匹配歧义 (如"其他营业收入"不映射, 以免被"营业收入"误命中)。
# 港股映射基于腾讯00700实测; 美股映射基于苹果AAPL实测补充。
HK_ITEM_MAP = {
    "营业额": "营业收入",
    "毛利": "毛利",
    "股东应占溢利": "归母净利润",
    "经营溢利": "营业利润",
    "除税前溢利": "利润总额",
    "除税后溢利": "净利润",
    "行政开支": "管理费用",
    "销售及分销费用": "销售费用",
    "融资成本": "财务费用",
    "利息收入": "利息收入",
    "少数股东损益": "少数股东损益",
    "股东权益": "归属于母公司股东权益合计",
    "总权益": "股东权益合计",
    "少数股东权益": "少数股东权益",
    "保留溢利(累计亏损)": "未分配利润",
    "股本溢价": "资本公积",
    "联营公司权益": "长期股权投资",
    "合营公司权益": "长期股权投资",
    # 异体字 / IFRS 口径差异（关键：不补就会静默取 0，报告写成"腾讯无应收账款"）
    "应收帐款": "应收账款",            # 港股用"帐"(巾) 非"账"(贝)，引擎按"账"搜 → 必 0
    "物业厂房及设备": "固定资产",        # IFRS: Property, plant and equipment
    "现金及等价物": "货币资金",
    "现金及现金等价物": "货币资金",
    "长期贷款": "长期借款",
    "递延收入(流动)": "合同负债",        # IFRS deferred revenue ≈ 合同负债
    "递延收入(非流动)": "递延收益",
    "贸易应收款项": "应收账款",
    "贸易及其他应收款项": "应收账款",
    "应付帐款": "应付账款",              # 同为"帐/账"异体字
    "应付税项": "应交税费",
    "应收税项": "其他应收款",
    # 港股现金流量表 IFRS 科目（东财港股直接返回 IFRS 英文直译名，非 A 股"经营活动产生的现金流量净额"写法）
    "经营业务现金净额": "经营活动产生的现金流量净额",
    "投资业务现金净额": "投资活动产生的现金流量净额",
    "融资业务现金净额": "筹资活动产生的现金流量净额",
}
US_ITEM_MAP = {
    "营销费用": "销售费用",
    "营业费用": "管理费用",
    "持续经营税前利润": "利润总额",
    # 美股归母口径：优先映射到 build_metrics 的"归母净利润"标准名，
    # 否则会落到"净利润"(含少数股东) 甚至被"归属于优先股净利润及其他项"抢跑(阿里实测算出 -23 亿)
    "归属于母公司股东净利润": "归母净利润",
    "归属于母公司股东的净利润": "归母净利润",
    "归属母公司股东净利润": "归母净利润",
    # 同理补美股口径差异（美股中文科目由东财翻译，部分与 A 股写法不同）
    "物业、厂房及设备": "固定资产",
    "物业厂房及设备": "固定资产",
    "现金及现金等价物": "货币资金",
    "现金及等价物": "货币资金",
    "递延收入(流动)": "合同负债",        # GAAP deferred revenue
    "递延收入(非流动)": "递延收益",
}
ITEM_MAP = {"hk": HK_ITEM_MAP, "us": US_ITEM_MAP}

# 消歧：港/美报表的「衍生小计行」以核心科目名开头（如"总资产减流动负债"以"总资产"开头，
# "总权益及非流动负债"），会被 build_metrics 的 contains 模糊匹配优先命中，导致核心科目取到
# 小计值（腾讯实测：总资产误取 1.63 万亿 vs 真值 2.04 万亿 → 资产平衡校验 0/4）。
#
# 规则（最短/最精确优先 + 中文构词法）：
#   若核心名 K 在表中**精确存在**，则删除所有**以 K 开头且不等于 K** 的科目 ——
#   中文报表里「核心名 + 后缀修饰」= 衍生小计，而「前缀修饰 + 核心名」= 有效分项
#   （如"归属于母公司股东权益合计"保留，因其核心名在末尾而非开头）。
# 【关键】引擎精确关键词归一化
# build_metrics 取数只认 arr(bs,["资产总计"]) / arr(bs,["负债合计"]) / arr(ist,["归属于母公司股东的净利润"])
# 这类**全称**，评分体系为 精确相等(3) > 别名命中(2) > 包含(1)。
# 港/美报表给的"总资产"/"总负债"/"归母净利润"只有 2 分，会被顺序更靠前的噪声项抢跑：
#   · "总资产减流动负债"(腾讯) 抢跑 → 总资产少算 21% → 资产平衡校验 0/4
#   · "总权益及总负债"(阿里) 抢跑 → 负债被当成总资产 → 资产负债率算成 100%
#   · "归属于优先股净利润及其他项"(阿里) 抢跑 → 归母净利算成 -23 亿
# 写 CSV 前统一改成引擎全称，拿到 3 分精确命中，从根本上杜绝抢跑。
ENGINE_ALIAS = {
    "总资产": "资产总计",
    "总负债": "负债合计",
    "归母净利润": "归属于母公司股东的净利润",
    "股东权益": "归属于母公司股东权益合计",
    "总权益": "股东权益合计",
}
CORE_KEYS = [
    "总资产", "总负债", "负债合计", "股东权益合计", "所有者权益合计", "净资产",
    "营业收入", "营业成本", "毛利", "净利润", "归母净利润", "营业利润",
    "流动资产合计", "非流动资产合计", "流动负债合计", "非流动负债合计",
]


def dedup_ambiguous(data):
    """剔除衍生小计行，返回 (清洗后data, 被剔除项列表)"""
    dropped = []
    # ① 以核心名开头的衍生小计（如"总资产减流动负债"抢跑"总资产"）
    for k in CORE_KEYS:
        if k not in data:          # 核心名须精确存在，否则不干预（避免误删唯一来源）
            continue
        for item in list(data.keys()):
            if item != k and item.startswith(k):
                dropped.append(item)
                del data[item]
    # ② 并列连词合计行（如阿里"总权益及总负债"=总资产，却抢跑"总负债" → 资产负债率算成100%）
    #    仅在"总资产"精确存在时剔除，避免删掉唯一来源
    if "总资产" in data:
        for item in list(data.keys()):
            if (item != "总资产" and item.startswith("总")
                    and any(c in item for c in ("及", "与", "和", "减"))):
                dropped.append(item)
                del data[item]
    # ③ 含核心名、但核心名既不在开头也不在结尾的夹心衍生项
    #    （如阿里"归属于优先股净利润及其他项"抢跑"净利润" → 归母算出 -23 亿）
    #    核心名在开头=衍生小计(已由①删) / 在结尾=有效分项(保留) / 夹在中间=噪声(删)
    for k in CORE_KEYS:
        if k not in data:
            continue
        for item in list(data.keys()):
            if item != k and k in item and not item.startswith(k) and not item.endswith(k):
                dropped.append(item)
                del data[item]
    return data, sorted(set(dropped))


US_SUFFIX = (".O", ".N", ".A", ".P", ".Q")   # NASDAQ / NYSE / NYSE American / NYSE Arca / Nasdaq


def detect_market(secucode):
    """按代码后缀判市场；返回 hk / us / a(A股,本脚本不支持) / unknown"""
    s = secucode.upper().strip()
    if s.endswith(".HK"):
        return "hk"
    if s.endswith(US_SUFFIX):
        return "us"
    if s.isdigit() and len(s) == 6:
        return "a"
    return "unknown"


def em_get(report_name, secucode, page_size=200):
    """东财 datacenter 统一请求（curl 子进程走代理 + 串行限流 + UA/Referer）。仅拉年报期。"""
    params = {
        "reportName": report_name,
        "columns": "ALL",
        "filter": '(SECUCODE="%s")(REPORT_TYPE="年报")' % secucode,
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": "REPORT_DATE",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
    }
    url = DATACENTER_URL + "?" + urllib.parse.urlencode(params)
    time.sleep(1.0)  # 串行限流，避免东财风控 (em_get 哲学)
    cmd = [
        "curl", "-s", "--max-time", "30", url,
        "-H", "User-Agent: %s" % UA,
        "-H", "Referer: https://emweb.securities.eastmoney.com/",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=40).stdout
        d = json.loads(out)
    except Exception as e:
        print("  ⚠️ 请求失败: %s" % e)
        return []
    return (d.get("result") or {}).get("data") or []


def normalize_item(name):
    if not name:
        return ""
    return name.replace("　", "").replace(" ", "").replace("\t", "").strip()


def pivot(rows, market):
    """list[dict] -> (years_desc, {item: {year: amount}}, currency)"""
    data = {}
    years = set()
    currency = ""
    remap = ITEM_MAP.get(market, {})
    for r in rows:
        item = normalize_item(r.get("ITEM_NAME"))
        if not item:
            continue
        item = remap.get(item, item)  # 跨准则翻译 (精确改名)
        rd = (r.get("REPORT_DATE") or "")[:10]
        if not rd or rd < "2000":
            continue
        fy = rd[:4]  # fiscal year (港股12-31 / 美股9月末 均取年)
        try:
            amt = r.get("AMOUNT")
            val = float(amt) if amt not in (None, "") else None
        except (ValueError, TypeError):
            val = None
        if val is None:
            continue
        data.setdefault(item, {})[fy] = val
        years.add(fy)
        if not currency and r.get("CURRENCY"):
            currency = r.get("CURRENCY")
    ylist = sorted(years, reverse=True)
    return ylist, data, currency


def write_csv(out_dir, stmt, ylist, data):
    path = os.path.join(out_dir, OUT_NAME[stmt] + ".csv")
    used = {}
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("科目," + ",".join("%s年年报" % y for y in ylist) + "\n")
        for item, series in data.items():
            out_item = ENGINE_ALIAS.get(item, item)   # 归一化到引擎精确关键词(拿3分防抢跑)
            if out_item in used:                       # 撞名：保留先出现的，但必须出声（禁静默丢数）
                print("  ⚠️ 科目撞名已跳过: '%s' -> '%s'（已有同名，保留先出现者）" % (item, out_item))
                continue
            used[out_item] = True
            vals = [str(series.get(y, "")) for y in ylist]
            f.write(out_item + "," + ",".join(vals) + "\n")
    return path


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit("用法: build_online_puller.py <secucode> [--out <目录>]")
    secucode = args[0]
    # 默认落 ./01_中间产物_CSV输入/（对齐七步分析 00→01→02 布局），--out 可覆盖
    out_dir = os.path.join(os.getcwd(), "01_中间产物_CSV输入")
    if "--out" in args:
        i = args.index("--out")
        if i + 1 >= len(args):
            sys.exit("❌ --out 缺少目录参数。用法: build_online_puller.py <secucode> [--out <目录>]")
        out_dir = args[i + 1]
    os.makedirs(out_dir, exist_ok=True)

    market = detect_market(secucode)
    if market == "a":
        sys.exit("❌ %s 是 A 股代码，本脚本仅服务港股(.HK)/美股(.O/.N)。\n"
                 "   A股请走原链路：westock-mcp(MCP) 或 a-stock-data skill（见 SKILL.md §1.0）" % secucode)
    if market == "unknown":
        print("  ⚠️ 无法从后缀判市场，按美股处理。港股请写成 00700.HK，美股写成 AAPL.O / BABA.N")
        market = "us"
    print("市场: %s | 代码: %s" % (market, secucode))
    collected = {}   # stmt -> (ylist, data)
    currencies = []
    for stmt in ("balance", "income", "cashflow"):
        rows = em_get(REPORT_MAP[stmt][market], secucode)
        if not rows:
            print("  ⚠️ %s 无数据" % OUT_NAME[stmt])
            continue
        ylist, data, currency = pivot(rows, market)
        data, dropped = dedup_ambiguous(data)
        if dropped:
            print("  · 剔除衍生小计行(防误匹配): %s" % "、".join(dropped[:6]))
        collected[stmt] = (ylist, data)
        currencies.append(currency)
        print("  · %s.csv 原始 %d 科目 %d 年(%s..%s) 币种=%s"
              % (OUT_NAME[stmt], len(data), len(ylist), ylist[-1], ylist[0], currency))
    if not collected:
        sys.exit("❌ 三张表均无数据，终止。\n"
                 "   排查：①代码格式（港股 00700.HK / 美股 AAPL.O、BABA.N）②该标的东财是否收录\n"
                 "         ③网络或东财风控（可稍后重试）")
    # 三表缺一不可：build_metrics 硬要求三张表齐备，缺表必须报错而非产出半成品
    missing = [OUT_NAME[s] for s in ("balance", "income", "cashflow") if s not in collected]
    if missing:
        sys.exit("❌ 未取到数据：%s —— 三张表缺一不可，已终止（不产出残缺 CSV）。\n"
                 "   排查：①东财该标的此报表缺失 ②网络/风控，稍后重试 ③代码是否正确" % "、".join(missing))
    # 港股 IFRS 无"营业成本"科目, 用 营收-毛利 反推注入, 修复毛利率 (零回归不改 build_metrics)
    if market == "hk" and "income" in collected:
        _yl, _di = collected["income"]
        if "营业收入" in _di and "毛利" in _di:
            _di["营业成本"] = {y: round(_di["营业收入"].get(y, 0) - _di["毛利"].get(y, 0), 2)
                               for y in _yl}
    # 取三表年份交集，保证 build_metrics 年份范围一致 (硬约束)
    common = None
    for stmt, (ylist, _) in collected.items():
        common = set(ylist) if common is None else (common & set(ylist))
    common = sorted(common, reverse=True)
    if not common:
        sys.exit("❌ 三张表无共同报告期，无法对齐，终止")
    # 剔除「负债与权益同时缺失」的年份（东财早年常缺列，会让资产平衡校验假失败）
    if "balance" in collected:
        _db = collected["balance"][1]
        def _zero(y):
            g = lambda k: (_db.get(k) or {}).get(y) or 0
            return (not (g("负债合计") or g("总负债") or g("负债总额"))
                    and not (g("股东权益合计") or g("净资产") or g("所有者权益合计")))
        bad = [y for y in common if _zero(y)]
        if bad:
            common = [y for y in common if y not in bad]
            print("  ⚠️ 剔除负债/权益均缺的年份: %s" % "、".join(bad))
    if not common:
        sys.exit("❌ 剔除缺失年份后无有效报告期，终止")
    currency = next((c for c in currencies if c), "")
    meta = {"secucode": secucode, "market": market, "currency": currency,
            "years_common": common, "years": {}}
    for stmt, (ylist, data) in collected.items():
        write_csv(out_dir, stmt, common, data)
        meta["years"][stmt] = ylist
        print("  ✅ %s.csv 已裁切至 %d 年(%s..%s)"
              % (OUT_NAME[stmt], len(common), common[-1], common[0]))
    with open(os.path.join(out_dir, "_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("完成 → %s (统一 %d 年, 币种=%s)" % (out_dir, len(common), currency))


if __name__ == "__main__":
    main()
