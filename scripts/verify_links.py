#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
七步财报分析 · 发布前来源链接验活（辅助工具）
==============================================
本脚本是七步 skill 的**发布前验活**：探活成品 HTML 里来源角标的 http(s)
外链，列出明确失效（4xx/5xx）的 URL。默认恒 exit 0、只提示，**只有加
--strict 才在出现 dead 时阻断发布（exit 1）**，与八维的温和默认保持一致。

职责边界（与质量门禁分工，勿混）：
  - check_html.py 的 P0-13 只做 HTML 静态门禁（角标数 / 六元组列 /
    src-summary 锚点 / 非纯域名 / 角标 URL 登记 / 状态徽章），
    **门禁必须离线可跑，不能依赖网络**；
  - 链接「能否打开」由本脚本单独跑网络验活，不进静态门禁；
  - 两者都不判断页面里是否真有被引数字（仍需按
    references/source-spec.md 四级颗粒度人工抽查）。

HEAD 报 4xx/5xx 时再用 GET 复核一次（部分站点对 HEAD / 自定义 UA 返 404
但 GET 正常，只信 HEAD 会把好链误报成坏链）。网络不可达/超时、站点拒绝
HEAD（403/405/429）不计入失效，避免把环境问题误报成坏链。

用法:
    python3 verify_links.py <报告.html>
    python3 verify_links.py --report <报告.html> --limit 30 --timeout 5
    python3 verify_links.py <报告.html> --strict --json ./link_report.json

退出码: 默认恒 0（只提示，不阻断）；--strict 且出现 dead 时为 1。
依赖: 仅标准库
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import html
import json
import re
import sys
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; seven-step-verify/1.0)"


def collect(text):
    """抽取并去重；HTML 里的 &amp; 必须还原成 &，否则带查询参数的 URL 会被错误探活。"""
    seen, out = set(), []
    for u in re.findall(r'href=["\'](https?://[^"\']+)["\']', text):
        u = html.unescape(u)
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _request_code(url, timeout, method, extra_headers=None):
    """返回 HTTP 状态码；网络问题返回 None。"""
    headers = {"User-Agent": UA}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError, ValueError):
        return None


def probe(url, timeout):
    """返回 (ok|dead|skip, 说明)。HEAD 失效时以 GET 复核为准。"""
    code = _request_code(url, timeout, "HEAD")
    if code is None:
        return "skip", "网络不可达 / 超时"
    if code in (403, 405, 429):
        return "skip", f"HTTP {code}（站点拒绝探活，非链接失效）"
    if 200 <= code < 400:
        return "ok", f"HTTP {code}"
    # 站点对 HEAD / 自定义 UA 返 404 但 GET 正常 → 以 GET 为准，避免误删好链
    code2 = _request_code(url, timeout, "GET", {"Range": "bytes=0-0"})
    if code2 is None:
        return "dead", f"HTTP {code}（GET 复核超时）"
    if 200 <= code2 < 400:
        return "ok", f"HTTP {code2}（HEAD {code} → GET 复核可达）"
    return "dead", f"HTTP {code2}（HEAD {code}）"


def main():
    ap = argparse.ArgumentParser(description="七步报告来源链接验活（默认只提示不阻断，--strict 才阻断）")
    ap.add_argument("report", nargs="?", help="报告 HTML 路径（位置参数，向后兼容八维）")
    ap.add_argument("--report", dest="report_flag", help="报告 HTML 路径（等价可选写法）")
    ap.add_argument("--limit", type=int, default=0, help="最多探活 N 个（0=全部）")
    ap.add_argument("--timeout", type=float, default=5.0, help="单链接超时秒数，默认 5")
    ap.add_argument("--workers", type=int, default=8, help="并发探活数，默认 8")
    ap.add_argument("--strict", action="store_true", help="出现明确失效链接时 exit 1（默认恒 0）")
    ap.add_argument("--json", dest="json_path", default=None, help="把结果写成 JSON，供发布脚本机读")
    args = ap.parse_args()

    report = args.report_flag or args.report
    if not report:
        ap.error("缺少报告路径：用位置参数或 --report 指定")

    try:
        text = open(report, encoding="utf-8").read()
    except OSError as e:
        print(f"无法读取：{e}", file=sys.stderr)
        return 0

    urls = collect(text)
    collected = len(urls)
    if args.limit > 0:
        urls = urls[:args.limit]
    total = len(urls)
    print(f"收集唯一链接 {collected} 个 | 本次探活 {total} 个 | 超时 {args.timeout}s")

    stat = {"ok": 0, "dead": 0, "skip": 0}
    dead = []
    workers = max(1, min(args.workers, len(urls) or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for u, (st, msg) in zip(urls, pool.map(lambda x: probe(x, args.timeout), urls)):
            stat[st] += 1
            if st == "dead":
                dead.append((u, msg))
    print(f"可达 {stat['ok']} | 失效 {stat['dead']} | 跳过 {stat['skip']}")
    if dead:
        print("明确失效链接：")
        for u, msg in dead:
            print(f"  x {msg}  {u}")
    print("提示：网络不可达/超时、403/405/429 不计入失效；本脚本不验证页面内容。")

    if args.json_path:
        payload = {
            "total": total,
            "ok": stat["ok"],
            "dead": stat["dead"],
            "skip": stat["skip"],
            "dead_urls": [u for u, _ in dead],
            "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        try:
            with open(args.json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print(f"结果已写入：{args.json_path}")
        except OSError as e:
            print(f"JSON 写入失败：{e}", file=sys.stderr)

    if args.strict and stat["dead"] > 0:
        print(f"[strict] 检出 {stat['dead']} 个失效链接，阻断发布。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
