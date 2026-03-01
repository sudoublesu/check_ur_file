"""
gemini.py - Google Gemini API 校对客户端

使用 google-generativeai 包。
依赖：pip install google-generativeai
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
    调用 Gemini API 进行深度校对（支持分块，解决超长文本注意力丢失）。

    Returns:
        (issues, summary)
    """
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError("请先安装 google-generativeai 包：pip install google-generativeai")

    api_key = get_api_key("gemini")
    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(
        model_name=Config.GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
        generation_config=genai.types.GenerationConfig(
            temperature=0.0,          # 校对任务要求最大确定性，禁止发散
            response_mime_type="application/json",
            max_output_tokens=8192,
        ),
    )

    def call_api(user_prompt: str) -> str:
        response = model.generate_content(user_prompt)
        return response.text or ""

    return proofread_chunks(doc_content, numbers, typos, call_api, Config.GEMINI_MAX_CHARS)
