# 七步财报分析法 · Seven-Step Financial Analysis

> **v2.1.2**｜基于饶刚《简明财务分析》「七步法」升级的财报分析引擎。三张原始表 → Phase 0 指标引擎 → 九步分析 → **HYDRO PAPER 研报级 HTML**（16 图 + 交付门禁），全程可离线、零远程资源、零第三方 Python 依赖；**最终 HTML 自包含单文件**（图表库/二维码/三层 CSS 全内联），单独转发也能看图。

数据来源支持三档：本地 CSV / **A 股 ONLINE 内置拉数（东财 F10 公开接口）** / 港股美股 ONLINE / 手动输入。没有本地财报也能闭环产出报告。

---

## 🧭 这是什么

| 项 | 说明 |
|---|---|
| **主要平台** | WorkBuddy（放入 `~/.workbuddy/skills/` 即可识别调用） |
| **其他 Agent** | 兼容。标准 Agent Skill 格式，支持 `SKILL.md` 约定的 Agent 均可加载；引擎为纯 Python 标准库 |
| **适用** | A 股 / 港股 / 美股上市公司财报深度分析，默认近 10 年年报 |
| **受众** | 二级市场普通投资者；行文「笔记风格」，专业名词首现必配大白话 |
| **核心价值** | 不是「算指标」，而是**数据 → 七步递进 → 八问商业模式 → 同行对比 → 可复算结论**的完整推理链，且每一步都有机械门禁兜底 |

**一句话**：把「读年报」工程化——三张表标准化、指标自动算、九步分析、报告数据驱动渲染、交付前 P0/P1 门禁全量拦截。

---

## ✨ 核心能力

- **HYDRO PAPER 研报皮肤**：暖纸底 + 宋体大标题 + 蓝色等高线艺术层 + 章节编号水印 + `FIG.01–16` 图表卡，单强调色；亮/暗主题由 `data-theme` 控制。三层 CSS 注入顺序固定：`hydro-base` → `hydro-skin` → `sevenstep-adapt`。
- **数据驱动渲染器** `scripts/render_report.py`：三种模式
  - A：`--data content.json` 全数据驱动；
  - B：`--data content.json --prefilled report_prefilled.html` 复用 `build_report_data.py` 抽出的 16 图脚本；
  - C：`--from-html 旧成品.html --data overrides.json` 仅换肤，数值零改动。
- **A 股 ONLINE 内置拉数**：`build_online_puller.py` 直连东财 F10 公开接口 `RPT_F10_FINANCE_G{BALANCE,INCOME,CASHFLOW}`，零第三方依赖；自动补 `.SH/.SZ` 后缀、`REPORT_TYPE=年报` + `REPORT_DATE` 双重期次隔离、`.BJ` 明确报错退出。
- **HTML 交付门禁** `scripts/check_html.py`：P0 拦截残留占位符、16 canvas ↔ 16 注册脚本、零远程资源、三层皮肤在位、内联 JS `node --check`、9 步 + 附录 + 免责声明、**静默空图**、**作者溯源二维码**、**页脚层级 P0-10**、**图表库自包含 P0-11**、**null 断点安全 P0-12**；P1 检查 emoji / Markdown 残留、图表卡与表格滚动容器覆盖率、Hero 数据截止时点。
- **静默空图防护**：缺 `segment_revenue.csv` / `headcount` / `peer_comparison.csv` 时不再画空坐标轴，改输出「本图数据未取得」提示卡，并由门禁反向阻断。
- **作者溯源页脚**：公众号 / 视频号二维码以 `data:image/png;base64,` 内嵌（不依赖远程图片），配置在 `assets/brand.json`，支持点击放大。
- **报告自包含契约（v2.1.2）**：`inline_lib()` 把 Chart.js 4.4.1 + datalabels 2.2.0 整段内联进 HTML，报告零远程、零同目录依赖；`check_html.py` 的 **P0-11** 禁止 `<script src="assets/...">`。把 HTML 单独放进空目录，真实浏览器实测 16/16 图真实绘制、console 0 错误。**P0-12** 加固 16 图的数据标签 formatter，缺值填 `null` 做断点时不再整图崩掉。
- **页脚层级契约（v2.1.1）**：`<footer class="report-footer">` 必须是 `<body>` 直接子元素，与 `.main-wrap` 兄弟。二者各自带 `padding-left`（48px / ≥1200px 时 248px，给固定侧栏让位）；若嵌套，偏移叠加两次，二维码溯源条会跑到页面中间。`check_html.py` 的 P0-10 栈解析门禁反向阻断。
- **端到端编排** `scripts/orchestrate.py`：fail-fast 闭环，核心步骤失败立即退出，不吞返回码。
- **A 股涨红跌绿**：`.up/.d` 红、`.down/.r` 绿，语义变量与颜色名解耦。

---

## 🔀 数据来源

| 方式 | 命令 / 说明 | 适用 |
|---|---|---|
| **A：本地 CSV** | 三张原始表 CSV（资产负债表 / 利润表 / 现金流量表）→ `--in <目录>` | 已有结构化数据 |
| **B：A 股 ONLINE** | `--online-a 601869 --years 10`，东财 F10 自动拉 10 年年报三表 | A 股，零外部数据源前置 |
| **C：港股 / 美股 ONLINE** | `build_online_puller.py` 行式接口分支 | 港美股 |
| **D：手动输入 / 联网旁证** | AI 列清单逐项补数 | 个别字段补数 |

> 无论哪档，最终统一：**落 3 张原始表 CSV → Phase 0 引擎 → `output.csv` → 九步分析 → HTML**。
> 输入契约：表头必须为 `科目, YYYY年年报, ...`，**左新右旧**；引擎只识别 `YYYY年年报` 列，季报 / 半年报列自动跳过。
> 期次隔离：当年三季报等中期数据须放进隔离区，不并入十年序列、不混算同比、不接入十年图表折线。

---

## 🔄 完整工作流

```
orchestrate.py --online-a <代码> --years 10 --out <产出目录> \
               --content <content.json> --report <最终报告.html>
  ↓
模块 -1  A 股 ONLINE 拉数（可选）  →  _online_input/ 三张宽表 + _meta.json
  ↓
Phase 0  build_metrics.py         →  output.csv + 辅助 CSV + data_status.md
         build_forecast.py        →  forecast_input.csv（一致预期）
         build_report_data.py     →  report_data.json + report_prefilled.html
  ↓
第1步 营收 · 第2步 成本 · 第3步 增长 · 第4步 业务构成 · 第5步 资产负债
第6步 投入产出 · 第7步 收益率 · 第8步 八问商业模式 · 第9步 同行对比
  ↓
validate_content.py --strict      →  R1–R8 内容质检（算式 / 标尺 / 咬合 / 数值自洽 / 反面假设 / 量纲）
  ↓
render_report.py                  →  HYDRO PAPER 16 图 HTML + 二维码页脚
  ↓
check_html.py --strict-p1         →  P0=0 / P1=0 方可交付
capture.py --all                  →  9 步 + 附录 + 页脚，共 11 张分段截图目视验收
```

---

## 📊 16 张图表

| 步骤 | 图表 |
|---|---|
| 第1步 | 图1 营收净利趋势、图2 盈利质量 |
| 第2步 | 图3 毛利率净利率、图4 费用率 |
| 第3步 | 图5 增长率、图6 CAGR 对比 |
| 第4步 | 图7 收入结构（100% 堆叠柱）、图8 业务毛利率 |
| 第5步 | 图9 资产结构、图10 负债率、图11 营运资本 |
| 第6步 | 图12 人均效率 |
| 第7步 | 图13 ROE/ROA/ROIC、图14 杜邦、图15 周转天数 |
| 第9步 | 图16 同行对比 |

> 图7 早期用 `line + fill + stacked + null` 会产生大面积堆叠色墙与断崖，v2.0 起改为 100% 堆叠柱 + `y.min=0,max=100`。
> 缺辅助表时对应图自动转「本图数据未取得」提示卡，禁止留空坐标轴冒充有数据。

---

## 📁 目录结构

```
seven-step-financial-analysis/
├── SKILL.md                        # 主流程与规范（含 §19 HYDRO PAPER 皮肤章节）
├── README.md                       # 本文件
├── report_template.html            # 报告模板骨架
├── verification_template.md        # 异常点验证模板
├── assets/
│   ├── hydro-base.css              # 皮肤第 1 层：基础变量 / 排版
│   ├── hydro-skin.css              # 皮肤第 2 层：HYDRO PAPER 视觉
│   ├── sevenstep-adapt.css         # 皮肤第 3 层：七步适配 + 空图卡 + 品牌页脚
│   ├── brand.json                  # 作者溯源配置（含二维码 base64）
│   ├── qr-wechat.png / qr-video.png
│   └── chart.umd.min.js / chartjs-plugin-datalabels.min.js   # 本地图表库
├── references/
│   ├── hydro-design-spec.md        # 七步专用视觉规格（v1.5）
│   ├── SOP_七步财报分析指标公式.md
│   ├── 内容标准_五件套.md / 阈值标尺库.md / 术语人话词典.md
│   ├── 反面假设清单.md / segment_aliases.json
├── scripts/                        # 15 个 Python 脚本，纯标准库
│   ├── build_online_puller.py      # A股/港股/美股 ONLINE 拉数
│   ├── build_metrics.py            # 指标引擎核心
│   ├── build_forecast.py / build_report_data.py / build_segment.py
│   ├── build_headcount.py / build_caliber_note.py / convert_input.py
│   ├── validate_content.py / validate_output.py / merge_line_fix.py
│   ├── orchestrate.py              # 端到端 fail-fast 编排
│   ├── render_report.py            # 数据驱动渲染 + 二维码页脚
│   ├── check_html.py               # HTML 交付门禁
│   └── capture.py                  # 分段截图验收
└── tests/test_segment_and_metrics.py
```

---

## 🚀 安装与使用

```bash
# 1. 放入 WorkBuddy skills 目录
cp -r seven-step-financial-analysis ~/.workbuddy/skills/

# 2. A 股一键闭环（示例：长飞光纤）
python3 ~/.workbuddy/skills/seven-step-financial-analysis/scripts/orchestrate.py \
  --online-a 601869 --years 10 --out ./out \
  --content ./content.json --report ./长飞光纤_七步财报分析报告.html

# 3. 本地 CSV 档
python3 .../orchestrate.py --in ./raw_csv --out ./out \
  --content ./content.json --report ./report.html
```

对话中触发：「用七步分析法分析一下 XXX」。

**报告纪律**：关键数据带来源与时点；投资判断必须附免责声明；禁止编造数据、禁止概念混淆、禁止数据自相矛盾。

---

## 📝 版本历史

| 版本 | 核心变化 |
|---|---|
| v1.x ~ v7.1 | 七步法基础版 → 笔记风格叙事 → 大厂研报版式 → 内置指标引擎 → 图表本地化 |
| **v2.0.0** | 沉淀 HYDRO PAPER v3.0 皮肤；新增数据驱动 `render_report.py`、HTML 门禁 `check_html.py`、分段截图 `capture.py`；`orchestrate.py` 改 fail-fast；修复约 42 项 bug |
| **v2.0.1** | 静默空图 P0-8：缺辅助表改提示卡，门禁反向阻断 |
| **v2.0.2** | A 股 ONLINE 内置拉数（东财 F10）；修复图16 缺 `peer_comparison.csv` 时残留占位符 P0；换源逐格登记口径差异 |
| **v2.1.2** | 修复「报告单独复制/转发后 16 图全白」：图表库整段内联做自包含单文件（P0-11）；修复 A 股 ONLINE 无一致预期时 `null.toFixed` 让图6 整图渲染失败（P0-12）；三模式 + 完整闭环在纯空目录实测 16/16 图真实绘制、console 0 错误 |
| **v2.1.1** | 修复页脚层级 P0：`footer` 改回 `<body>` 直接子元素，消除 `padding-left` 双重偏移（二维码溯源条不再跑到页面中间）；新增 P0-10 门禁；三档视口坐标验收差为 0 |
| **v2.1.0** | 公众号 / 视频号二维码 brand 页脚（内嵌 data URI、零远程资源）；新增 P0-9 门禁；`capture.py` 增 `--section footer` |

> 已知限制见 `SKILL.md §19.6`：同源双版本尚未合并；`build_segment.py` 占比量纲假设；`build_forecast.py` 死代码；R4 仍为全文级弱校验；期次隔离依赖 `content.json` 的 `quarantine` 字段与人工纪律。

---

## 👤 作者与许可

**作者**：松幽（SongYouAI）

- 📱 公众号：**松幽舒苑**
- 🎬 视频号：**松幽AI**

**方法论参考**：饶刚《简明财务分析》「七步法」（升级版）。

**License**：MIT — 可自由使用、修改、分发，保留出处即可。

```
Copyright (c) 2026 松幽（公众号:松幽舒苑 | 视频号:松幽AI）
```

---

*本 Skill 基于 AI 对公开信息的整理分析，所有内容仅供参考，不构成任何投资建议。投资有风险，决策需谨慎。*
