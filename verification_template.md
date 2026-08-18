# {公司名称} 财报分析 - 验证报告

> 生成时间：{生成时间}  
> 验证状态：✅ 已完成    
> 验证年报：{pdf_paths}  
> 初版报告：{初版报告路径}  
> 数据来源档位：{source_tier}（RICH / MEDIUM / LEAN / ONLINE）
> Phase 0 指标生成：引擎 seven-step-metrics-csv（{engine_version}）→ output.csv：`{output_csv_path}`；辅助CSV：segment={有/无} / headcount={有/无} / forecast={有/无}

---

## 一、验证总结

| 统计项 | 数量 |
|--------|------|
| 识别异常点总数 | {total_count} 个 |
| ✅已验证（引原文） | {verified_count} 个 |
| ✅已解释（引旁证） | {explained_count} 个 |
| ⚠️数据缺口（方向+🥉） | {gap_count} 个 |

**验证覆盖率**：{coverage_rate}%

---

## 二、详细验证结果

### 异常点 #1：{异常标题}

**来源**：第 {step_num} 步 - {step_name}    
**异常描述**：{anomaly_description}    
**原始数据**：{related_data}

#### 年报验证结果

**查阅章节**：{section_name}（第 {page_num} 页）    
**年报原文引用**：
> {pdf_quote_text}（限 200 字）

**验证结论**：
- {✅ 已验证（引原文）/ ✅ 已解释（引旁证）/ ⚠️ 数据缺口（方向+🥉）}
- **原因**：{anomaly_explanation}
- **风险等级**：{risk_level}（低 / 中 / 高）

**修正建议**：
- {correction_suggestion}

---

### 异常点 #2：{异常标题}

（同上格式，每个异常点一份）

---

## 三、报告修正建议

### 3.1 数据修正（如有）

| 修正项 | 原报告数值 | 年报实际数值 | 修正说明 |
|--------|--------------|----------------|----------|
| {correction_item} | {original_value} | {actual_value} | {correction_note} |

### 3.2 分析结论修正

| 修正项 | 原报告结论 | 修正后结论 | 依据 |
|--------|--------------|----------------|------|
| {conclusion_item} | {original_conclusion} | {corrected_conclusion} | {basis} |

### 3.3 新增信息（从年报中补充）

| 新增信息类型 | 内容摘要 |
|------------|----------|
| {info_type} | {info_summary} |

---

## 四、最终投资建议（更新版）

### 4.1 更新后的投资评级

**原评级**：{original_rating}  
**更新后评级**：{updated_rating}  

**调整理由**：
{rating_change_reason}

### 4.2 关键风险点（验证后更新）

| 风险点 | 风险等级 | 验证结果 | 应对建议 |
|--------|----------|----------|----------|
| {risk_item} | {risk_level} | {verification_result} | {mitigation_suggestion} |

### 4.3 投资建议

{updated_investment_recommendation}

---

## 五、验证方法说明

### 5.1 验证流程

1. **解析初版报告**：使用正则表达式提取所有 `⚠️`、`需验证：`、`需关注：` 标注的异常点
2. **定位年报章节**：根据异常类型，优先查阅 MD&A、财务报表附注等相关章节
3. **提取相关文本**：使用 pdfplumber 库提取相关页面的文本内容
4. **分析异常原因**：基于年报原文，分析异常点的业务/财务原因
5. **生成验证结论**：给出验证结果（✅已验证/✅已解释/⚠️数据缺口）和风险等级

### 5.2 局限性说明

- 本报告由 AI 自动生成，验证结论仅供参考，不构成投资建议
- 年报文本提取可能不完整（尤其是扫描版 PDF），可能导致验证不充分
- 异常点识别依赖正则表达式，可能存在漏报或误报
- 验证结论需人工复核，标注"AI 验证，请人工确认"

---

**验证报告生成完成！** 🎉

> 最终报告已根据验证结果修正，数据准确性和分析结论可信度大幅提升。
