"""
deepseek.py - DeepSeek API 校对客户端

DeepSeek 的 API 与 OpenAI 完全兼容，使用 openai 包调用。
依赖：pip install openai
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
    调用 DeepSeek API 进行深度校对。

    Returns:
        (issues, summary)
        issues: list of dicts with keys para_index / comment / severity / matched / source
        summary: 文件整体评估一句话
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "请先安装 openai 包：pip install openai"
        )

    api_key = get_api_key("deepseek")

    user_prompt = build_user_prompt(
        doc_content,
        numbers,
        typos,
        max_chars=Config.DEEPSEEK_MAX_CHARS,
    )

    client = OpenAI(
        api_key=api_key,
        base_url=Config.DEEPSEEK_BASE_URL,
    )

    response = client.chat.completions.create(
        model=Config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.2,          # 低温度保证输出稳定
        response_format={"type": "json_object"},
        max_tokens=4096,
    )

    raw = response.choices[0].message.content or ""
    issues, summary = parse_ai_response(raw)
    return issues, summary
