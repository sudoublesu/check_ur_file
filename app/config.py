"""
config.py - API Key 及模型配置

从环境变量或项目根目录的 .env 文件读取配置。
"""

import os
from pathlib import Path

# ── 尝试加载 .env 文件（不强依赖 python-dotenv）─────────────────────
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


# ── 配置项 ──────────────────────────────────────────────────────────

class Config:
    # DeepSeek
    DEEPSEEK_API_KEY: str  = os.environ.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL: str    = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # Gemini
    # 默认使用 Pro 系列以获得最佳校对深度；如需加速可在 .env 中改为 gemini-2.0-flash
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL: str   = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro-preview-03-25")

    # Claude
    # 默认使用 Opus 以获得最佳推理能力；如需降低成本可在 .env 中改为 claude-sonnet-4-6
    CLAUDE_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str   = os.environ.get("CLAUDE_MODEL", "claude-opus-4-6")

    # 文档截断长度（字符数），控制发给 AI 的内容量
    DEEPSEEK_MAX_CHARS: int = 40_000
    GEMINI_MAX_CHARS: int   = 120_000
    CLAUDE_MAX_CHARS: int   = 80_000


def get_api_key(provider: str) -> str:
    """获取 API Key，未配置时抛出清晰错误。"""
    if provider == "deepseek":
        key = Config.DEEPSEEK_API_KEY
        if not key:
            raise EnvironmentError(
                "未配置 DEEPSEEK_API_KEY。\n"
                "请在项目根目录创建 .env 文件，写入：\n"
                "  DEEPSEEK_API_KEY=sk-xxxx"
            )
        return key
    if provider == "gemini":
        key = Config.GEMINI_API_KEY
        if not key:
            raise EnvironmentError(
                "未配置 GEMINI_API_KEY。\n"
                "请在项目根目录创建 .env 文件，写入：\n"
                "  GEMINI_API_KEY=AIzaSy-xxxx"
            )
        return key
    if provider == "claude":
        key = Config.CLAUDE_API_KEY
        if not key:
            raise EnvironmentError(
                "未配置 ANTHROPIC_API_KEY。\n"
                "请在项目根目录创建 .env 文件，写入：\n"
                "  ANTHROPIC_API_KEY=sk-ant-xxxx"
            )
        return key
    raise ValueError(f"未知的 AI 提供方：{provider}")
