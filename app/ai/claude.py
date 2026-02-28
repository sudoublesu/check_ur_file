"""
claude.py - Anthropic Claude API 校对客户端

依赖：pip install anthropic
"""

from __future__ import annotations

from app.config import Config, get_api_key
from app.ai.base import SYSTEM_PROMPT, build_user_prompt, parse_ai_response


def proofread(
    doc_content: dict,
    numbers: dict,
    typos: list,
) -> tuple[list, str]:
    """
    调用 Claude API 进行深度校对。

    Returns:
        (issues, summary)
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "请先安装 anthropic 包：pip install anthropic"
        )

    api_key = get_api_key("claude")

    user_prompt = build_user_prompt(
        doc_content,
        numbers,
        typos,
        max_chars=Config.CLAUDE_MAX_CHARS,
    )

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    raw = message.content[0].text if message.content else ""
    issues, summary = parse_ai_response(raw)
    return issues, summary
