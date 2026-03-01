"""
claude.py - Anthropic Claude API 校对客户端

依赖：pip install anthropic
"""

from __future__ import annotations

from app.config import Config, get_api_key
from app.ai.base import SYSTEM_PROMPT, proofread_chunks


def proofread(
    doc_content: dict,
    numbers: dict,
    typos: list,
) -> tuple[list, str]:
    """
    调用 Claude API 进行深度校对（支持分块，解决超长文本注意力丢失）。

    Returns:
        (issues, summary)
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("请先安装 anthropic 包：pip install anthropic")

    api_key = get_api_key("claude")
    client = anthropic.Anthropic(api_key=api_key)

    def call_api(user_prompt: str) -> str:
        message = client.messages.create(
            model=Config.CLAUDE_MODEL,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.0,          # 校对任务要求最大确定性，禁止发散
        )
        return message.content[0].text if message.content else ""

    return proofread_chunks(doc_content, numbers, typos, call_api, Config.CLAUDE_MAX_CHARS)
