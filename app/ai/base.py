"""
base.py - AI 校对客户端公共工具

包含：
  - 构建发给 AI 的文档摘录
  - 解析 AI 返回的 JSON issues 列表
  - 所有客户端共享的提示词模板
"""

import json
import re
from pathlib import Path

REFERENCES_DIR = (
    Path(__file__).parent.parent.parent
    / "skills" / "planning-proofreader" / "references"
)

# ── 提示词 ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
你是上海市控制性详细规划（控规）文件的资深校对专家，兼具规划编制经验和中文语言文字功底。

## 你的核心任务

**必须逐段检查**，找出以下所有问题：

### 第一优先：错别字（全文扫描，不得遗漏）
- 形近字误用：如「以下」写成「一下」、「坐落」写成「座落」、「作为」写成「做为」
- 音近字误用：如「规划」写成「规化」、「设施」写成「设映」
- 多字/少字：句子中多余或缺失的字
- 规划专业术语错字：如「容积率」「绿地率」「建筑密度」「用地性质」等专业词是否正确
- **每一段都要仔细检查，不能跳过**

### 第二优先：数据逻辑矛盾
- 分项合计与总数不符
- 同一指标在不同章节数值不一致
- 百分比计算错误

### 第三优先：专业概念错误
- 术语含义用错（如将高中纳入义务教育设施范围）
- 用地性质代码或名称不符合上海标准

### 第四优先：内容与语言问题
- 前后矛盾：不同章节描述相悖
- 语言不规范：口语化、主语缺失、标题与内容不符
- 完整性：重要信息明显缺失

## 输出要求（严格 JSON，不得有其他文字）

```json
{
  "summary": "一句话总结文件整体质量及主要问题类型",
  "issues": [
    {
      "para_index": 5,
      "comment": "问题描述，说明错误原因和修改建议",
      "severity": "error",
      "matched": "原文中的问题片段（不超过20字）"
    }
  ]
}
```

severity 取值：
- error：错别字、数据错误、必须修改的问题
- warning：术语不规范、建议修改的问题
- suggestion：语言优化、可考虑修改

para_index 使用文档摘录中给出的编号；无法定位时使用 -1。
"""


def build_user_prompt(
    doc_content: dict,
    numbers: dict,
    typos: list,
    max_chars: int,
) -> str:
    """构建发给 AI 的用户消息。"""

    # 1. 构建文档摘录（带段落编号）
    paragraphs = doc_content.get("paragraphs", [])
    excerpt_lines = []
    total_chars = 0
    for para in paragraphs:
        line = f"[{para['index']}] {para['text']}"
        if total_chars + len(line) > max_chars:
            excerpt_lines.append(f"... （文档过长，已截断，共 {len(paragraphs)} 段）")
            break
        excerpt_lines.append(line)
        total_chars += len(line)

    # 表格内容（附加到摘录末尾，只取前3个表格）
    for i, table in enumerate(doc_content.get("tables", [])[:3]):
        excerpt_lines.append(f"\n[表格{i}]")
        for row in table.get("rows", [])[:10]:
            excerpt_lines.append(" | ".join(str(c) for c in row))

    doc_excerpt = "\n".join(excerpt_lines)

    # 2. 已发现问题摘要
    existing = []
    for item in typos[:30]:  # 最多30条，避免提示词过长
        existing.append(
            f"- 第{item.get('para_index')}段：{item.get('comment', '')[:60]}"
        )
    existing_text = "\n".join(existing) if existing else "（无）"

    # 3. 数字指标摘要
    num_lines = []
    for cat, items in numbers.items():
        for item in items[:10]:
            num_lines.append(
                f"- [{cat}] {item.get('matched', item.get('value', ''))}  "
                f"（第{item.get('para', '?')}段：{item.get('context', '')[:40]}）"
            )
    numbers_text = "\n".join(num_lines) if num_lines else "（未提取到）"

    # 4. 加载参考规则摘要
    rules_text = _load_rules_excerpt()

    return f"""
## 文件内容（段落格式：[编号] 正文）

{doc_excerpt}

---

## 机械规则已发现的问题（以下问题请勿重复；但同类问题若未在列表中出现，仍须报告）

⚠️ 注意：以下仅为有限词表匹配结果，**不代表错别字检查已完成**。错别字必须由你从头逐字扫描。

{existing_text}

---

## 已提取数字指标（请重点核验逻辑一致性）

{numbers_text}

---

## 校对参考规则

{rules_text}

---

## 你的任务（按优先级依次完成）

**1. 错别字全面扫描（最重要，不得跳过任何一段）**
   - 机械规则只覆盖约15个固定词对，绝大多数错别字需要你来发现
   - 逐段逐字检查：形近字（如「己」/「已」/「巳」）、音近字、多字、少字
   - 规划专业词必查：容积率、绿地率、建筑密度、用地性质、控制性详细规划等

**2. 数字逻辑核验**
   - 分项合计与总数是否一致（注意嵌套"其中"结构：第二个"其中"是对同一总量的再拆分，不是新增项；"另有X处"是独立补充，不计入前面的合计；"含X处"是附属说明）
   - 同一指标在不同章节数值是否矛盾
   - 百分比计算是否正确

**3. 专业概念检查**
   - 术语含义是否用错（如将高中纳入义务教育）
   - 用地性质代码/名称是否符合上海标准

**4. 语言规范审查**
   - 前后矛盾、口语化表达、主语缺失、标题与内容不符

以 JSON 格式返回所有发现的问题。
""".strip()


def parse_ai_response(response_text: str) -> tuple[list, str]:
    """
    解析 AI 返回的 JSON。

    Returns:
        (issues, summary)  解析失败时返回 ([], "")
    """
    # 提取 JSON 块（AI 有时会包裹在 ```json ... ``` 中）
    text = response_text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        # 尝试直接找最外层 {}
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


# ── 内部工具 ──────────────────────────────────────────────────────

def _load_rules_excerpt() -> str:
    """读取校对规则和常见错误手册，截取关键部分。"""
    excerpts = []
    for fname in ("proofread-rules.md", "common-errors.md"):
        path = REFERENCES_DIR / fname
        if path.exists():
            content = path.read_text(encoding="utf-8")
            # 只取前 2000 字，避免提示词过长
            excerpts.append(content[:2000])
    return "\n\n---\n\n".join(excerpts) if excerpts else "（参考文件未找到）"
