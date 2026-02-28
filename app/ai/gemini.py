"""
gemini.py - Google Gemini API 校对客户端

使用 google-generativeai 包。
依赖：pip install google-generativeai
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
    调用 Gemini API 进行深度校对。

    Returns:
        (issues, summary)
    """
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError(
            "请先安装 google-generativeai 包：pip install google-generativeai"
        )

    api_key = get_api_key("gemini")
    genai.configure(api_key=api_key)

    user_prompt = build_user_prompt(
        doc_content,
        numbers,
        typos,
        max_chars=Config.GEMINI_MAX_CHARS,  # Gemini 支持更长上下文
    )

    model = genai.GenerativeModel(
        model_name=Config.GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
        generation_config=genai.types.GenerationConfig(
            temperature=0.2,
            response_mime_type="application/json",
            max_output_tokens=4096,
        ),
    )

    response = model.generate_content(user_prompt)
    raw = response.text or ""
    issues, summary = parse_ai_response(raw)
    return issues, summary
