#!/usr/bin/env python3
"""
check_typos.py — 规划文件错别字及语言问题检查
输入：doc_content.json（由 read_docx.py 或 read_pdf.py 生成）
输出：typos.json（按段落索引列出的潜在问题）
"""

import json
import re
import sys
from pathlib import Path


# 注：形近字/音近字等错别字检查由 AI 负责，不使用有限词表。
# 枚举词对的方式覆盖面有限（如「一下问题」不同于「一下内容」），
# 容易造成漏报；AI 逐字扫描可以覆盖所有实际出现的错别字。

# ──────────────────────────────────────────────
# 格式规则（正则）
#    格式：(pattern, message, severity)
# ──────────────────────────────────────────────
FORMAT_RULES = [
    # 年份区间括号内应包含"年"字
    (
        r'（\d{4}[-—–]\d{4}）年',
        '年份区间括号格式错误：「（XXXX-XXXX）年」应改为「（XXXX—XXXX年）」',
        'suggestion'
    ),
    # 百分号前有空格
    (
        r'\d\s+%',
        '百分号前有多余空格，建议删除',
        'suggestion'
    ),
    # 「一下」误用为「以下」（高频错别字，AI 易遗漏）
    # 匹配「一下」后接列举性词语，在规划文本中几乎必为「以下」
    (
        r'一下(?:问题|内容|情况|原则|要求|措施|做法|分析|规定|规范|标准|'
        r'方面|规划|建议|说明|所述|情形|几种|几点|几个|几条|几类|几项|事项|'
        r'指标|目标|任务|重点|方向|基础|依据|政策)',
        '疑似错别字：「一下」应为「以下」',
        'error'
    ),
    # 重复词语（ABAB式，排除常见叠词如"一一""各各"）
    (
        r'(?<![一各每])([\u4e00-\u9fa5]{2,4})\1(?![一各每])',
        '疑似重复词语，请核查是否为笔误',
        'suggestion'
    ),
    # 注：「首项逗号、其余顿号」规则误报率极高，已移除；
    # 全文错别字请使用 AI 深度校对模式进行检测。
]

# ──────────────────────────────────────────────
# 术语一致性（全文范围检查）
#    格式：(正确术语, [易混淆写法], 说明)
# ──────────────────────────────────────────────
TERM_CONSISTENCY = [
    (
        "江湾镇街道",
        ["新江湾镇街道", "新江湾镇"],
        "行政区划名称应统一为「江湾镇街道」"
    ),
    (
        "控制性详细规划",
        ["控制性规划", "控规详细规划"],
        "全称应为「控制性详细规划」"
    ),
    (
        "基础教育设施",
        ["基础教育设备", "教育基础设施"],
        "规范术语为「基础教育设施」"
    ),
    (
        "建筑密度",
        ["建蔽率", "建筑覆盖率"],
        "上海控规指标用「建筑密度」"
    ),
    (
        "绿地率",
        ["绿化率", "绿化覆盖率"],
        "规划指标用「绿地率」而非「绿化率」"
    ),
]


def check_typos(paragraphs: list) -> list:
    """对段落列表逐项检查，返回问题列表。"""
    issues = []
    seen_terms = {}  # 术语首次出现位置

    for para in paragraphs:
        idx = para.get("index", 0)
        text = para.get("text", "")
        if not text.strip():
            continue

        # 格式规则（结构化检查，规则可靠；错别字由 AI 逐字扫描）
        for pattern, message, severity in FORMAT_RULES:
            matches = re.findall(pattern, text)
            if matches:
                issues.append({
                    "para_index": idx,
                    "comment": f"[格式] {message}（匹配：{matches[0]}）",
                    "severity": severity,
                    "matched": str(matches[0])
                })

        # 术语一致性（收集出现位置）
        for correct_term, variants, note in TERM_CONSISTENCY:
            for variant in variants:
                if variant in text:
                    key = variant
                    if key not in seen_terms:
                        seen_terms[key] = []
                    seen_terms[key].append(idx)

    # 输出术语一致性问题
    for correct_term, variants, note in TERM_CONSISTENCY:
        for variant in variants:
            if variant in seen_terms:
                paras = seen_terms[variant]
                issues.append({
                    "para_index": paras[0],
                    "comment": (
                        f"[术语] 「{variant}」出现在第{paras}段，{note}。"
                        f"建议全文统一使用「{correct_term}」。"
                    ),
                    "severity": "warning",
                    "matched": variant
                })

    # 去重（同一段同一匹配词只报一次）
    seen = set()
    deduped = []
    for item in issues:
        key = (item["para_index"], item.get("matched", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    return sorted(deduped, key=lambda x: x["para_index"])


def main():
    if len(sys.argv) < 2:
        print("用法：python check_typos.py doc_content.json [output.json]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "typos.json"

    with open(input_path, encoding="utf-8") as f:
        doc = json.load(f)

    paragraphs = doc.get("paragraphs", [])
    if not paragraphs:
        print("未找到段落内容，请检查输入文件格式。")
        sys.exit(1)

    issues = check_typos(paragraphs)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(issues, f, ensure_ascii=False, indent=2)

    # 控制台摘要
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    suggestions = [i for i in issues if i["severity"] == "suggestion"]

    print(f"错别字检查完成：{len(issues)} 项潜在问题")
    print(f"  错误（错别字）：{len(errors)} 项")
    print(f"  警告（术语/数据）：{len(warnings)} 项")
    print(f"  建议（格式）：{len(suggestions)} 项")
    print(f"结果已写入：{output_path}")

    if issues:
        print("\n--- 问题摘要 ---")
        for item in issues:
            sev = {"error": "❌", "warning": "⚠️", "suggestion": "💡"}.get(item["severity"], "•")
            print(f"  {sev} 第{item['para_index']:>4}段：{item['comment'][:60]}...")


if __name__ == "__main__":
    main()
