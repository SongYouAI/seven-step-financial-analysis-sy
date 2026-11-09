---
version: 1.3
name: seven-step-hydro-paper-adaptation
description: 七步财报分析复用的 HYDRO PAPER v3.0 皮肤规格与适配层约定。同源完整规格见八维行业分析 skill 的 references/hydro-design-spec.md。
status: 默认版式；取代七步模板自带的深蓝金棕 :root 表现（结构与类名不变）
---

# HYDRO PAPER v3.0 · 七步财报分析适配规格

## 1. 来源与边界

视觉源：桌面的「长江电力 · 中国大水电 · 八维行业分析报告.html」，其 `hydro-skin.css`
与八维行业分析 skill 的 `assets/hydro-skin.css` 实测字节一致。

**本 skill 与八维版的差异**（不要照搬八维规格里的组件）：

> v2.1.0 更新：页脚 brand 区块已按八维 v3.2.2 移植，不再列作差异；实现细节见 `SKILL.md §19.5.1`。

| 项 | 八维版 | 七步版 |
|---|---|---|
| 章节 | `dim1–dim8` + conclusion | `step1–step9` + appendix（9 步 + 附录） |
| 图表 | C1/C2/C3 三张 SVG | 16 张 Chart.js 图，`FIG.01–16` 卡 |
| 页脚 | `.brand-block` + 二维码 + `brand.json` + P0-16 | **v2.1.0 起同款** `.brand-block` + 二维码 + `brand.json` + P0-9；差异：七步禁用远程 URL、不提供 `branding.url` |
| 门禁 | `check_report.py` P0-12/P0-16 | `check_html.py` 的 P0/P1（见 §6） |
| 生成器 | 八维 `render_report.py` + `html_helpers.py` | 七步 `render_report.py`（不依赖 html_helpers） |

## 2. 设计令牌（来自 hydro-skin.css）

```
--p-paper    #f3f0e8   暖纸底          --p-surface  #ffffff  卡片
--p-ink      #12181c   主文字          --p-ink-2    #4f5a60  次要文字
--p-line     #e2ddd1   发丝线          --p-accent   #2a4bd7  唯一强调色
--p-risk     #c0442c   风险            --p-warn     #b7852a  警示/隔离区
--p-good     #12684a   正向
font-serif   "Songti SC" / STSong / Noto Serif CJK SC / Georgia
font-sans    "PingFang SC" / Inter / Microsoft YaHei
font-mono    SFMono-Regular / JetBrains Mono
```

暗色主题由 `html[data-theme="dark"]` 反相令牌，不改结构。
**禁项**：`opacity:0` 入场初始态、2px 以上粗线、渐变描边、多色强调、emoji 图标、远程字体/图片/CDN。

## 3. 三层 CSS 与注入顺序

`render_report.py` 在 `</head>` 之前按序注入，后者优先级最高：

1. `assets/hydro-base.css` — 模板原有基底（组件结构、布局、深色变量）。单独打开模板看到的深蓝紫金是 v2 遗留，会被覆盖，属正常。
2. `assets/hydro-skin.css` — 皮肤本体，`id="hydro-skin" data-design="HYDRO PAPER v3.0"`。
3. `assets/sevenstep-adapt.css` — 七步适配层，`id="sevenstep-adapt"`。

改样式只改第 2 层；新增七步专属组件只加在第 3 层；**不回写 `report_template.html`**。

## 4. 组件映射（七步 → HYDRO）

| 七步原始 | 适配后 | 说明 |
|---|---|---|
| `<section id="stepN" class="step-card">` | `<div class="step-card" id="stepN">` + `.step-head` + `.step-num-watermark` | 章节编号水印 `01–09`、附录 `10` |
| 裸图注 `<p>图N · …</p>` + 裸 canvas | `.chart-card` > `.chart-head`（`FIG.0N` 徽章）+ `.chart-body` | `clean()` 自动包装，幂等 |
| `.table-scroll` | `.table-wrap.table-scroll` | 保留移动端横向滚动 |
| `.kpi-grid/.kpi-card/.kpi-delta` | 沿用 HYDRO 同名类 | **涨红跌绿**：`.up` 红 / `.down` 绿 |
| 🥇🥈🥉🚫 | `.src-tag.a/.b/.c/.x` 文字徽章：公告/接口/旁证/未采用 | 避免字体缺字变豆腐块 |
| 金色 inline 隔离框 | `.source-box.quarantine` | 金色左边线，2026 前三季度等隔离期专用 |
| `.warning-box` / `.report-footer` | 适配层补齐 | 左侧 2px 警示线 / 顶部发丝线 |
| 旧单行署名 footer | `<footer class="report-footer">` + `.brand-block` + 2 张二维码 + `#qrLightbox` | 强制输出，二维码 data URI 内嵌，点击放大复用同一份图 |

Hero 结构：`.hero` + `.hero-art`（等高线 SVG，标签年份由 `years` 注入，x=360 防裁切）
+ `.hero-masthead` + `.hero-overline` + `h1[data-note]` + `.badge` + `.subtitle`
+ 四列 `.meta-row` + `.hero-foot`。侧栏 `.side-nav` 首屏带 `nav-hidden`，避免遮住 Hero。

## 5. 图表规则（踩过的坑）

- **图7 必须是 100% 堆叠柱**：`type:'bar'`、`x/y stacked`、`y.min=0,max=100`、实色、`null` 空档自然留白。
  旧版 `line + fill:true + stacked + tension` 会在 2019/2020 空值处拉出大面积色墙与斜切断崖，y 轴还会自动从 55% 起把 55–100% 拉满全屏。
- **图5 增长率**：数据 `drop_last()` 去掉最旧年，标签必须 `window.__years.slice(0,-1)`（旧版 `slice(1)` 去头，整体错一年）。
- **年份变量**：`__years` 左新右旧，`__yearStart`=最旧年、`__yearEnd`=最新年，`__yearSpan` 正序。
- **图12 人均**：`build_headcount.py` 写出的已是万元，`build_report_data.py` 必须 `as_is()` 原样透传，再 `to_wan()` 会缩小一万倍。
- **图16 同行**：`--peer peer_comparison.csv` 自动注入；缺文件时 `build_report_data.py` 写 `labels:[]` + 3 个 `data:[]`（**不可留 `{{CHART16_*}}` 占位符**，否则 P0-1 + 内联 JS 语法错误），由空图提示卡接管；补齐后重新生成自动出图。
- 图表色板由适配层 `--chart-1..6` 提供，boot 脚本读成 `window.__c`；脚本里的 emoji、旧 hex（`#1e5fb4` 等）由 `normalize_chart_colors()` 统一替换。
- 图表库只认同目录 `assets/chart.umd.min.js` + `chartjs-plugin-datalabels.min.js`，**无 CDN 兜底**。
- **禁交付空白坐标轴**：缺 `segment_revenue.csv` / `headcount` / `peer_comparison.csv` 时生成器会写 `names=[]` / `series=[]` / `data:[]` / `labels:[]`，Chart.js 仍画出一套空轴。`render_report.py` 的 `mark_empty_charts()` 会把这类图换成 `.chart-empty-note`（`FIG.NN · 未披露` + 「本图数据未取得」），canvas 置 `hidden` 以维持 16 ↔ 16 契约；**不插值、不编造**。提示卡说明文案按图号区分（图16 = 同行可比数据，其余 = 分业务/员工资料）。样式在适配层，门禁 P0-8 反向校验。

## 6. 门禁对应（scripts/check_html.py）

| 门禁 | 检查 |
|---|---|
| P0-1 | 大写叙事占位符零残留 |
| P0-2 | 16 canvas ↔ 16 `__reg` ID 一致 |
| P0-3 | 零远程 `src/href`、无 `cdn.jsdelivr` |
| P0-4 | 三层样式 `hydro-base` / `hydro-skin` / `sevenstep-adapt` 在位 |
| P0-5 | 内联 `<script>` 逐段 `node --check` |
| P0-6 | div/section/table/script/style/blockquote 标签配平 |
| P0-7 | 9 个 step-card + appendix + 免责声明 |
| P0-8 | 空数据图（`names=[]` / `series=[]` / `data:[]` / `labels:[]`）必须有对应 `data-chart` 的 `.chart-empty-note` 提示卡（静默空图阻断） |
| P0-9 | 作者溯源 brand 区块强制在位：brand-block / qrLightbox / 2 个 `.brand-qr` / 2 张 `data:image/png;base64,` / 公众号+视频号标识 |
| P1 | emoji / Markdown 残留、`.chart-card` 与 `.table-wrap` 覆盖、Hero 数据截止时点、本地 assets |

## 7. headless 截图坑

`file://报告.html#step4` 在无头 Chrome 里**不会滚动**，直接 `--screenshot` 会白屏（DOM 中图表其实已渲染）。
`capture.py` 的做法：把目标 section 裁成独立 HTML（复用完整 `<head>` + 全部 `<script>`，
本地 assets 改绝对 file URI + 覆盖层隐藏侧栏/渐入），再截图。不修改交付文件。
`--section footer` 与 `--all` 已包含页脚 brand 区块，用于二维码目视验收。

首屏截图里浮动侧栏压住 Hero 是 CSS 过渡未推进的中间帧（DOM 中已带 `nav-hidden`），
交付 HTML 无需为此做妥协性改动；生成器已让侧栏初始即隐藏。

## 8. 已知限制

- 图7/8 需 `build_segment.py` 注入业务构成，图12 需 `build_headcount.py` 注入员工构成，图16 需 `peer_comparison.csv`；缺辅助表时由生成器出「未披露」提示卡（数据仍不得编造、不得插值），补齐辅助表后重新生成即自动出图。
- 宋体标题依赖本机 `Songti SC`；无该字族时回落 Georgia/系统衬线，版心不塌陷。
- 等高线 SVG 是装饰性示意，不代表真实数据曲线。
