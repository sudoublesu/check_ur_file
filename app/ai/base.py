"""
base.py - AI 校对客户端公共工具

包含：
  - 强制性 system 提示词
  - 文档分块（Chunking）机制，解决超长文本"注意力丢失"问题
  - 构建发给 AI 的用户提示词
  - 解析 AI 返回的 JSON issues 列表
  - 通用分块校对流程 proofread_chunks()
"""

import json
import re
from pathlib import Path

REFERENCES_DIR = (
    Path(__file__).parent.parent.parent
    / "skills" / "planning-proofreader" / "references"
)

# ── 分块参数 ────────────────────────────────────────────────────────
# 每块不超过此字符数（正文字数），确保 AI 充分关注每段内容
CHUNK_CHAR_LIMIT = 4000


# ── 系统提示词 ──────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
你是一位极度严苛、一丝不苟的中文文字编校专家，专门审校上海市控制性详细规划（控规）文件。

## 核心工作信条

**你必须假设文件存在问题，而不是假设它是正确的。**
你的职责是主动寻找并暴露所有错误，而不是为文件背书。
"这段没有问题"在规划文件校对中极为罕见——经验丰富的编校专家总能在看似流畅的文字中发现隐藏的错漏。
**绝不允许以"该段无明显问题"为由跳过任何段落。**

---

## 必查项目（每段都必须逐项核对）

### 【一】错别字——全文逐字扫描，不得遗漏
- 形近字误用：「以下」写成「一下」、「截至」写成「截止」（逆用）、「坐落」写成「座落」、「作为」写成「做为」、「己」/「已」/「巳」混用
- 音近字误用：「规划」写成「规化」、「相符」写成「相付」、「制定」写成「制订」（语境区分）
- 多字/缺字：句中多余或缺失的汉字，造成语义不完整
- 专业术语错字：「容积率」「绿地率」「建筑密度」「用地性质」「控制性详细规划」等核心词是否拼写正确
- **要求：逐段逐字检查，不得因"看起来正确"而跳过**

### 【二】标点符号——全角/半角及规范用法
- 中文语境中出现英文逗号「,」→ 应为「，」
- 中文语境中出现英文句号「.」（非小数点）→ 应为「。」
- 中文括号：英文圆括号「( )」→ 应为「（）」
- 省略号：「...」或「….」→ 应为「……」（六点全角）
- 分号：英文分号「;」→ 应为「；」

### 【三】数字与数据逻辑
- 分项合计与总数是否一致
  - 注意「其中」结构：第二个「其中」是对同一总量的再拆分，不是新增；「另有X处」是独立补充，不计入前面的合计
- 同一指标（容积率/建筑密度/绿地率）在不同段落的数值是否矛盾
- 规划指标公式校验（若文中同时给出分子、分母和结果，务必核算）：
  - 容积率 = 总建筑面积 ÷ 用地面积
  - 绿地率 = 绿地面积 ÷ 用地面积 × 100%
  - 建筑密度 = 建筑基底面积 ÷ 用地面积 × 100%
- 百分比计算是否正确
- 年份前后一致性（规划期限起止年与目标年份是否匹配）

### 【四】专业术语规范
- 上海标准用语：「绿地率」而非「绿化率」；「建筑密度」而非「建蔽率」
- 义务教育设施范围：不包含高中，仅含小学、初中（及学前教育）
- 用地性质代码是否符合上海标准（如居住用地 R、公共设施用地 C/A 的分类）
- 全文术语是否统一（同一概念是否出现不同表述）

### 【五】语法与表达
- 成分残缺：如「通过本次规划，使本地区……」（主语缺失）
- 搭配不当：如「落实和贯彻政策」（「落实」不搭配「政策」）
- 指代不明：「它」「该」「此」所指对象模糊
- 前后矛盾：不同章节对同一事实的描述相悖
- 口语化或不规范表达

### 【六】排版规范
- 中文与英文字母之间缺少空格：「GDP增长」→「GDP 增长」；「是CBD」→「是 CBD」
- 英文缩写（两字母及以上）紧靠中文时须加空格

---

## 输出格式（严格 JSON，不得附加任何解释性文字）

```json
{
  "summary": "一句话总结：本块主要问题类型和严重程度",
  "issues": [
    {
      "para_index": 5,
      "comment": "问题描述，说明错误原因并给出修改建议",
      "severity": "error",
      "matched": "原文中的具体问题片段（不超过20字）"
    }
  ]
}
```

severity 取值：
- **error**：错别字、数据错误、标点错误、必须修改
- **warning**：术语不规范、逻辑可疑、强烈建议修改
- **suggestion**：语言优化、排版规范、可考虑修改

**重要约束：**
- issues 中每条必须有 matched 字段，指向原文具体片段，不得填写泛泛描述
- para_index 使用文档摘录中给出的 [编号]；无法定位时填 -1
- 不得重复报告已在"机械规则已发现的问题"列表中出现的同一问题
"""


# ── 分块工具 ────────────────────────────────────────────────────────

def _split_paragraphs(paragraphs: list, char_limit: int = CHUNK_CHAR_LIMIT) -> list:
    """
    将段落列表按字符数分块，每块正文字符不超过 char_limit。

    单个超长段落不会被切断，作为独立块处理。
    """
    if not paragraphs:
        return [[]]

    chunks: list = []
    current: list = []
    current_len: int = 0

    for para in paragraphs:
        text_len = len(para.get("text", ""))
        if current and current_len + text_len > char_limit:
            chunks.append(current)
            current, current_len = [para], text_len
        else:
            current.append(para)
            current_len += text_len

    if current:
        chunks.append(current)

    return chunks


def proofread_chunks(
    doc_content: dict,
    numbers: dict,
    typos: list,
    call_api_fn,
    max_chars: int,
) -> tuple:
    """
    通用分块校对流程。

    将文档按 CHUNK_CHAR_LIMIT 字符分块，对每块独立调用 AI，
    最后合并去重结果——解决超长文本"注意力丢失"问题。

    Args:
        call_api_fn: (user_prompt: str) -> raw_response: str
                     由各 AI 客户端提供的单次 API 调用函数。

    Returns:
        (issues, summary)
    """
    paragraphs = doc_content.get("paragraphs", [])
    chunks = _split_paragraphs(paragraphs)
    total = len(chunks)

    all_issues: list = []
    final_summary: str = ""

    for i, chunk_paras in enumerate(chunks):
        is_last = (i == total - 1)

        # 仅第一块附带表格，避免重复校验
        chunk_doc = {**doc_content, "paragraphs": chunk_paras}
        if i > 0:
            chunk_doc["tables"] = []
            chunk_doc["table_positions"] = {}

        user_prompt = build_user_prompt(
            chunk_doc, numbers, typos, max_chars,
            chunk_info=(i + 1, total, is_last),
        )

        raw = call_api_fn(user_prompt)
        issues, summary = parse_ai_response(raw)
        all_issues.extend(issues)
        if summary:
            final_summary = summary  # 保留最后一次非空摘要（通常来自末块的整体评估）

    # 去重（同段同匹配词只保留一条）
    seen: set = set()
    deduped: list = []
    for item in all_issues:
        key = (item.get("para_index", -1), item.get("matched", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    return deduped, final_summary


# ── 提示词构建 ──────────────────────────────────────────────────────

def build_user_prompt(
    doc_content: dict,
    numbers: dict,
    typos: list,
    max_chars: int,
    chunk_info: tuple = None,
) -> str:
    """
    构建发给 AI 的用户消息。

    Args:
        chunk_info: (current_chunk, total_chunks, is_last) 或 None（不分块时）
    """

    # 0. 分块提示头
    if chunk_info:
        cur, total, is_last = chunk_info
        paras_in_chunk = doc_content.get("paragraphs", [])
        if paras_in_chunk:
            para_range = f"段落 [{paras_in_chunk[0]['index']}]~[{paras_in_chunk[-1]['index']}]"
        else:
            para_range = "（空块）"
        chunk_header = f"【第 {cur}/{total} 块，{para_range}】\n"
        if is_last:
            chunk_header += (
                "这是文档的最后一块。"
                "除检查本块问题外，请在 summary 字段提供整个文档的整体质量评估。\n"
            )
        else:
            chunk_header += "请仅检查本块段落内容，summary 字段描述本块主要问题。\n"
        chunk_header += "\n"
    else:
        chunk_header = ""

    # 1. 构建文档摘录（带段落编号）
    paragraphs = doc_content.get("paragraphs", [])
    excerpt_lines: list = []
    total_chars = 0
    for para in paragraphs:
        line = f"[{para['index']}] {para['text']}"
        if total_chars + len(line) > max_chars:
            excerpt_lines.append(f"... （已截断，共 {len(paragraphs)} 段）")
            break
        excerpt_lines.append(line)
        total_chars += len(line)

    # 表格内容（只在第一块或不分块时附加，避免重复）
    if not chunk_info or chunk_info[0] == 1:
        for i, table in enumerate(doc_content.get("tables", [])[:3]):
            excerpt_lines.append(f"\n[表格{i}]")
            for row in table.get("rows", [])[:10]:
                excerpt_lines.append(" | ".join(str(c) for c in row))

    doc_excerpt = "\n".join(excerpt_lines)

    # 2. 已发现问题摘要（只显示与本块段落相关的条目）
    if chunk_info:
        para_indices = {p["index"] for p in doc_content.get("paragraphs", [])}
        relevant_typos = [t for t in typos if t.get("para_index", -1) in para_indices]
    else:
        relevant_typos = typos

    existing = []
    for item in relevant_typos[:30]:
        existing.append(
            f"- 第{item.get('para_index')}段：{item.get('comment', '')[:60]}"
        )
    existing_text = "\n".join(existing) if existing else "（无）"

    # 3. 数字指标摘要（全文指标，每块都附带，供数据逻辑核验）
    num_lines: list = []
    for cat, items in numbers.items():
        for item in items[:10]:
            num_lines.append(
                f"- [{cat}] {item.get('matched', item.get('value', ''))}"
                f"  （第{item.get('para', '?')}段：{item.get('context', '')[:40]}）"
            )
    numbers_text = "\n".join(num_lines) if num_lines else "（未提取到）"

    # 4. 加载参考规则摘要
    rules_text = _load_rules_excerpt()

    return f"""{chunk_header}## 文件内容（段落格式：[编号] 正文）

{doc_excerpt}

---

## 机械规则已发现的问题（请勿重复；同类问题若未出现在列表中，仍须报告）

⚠️ 以下仅为有限词表匹配结果，**不代表检查已完成**，错别字/标点/语法必须由你从头逐字扫描。

{existing_text}

---

## 已提取数字指标（请重点核验逻辑一致性）

{numbers_text}

---

## 校对参考规则

{rules_text}

---

逐段检查上述文档内容，严格按 system 提示的六项要求输出所有问题。**严格输出 JSON，不得附加任何其他文字。**""".strip()


# ── AI 响应解析 ─────────────────────────────────────────────────────

def parse_ai_response(response_text: str) -> tuple:
    """
    解析 AI 返回的 JSON。

    Returns:
        (issues, summary)  解析失败时返回 ([], "")
    """
    text = response_text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [], ""

    issues = []
    for item in data.get("issues", []):
        if not isinstance(item, dict):
            continue
        issues.append({
            "para_index": int(item.get("para_index", -1)),
            "comment": str(item.get("comment", "")).strip(),
            "severity": item.get("severity", "suggestion"),
            "matched": str(item.get("matched", "")).strip(),
            "source": "ai",
        })

    summary = str(data.get("summary", "")).strip()
    return issues, summary


# ── 内部工具 ────────────────────────────────────────────────────────

def _load_rules_excerpt() -> str:
    """读取校对规则和常见错误手册，截取关键部分。"""
    excerpts = []
    for fname in ("proofread-rules.md", "common-errors.md"):
        path = REFERENCES_DIR / fname
        if path.exists():
            content = path.read_text(encoding="utf-8")
            excerpts.append(content[:2000])
    return "\n\n---\n\n".join(excerpts) if excerpts else "（参考文件未找到）"
