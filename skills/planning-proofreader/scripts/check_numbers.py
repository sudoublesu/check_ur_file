#!/usr/bin/env python3
"""
check_numbers.py - 提取文档中所有数字/规划指标，辅助交叉核验

Usage:
    python check_numbers.py <doc_json>   # read_docx.py 或 read_pdf.py 的输出
    python check_numbers.py --text "直接输入文本"

Output JSON 结构:
{
  "areas":      [{"value": "12.5", "unit": "公顷", "context": "...", "para": 3}],
  "ratios":     [{"value": "0.8",  "unit": "容积率", "context": "...", "para": 5}],
  "years":      [{"value": "2035", "context": "...", "para": 1}],
  "populations":[{"value": "5万", "context": "...", "para": 2}],
  "others":     [{"value": "...", "context": "..."}]
}
"""

import sys
import json
import re
from collections import defaultdict


# 规划指标识别模式
PATTERNS = {
    "areas": [
        r'(\d+(?:\.\d+)?)\s*(?:平方公里|km²|km2)',
        r'(\d+(?:\.\d+)?)\s*(?:公顷|hm²|ha)',
        r'(\d+(?:\.\d+)?)\s*(?:平方米|m²|m2)',
        r'(\d+(?:\.\d+)?)\s*亩',
    ],
    "ratios": [
        r'容积率[为是：:]\s*(\d+(?:\.\d+)?)',
        r'建筑密度[为是：:]\s*(\d+(?:\.\d+)?)\s*%?',
        r'绿地率[为是：:]\s*(\d+(?:\.\d+)?)\s*%?',
        r'(\d+(?:\.\d+)?)\s*%.*?(?:绿地率|建筑密度|容积率)',
    ],
    "years": [
        r'(20[0-9]{2})\s*年',
        r'(19[0-9]{2})\s*年',
    ],
    "populations": [
        r'(\d+(?:\.\d+)?)\s*(?:万人|万户|万)',
        r'人口[为是：:]\s*(\d+(?:\.\d+)?)\s*万',
    ],
}


def find_in_text(text: str, para_idx: int = -1) -> dict:
    results = defaultdict(list)
    lines = text.split('\n')

    for line_idx, line in enumerate(lines):
        for category, pattern_list in PATTERNS.items():
            for pattern in pattern_list:
                for m in re.finditer(pattern, line):
                    # 提取上下文（前后30字）
                    start = max(0, m.start() - 30)
                    end = min(len(line), m.end() + 30)
                    context = line[start:end].strip()
                    results[category].append({
                        "value": m.group(1) if m.lastindex else m.group(0),
                        "matched": m.group(0),
                        "context": context,
                        "para": para_idx if para_idx >= 0 else line_idx,
                    })

    # 去重
    for cat in results:
        seen = set()
        deduped = []
        for item in results[cat]:
            key = (item['value'], item['para'])
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        results[cat] = deduped

    return dict(results)


def process_doc_json(doc_json: dict) -> dict:
    all_results = defaultdict(list)

    # 处理段落
    for para in doc_json.get('paragraphs', []):
        found = find_in_text(para['text'], para['index'])
        for cat, items in found.items():
            all_results[cat].extend(items)

    # 处理表格
    for table in doc_json.get('tables', []):
        for row in table.get('rows', []):
            for cell in row:
                found = find_in_text(cell)
                for cat, items in found.items():
                    all_results[cat].extend(items)

    # 处理 PDF full_text
    if 'full_text' in doc_json:
        found = find_in_text(doc_json['full_text'])
        for cat, items in found.items():
            all_results[cat].extend(items)

    return dict(all_results)


def _parse_cell_number(cell: str):
    """
    从表格单元格文本中解析数值，失败返回 None。
    处理：千位分隔符、单位后缀、百分号。
    """
    s = str(cell).strip()
    # 去除千分位逗号和中文逗号
    s = re.sub(r'[,，\s\u3000]', '', s)
    # 去除末尾单位（%/万/公顷/平方公里/平方米/亩/人/户/处/所/个/套/km²/hm²）
    s = re.sub(
        r'(?:%|％|万|平方公里|km²|km2|公顷|hm²|ha|平方米|m²|m2|亩|万人|万户|人|户|处|所|个|套)+$',
        '', s,
    )
    m = re.fullmatch(r'-?\d+(?:\.\d+)?', s)
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return None


def _remove_sub_items(vals: list, tol_abs: float) -> list:
    """
    从按行顺序排列的数值列表中自动去除嵌套子项，只保留顶层行。

    检测逻辑：若某行之后若干连续行的数值之和恰好等于该行的值（在容差内），
    则这些后续行视为该行的子项，予以排除。

    示例（规划用地表格）：
      住宅组团(16.37) → 二类住宅(13.65) + 三类住宅(2.72)
      基础教育(2.54)  → 初级中学(1.01) + 小学(0.86) + 幼托(0.67)
      绿地(7.34)      → 公共绿地(6.94) + 防护绿地(0.40)
    只返回顶层行：[16.37, 0.56, 2.54, 2.03, ..., 7.34]
    """
    n = len(vals)
    is_sub = [False] * n

    for i in range(n):
        if is_sub[i]:
            continue
        v_parent = vals[i]
        if v_parent is None or v_parent <= 0:
            continue
        tol = max(v_parent * 0.01, tol_abs)
        running = 0.0
        for j in range(i + 1, n):
            if is_sub[j] or vals[j] is None:
                continue
            running += vals[j]
            if abs(running - v_parent) <= tol:
                # 行 i+1..j 是行 i 的子项
                for k in range(i + 1, j + 1):
                    is_sub[k] = True
                break
            if running > v_parent + tol:
                break  # 已超出父项值，无子项

    return [v for v, sub in zip(vals, is_sub) if not sub]


def _validate_table_sums(tables: list, table_positions: dict = None) -> list:
    """
    检查表格中合计行/列的数值是否等于各顶层分项之和。

    逻辑：
      - 找到第一列含「合计/总计/小计/共计/汇总」的行
      - 收集该行之前的数据行数值（跳过「其中/含/包括」等显式子拆分行）
      - 通过 _remove_sub_items 自动识别并排除隐式嵌套子行
        （如「基础教育设施」下的「初级中学/小学/幼托」）
      - 将剩余顶层行求和，与合计值比对

    table_positions: {table_index: preceding_para_index} 来自 read_docx.py，
                     用于将批注精确定位到表格前一段落。
    """
    TOTAL_KW = ('合计', '总计', '小计', '共计', '汇总')
    # 子拆分行关键词：首列以这些词开头的行直接排除
    SUB_KW   = ('其中', '含', '包括', '其中：', '其中:')
    TOL_REL  = 0.005   # 相对容差 0.5%
    TOL_ABS  = 0.11    # 绝对容差（应对舍入误差）

    tbl_pos = table_positions or {}
    issues = []

    for tbl_idx, table in enumerate(tables):
        rows = table.get('rows', [])
        if len(rows) < 3:
            continue

        # 该表格在文档 body 中对应的段落位置（用于 Word 批注精确定位）
        para_idx_for_table = tbl_pos.get(tbl_idx, -1)

        for row_i, row in enumerate(rows):
            if not row:
                continue
            first_cell = str(row[0]).strip()
            if not any(kw in first_cell for kw in TOTAL_KW):
                continue

            # 对每一列做求和校验
            for col_j in range(1, len(row)):
                stated = _parse_cell_number(row[col_j])
                if stated is None or stated == 0:
                    continue

                # 收集数据行数值（按行顺序保留，用于子项检测）
                data_vals = []
                for data_i in range(1, row_i):
                    data_row = rows[data_i]
                    if not data_row:
                        continue
                    # 跳过「其中/含/包括」等显式子拆分行
                    data_first = str(data_row[0]).strip()
                    if any(data_first.startswith(kw) or data_first == kw
                           for kw in SUB_KW):
                        continue
                    if col_j >= len(data_row):
                        continue
                    v = _parse_cell_number(data_row[col_j])
                    if v is not None:
                        data_vals.append(v)

                if len(data_vals) < 2:
                    continue

                # 自动去除嵌套子行（如住宅组团下的二类/三类住宅），只保留顶层行
                top_vals = _remove_sub_items(data_vals, TOL_ABS)
                if len(top_vals) < 2:
                    continue

                computed = sum(top_vals)
                diff = computed - stated
                tol = max(abs(stated) * TOL_REL, TOL_ABS)

                if abs(diff) > tol:
                    issues.append({
                        'para_index': para_idx_for_table,
                        'comment': (
                            f'第 {tbl_idx + 1} 张表格「{first_cell}」行'
                            f'第 {col_j + 1} 列：'
                            f'分项之和 {computed:.6g} 与合计值 {stated:.6g} 不一致'
                            f'（差值 {diff:+.6g}），请核查数据'
                        ),
                        'severity': 'error',
                        'matched': str(row[col_j]).strip(),
                        'source': 'numbers',
                    })

    return issues


# 段落内求和校验（_validate_para_sums）已移除。
#
# 原因：段落中的数字常见嵌套"其中"结构，如：
#   「共169处，其中168处…，1处…。其中102处…、37处…、30处…。另有19处…」
# 此类结构中第二个"其中"是对同一总量的再拆分，"另有"是独立补充，
# "含X处"是附属说明，简单相加所有分项会产生大量误报。
# 段落语义层面的求和校验由 AI 负责，规则引擎只做结构清晰的表格校验。


def cross_validate(numbers: dict, paragraphs: list, tables: list = None, table_positions: dict = None) -> list:
    """
    对提取的数字指标进行交叉校验，返回标准格式的问题列表。

    校验内容：
      1. 同一指标（容积率/建筑密度/绿地率）在不同段落出现不同数值
      2. 指标数值超出合理范围
      3. 规划期限与文中目标年份不符
      4. 表格合计行与分项之和不一致
      5. 段落内"其中A、B……合计X"的求和一致性
    """
    issues = []

    # ── 1. 检测规划期限 ────────────────────────────────────────────────
    planning_start, planning_end = None, None
    for para in paragraphs:
        m = re.search(
            r'规划期限[为是：:]{0,2}\s*(\d{4})[年\-—~～至到]+(\d{4})年',
            para.get('text', ''),
        )
        if m:
            planning_start = int(m.group(1))
            planning_end   = int(m.group(2))
            break

    # ── 2. 同一指标多值矛盾 ────────────────────────────────────────────
    RATIO_KEYWORDS = {
        '容积率':  (0.1, 8.0),
        '建筑密度': (5.0, 80.0),
        '绿地率':  (5.0, 70.0),
    }
    ratio_occurrences: dict = {kw: [] for kw in RATIO_KEYWORDS}

    for item in numbers.get('ratios', []):
        ctx = item.get('context', '')
        val_str = item.get('value', '')
        try:
            val = float(val_str)
        except ValueError:
            continue
        for kw in RATIO_KEYWORDS:
            if kw in ctx:
                ratio_occurrences[kw].append({
                    'val': val, 'para': item.get('para', -1), 'ctx': ctx,
                })

    for kw, occ_list in ratio_occurrences.items():
        if not occ_list:
            continue
        unique_vals = sorted({o['val'] for o in occ_list})
        # 多个不同值 → 矛盾
        if len(unique_vals) > 1:
            val_str = '、'.join(str(v) for v in unique_vals)
            paras   = '、'.join(str(o['para']) for o in occ_list)
            issues.append({
                'para_index': occ_list[0]['para'],
                'comment': (
                    f'「{kw}」在文中出现多个不同数值（{val_str}），'
                    f'涉及第 {paras} 段，请核实是否为不同地块或章节笔误'
                ),
                'severity': 'warning',
                'matched': kw,
                'source': 'numbers',
            })
        # 超出合理范围
        lo, hi = RATIO_KEYWORDS[kw]
        for o in occ_list:
            v = o['val']
            if not (lo <= v <= hi):
                issues.append({
                    'para_index': o['para'],
                    'comment': (
                        f'「{kw}」数值 {v} 超出合理范围（{lo}–{hi}），'
                        f'请核实是否笔误或单位有误'
                    ),
                    'severity': 'warning',
                    'matched': str(v),
                    'source': 'numbers',
                })

    # ── 3. 目标年份与规划期限不符 ──────────────────────────────────────
    if planning_end:
        target_pattern = re.compile(
            r'到\s*(20\d{2})\s*年|'
            r'(20\d{2})\s*年(?:底|末|前|实现|达到|完成)',
        )
        for para in paragraphs:
            text = para.get('text', '')
            idx  = para.get('index', -1)
            for m in target_pattern.finditer(text):
                year = int(m.group(1) or m.group(2))
                if year > planning_end and '规划' not in text[max(0, m.start()-5):m.start()]:
                    issues.append({
                        'para_index': idx,
                        'comment': (
                            f'目标年份 {year} 年超出本规划期末（{planning_end} 年），'
                            f'请确认是引用上位规划还是本规划目标年份有误'
                        ),
                        'severity': 'suggestion',
                        'matched': f'{year}年',
                        'source': 'numbers',
                    })

    # ── 4. 表格合计行校验 ──────────────────────────────────────────────
    # 表格结构规整，规则可靠；段落语义求和由 AI 负责（见注释）
    if tables:
        issues.extend(_validate_table_sums(tables, table_positions))

    return issues


def main():
    if len(sys.argv) < 2:
        print("Usage: python check_numbers.py <doc.json> [output.json]", file=sys.stderr)
        print("       python check_numbers.py --text '文本内容'", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == '--text':
        text = sys.argv[2] if len(sys.argv) > 2 else sys.stdin.read()
        results = find_in_text(text)
        output_path = None
    else:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            doc_json = json.load(f)
        results = process_doc_json(doc_json)
        output_path = sys.argv[2] if len(sys.argv) > 2 else None

    output_str = json.dumps(results, ensure_ascii=False, indent=2)
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output_str)
        print(f"数字指标已写入：{output_path}")
    else:
        print(output_str)


if __name__ == '__main__':
    main()
