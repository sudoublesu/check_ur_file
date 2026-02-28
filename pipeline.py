#!/usr/bin/env python3
"""
pipeline.py - 规划文件校对主流程

将 read_docx / read_pdf / check_numbers / check_typos / add_comments
串联为一次调用，供命令行测试和后续 Streamlit UI 使用。

Usage:
    python pipeline.py input/文件.docx
    python pipeline.py input/文件.pdf --output output/ --ai deepseek
    python pipeline.py input/文件.docx --ai gemini
"""

import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime

# ── 将 scripts 目录加入模块搜索路径 ──────────────────────────────────
BASE_DIR = Path(__file__).parent
SCRIPTS_DIR = BASE_DIR / "skills" / "planning-proofreader" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from read_docx import extract_docx
from read_pdf import extract_pdf
from check_numbers import process_doc_json, cross_validate
from check_typos import check_typos
from add_comments import add_comments_to_docx


# ── 目录约定 ───────────────────────────────────────────────────────────
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"


# ══════════════════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════════════════

def run_pipeline(
    input_path: str,
    output_dir: str = None,
    progress_cb=None,
    ai_model: str = None,
) -> dict:
    """
    执行完整校对流程。

    Args:
        input_path : 输入文件路径（.docx 或 .pdf）
        output_dir : 输出目录，默认 output/
        progress_cb: 进度回调 progress_cb(step: str, pct: int)
                     供 Streamlit 等 UI 使用；为 None 时打印到终端
        ai_model   : "deepseek" / "gemini" / None（跳过 AI 步骤）

    Returns:
        {
          "doc_content": dict,       # 文档结构化内容
          "numbers"    : dict,       # 提取的数字指标
          "typos"      : list,       # 错别字/格式问题列表
          "issues"     : list,       # 全部问题（合并后，传入批注）
          "ai_summary" : str,        # AI 整体评估（无 AI 时为空字符串）
          "report_path": str,        # 校对报告 .md 路径
          "docx_path"  : str | None, # 批注版 .docx 路径（pdf 输入时为 None）
        }
    """

    def report(step: str, pct: int):
        if progress_cb:
            progress_cb(step, pct)
        else:
            print(f"[{pct:3d}%] {step}")

    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"文件不存在：{input_path}")

    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    suffix = input_path.suffix.lower()
    stem = input_path.stem

    # ── Step 1：读取文件 ───────────────────────────────────────────────
    report("读取文件内容…", 10)
    if suffix == ".docx":
        doc_content = extract_docx(str(input_path))
    elif suffix == ".pdf":
        doc_content = extract_pdf(str(input_path))
    else:
        raise ValueError(f"不支持的文件类型：{suffix}（仅支持 .docx / .pdf）")

    _save_temp("doc_content.json", doc_content)

    # ── Step 2：提取数字指标 ───────────────────────────────────────────
    report("提取数字指标…", 30)
    numbers = process_doc_json(doc_content)
    _save_temp("numbers.json", numbers)

    # ── Step 3：错别字 & 格式检查 ──────────────────────────────────────
    report("检查错别字和格式问题…", 50)
    paragraphs = doc_content.get("paragraphs", [])
    typos = check_typos(paragraphs)
    _save_temp("typos.json", typos)

    # ── Step 3b：数字指标交叉校验 ──────────────────────────────────────
    number_issues = cross_validate(
        numbers, paragraphs,
        doc_content.get("tables", []),
        doc_content.get("table_positions", {}),
    )
    _save_temp("number_issues.json", number_issues)

    # ── Step 4：AI 深度校对 ────────────────────────────────────────────
    ai_issues: list = []
    ai_summary: str = ""

    if ai_model:
        report(f"AI 深度校对（{ai_model}）…", 70)
        try:
            ai_issues, ai_summary = _call_ai(
                ai_model, doc_content, numbers, typos
            )
            _save_temp("ai_issues.json", ai_issues)
        except Exception as e:
            report(f"AI 校对失败（{e}），跳过…", 70)
    else:
        report("跳过 AI 校对（未指定模型）…", 70)

    # 合并所有问题（顺序：错别字 → 数字校验 → AI）
    issues = typos + number_issues + ai_issues
    _save_temp("issues.json", issues)

    # ── Step 5：生成 Markdown 报告 ─────────────────────────────────────
    report("生成校对报告…", 85)
    report_path = out_dir / "校对报告.md"
    location_map = _build_para_location_map(doc_content.get("paragraphs", []))
    report_md = _build_report(stem, doc_content, numbers, issues, ai_summary, ai_model, typos, location_map, number_issues)
    report_path.write_text(report_md, encoding="utf-8")

    # ── Step 6：生成批注版 Word（仅 .docx）────────────────────────────
    docx_path = None
    if suffix == ".docx" and issues:
        report("生成批注版文档…", 95)
        docx_path = out_dir / f"{stem}_批注.docx"
        add_comments_to_docx(str(input_path), issues, str(docx_path))

    report("完成！", 100)

    return {
        "doc_content": doc_content,
        "numbers": numbers,
        "typos": typos,
        "number_issues": number_issues,
        "issues": issues,
        "ai_summary": ai_summary,
        "location_map": location_map,
        "report_path": str(report_path),
        "docx_path": str(docx_path) if docx_path else None,
    }


# ══════════════════════════════════════════════════════════════════════
#  报告生成
# ══════════════════════════════════════════════════════════════════════

def _infer_heading_level(para: dict) -> int:
    """
    从段落推断标题层级（1/2/3…），0 表示正文。

    优先使用 read_docx 已识别的 level 字段；
    若为 0，则尝试从样式名推断——支持自定义样式如
    '0-1'（一级）、'0-1.1'（二级）、'1.1.1'（三级）等。
    """
    import re as _re
    level = para.get("level", 0)
    if level > 0:
        return level

    style = para.get("style", "")
    # 处理 "前缀-层级编号" 格式，如 "0-1"→L1，"0-1.1"→L2，"0-1.1.1"→L3
    # 取最后一个连字符之后的部分，检查是否为 "数字(.数字)*"
    part = style.rsplit("-", 1)[-1] if "-" in style else style
    m = _re.match(r'^(\d+(?:\.\d+)*)$', part)
    if m:
        return part.count('.') + 1                  # 点数 + 1 = 层级

    return 0


def _build_para_location_map(paragraphs: list) -> dict:
    """
    为每个段落建立「章节位置」描述，供报告定位使用。

    Returns:
        {para_index: "位置描述"}
        例：{73: "「二、现状分析 · 2.1 用地现状」第3段"}
    """
    location_map: dict = {}
    headings: dict = {}   # level(1/2/3) -> heading_text
    body_count: int = 0   # 当前章节内正文段计数

    for para in paragraphs:
        idx   = para["index"]
        text  = para.get("text", "")
        level = _infer_heading_level(para)

        if level > 0:
            headings[level] = text
            for l in list(headings.keys()):
                if l > level:
                    del headings[l]
            body_count = 0
            location_map[idx] = f"「{text[:30]}」（章节标题）"
        else:
            body_count += 1
            if headings:
                deepest = max(headings.keys())
                section = headings[deepest][:20]
                parent_level = deepest - 1
                if parent_level >= 1 and parent_level in headings:
                    parent = headings[parent_level][:15]
                    loc = f"「{parent} · {section}」第{body_count}段"
                else:
                    loc = f"「{section}」第{body_count}段"
            else:
                loc = f"开篇第{body_count}段"
            location_map[idx] = loc

    return location_map


def _call_ai(
    model: str,
    doc_content: dict,
    numbers: dict,
    typos: list,
) -> tuple:
    """根据模型名称调用对应的 AI 客户端。"""
    if model == "deepseek":
        from app.ai.deepseek import proofread
    elif model == "gemini":
        from app.ai.gemini import proofread
    elif model == "claude":
        from app.ai.claude import proofread
    else:
        raise ValueError(f"不支持的 AI 模型：{model}（可选：deepseek / gemini / claude）")
    return proofread(doc_content, numbers, typos)


def _build_report(
    filename: str,
    doc_content: dict,
    numbers: dict,
    issues: list,
    ai_summary: str = "",
    ai_model: str = None,
    typos: list = None,
    location_map: dict = None,
    number_issues: list = None,
) -> str:
    errors = [i for i in issues if i.get("severity") == "error"]
    warnings = [i for i in issues if i.get("severity") == "warning"]
    suggestions = [i for i in issues if i.get("severity") == "suggestion"]
    today = datetime.now().strftime("%Y年%m月%d日")
    ai_label = {
        "deepseek": "DeepSeek",
        "gemini": "Gemini",
        "claude": "Claude",
    }.get(ai_model or "", "")
    gen_method = (
        f"自动检查（错别字 + 格式规则）+ {ai_label} 深度校对"
        if ai_label else "自动检查（错别字 + 格式规则），AI 深度校对未启用"
    )

    lines = [
        f"# 校对报告 — {filename}",
        "",
        f"**校对日期：** {today}",
        f"**生成方式：** {gen_method}",
        "",
        "---",
        "",
        "## 总体评估",
        "",
        *(
            [f"> {ai_summary}", ""]
            if ai_summary else []
        ),
        (
            f"共发现 **{len(issues)}** 项潜在问题"
            f"（错别字/格式 {len(typos or [])} 项"
            + (f" + 数字校验 {len(number_issues or [])} 项" if number_issues else "")
            + (f" + {ai_label} 深度校对 {len(issues) - len(typos or []) - len(number_issues or [])} 项" if ai_label else "")
            + "）："
        ),
        "",
        "| 问题级别 | 数量 |",
        "|---|---|",
        f"| 错误（必须修改） | {len(errors)} 项 |",
        f"| 警告（建议修改） | {len(warnings)} 项 |",
        f"| 建议（可考虑）   | {len(suggestions)} 项 |",
        "",
        "---",
        "",
    ]

    lmap = location_map or {}

    def _loc(item: dict) -> str:
        idx = item.get("para_index", -1)
        if idx < 0:
            return "位置未定位"
        return lmap.get(idx, f"第{idx}段")

    # 错误
    lines += ["## 一、错误（必须修改）", ""]
    if errors:
        lines += ["| 位置 | 问题描述 | 匹配文本 |", "|---|---|---|"]
        for item in errors:
            loc     = _loc(item).replace("|", "｜")
            comment = item.get("comment", "").replace("|", "｜")
            matched = item.get("matched", "").replace("|", "｜")
            lines.append(f"| {loc} | {comment} | `{matched}` |")
    else:
        lines.append("*未检测到错误。*")
    lines.append("")

    # 警告
    lines += ["---", "", "## 二、警告（建议修改）", ""]
    if warnings:
        lines += ["| 位置 | 问题描述 | 匹配文本 |", "|---|---|---|"]
        for item in warnings:
            loc     = _loc(item).replace("|", "｜")
            comment = item.get("comment", "").replace("|", "｜")
            matched = item.get("matched", "").replace("|", "｜")
            lines.append(f"| {loc} | {comment} | `{matched}` |")
    else:
        lines.append("*未检测到警告。*")
    lines.append("")

    # 建议
    lines += ["---", "", "## 三、建议（可考虑优化）", ""]
    if suggestions:
        lines += ["| 位置 | 问题描述 | 匹配文本 |", "|---|---|---|"]
        for item in suggestions:
            loc     = _loc(item).replace("|", "｜")
            comment = item.get("comment", "").replace("|", "｜")
            matched = item.get("matched", "").replace("|", "｜")
            lines.append(f"| {loc} | {comment} | `{matched}` |")
    else:
        lines.append("*无额外建议。*")
    lines.append("")

    lines += [
        "---",
        "",
        "*本报告由规划文件校对工具自动生成，请人工复核后使用。*",
    ]

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════════════════

def _save_temp(filename: str, data):
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMP_DIR / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
#  命令行入口
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="规划文件校对流程")
    parser.add_argument("input", help="待校对文件路径（.docx 或 .pdf）")
    parser.add_argument("--output", "-o", default=None, help="输出目录（默认 output/）")
    parser.add_argument(
        "--ai", choices=["deepseek", "gemini", "claude"], default=None,
        help="启用 AI 深度校对（需在 .env 中配置对应 API Key）",
    )
    args = parser.parse_args()

    try:
        result = run_pipeline(args.input, args.output, ai_model=args.ai)
    except (FileNotFoundError, ValueError) as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)

    print()
    print("═" * 50)
    print("校对完成")
    print(f"  问题总数 : {len(result['issues'])} 项")
    if result.get("ai_summary"):
        print(f"  AI 评估 : {result['ai_summary']}")
    print(f"  校对报告 : {result['report_path']}")
    if result["docx_path"]:
        print(f"  批注文档 : {result['docx_path']}")
    print("═" * 50)


if __name__ == "__main__":
    main()
