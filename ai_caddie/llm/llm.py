"""Optional LLM wording layer for AI Caddie reports.

Only sanitized `llmBrief` objects are sent to the model. Raw Garmin files,
cookies, tokens, and local paths are not included.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ai_caddie.llm.llm_providers import AnthropicProvider, LLMMessage, TextProvider, build_text_provider, redact_secret_text

DEFAULT_MODEL = os.getenv("AI_CADDIE_MODEL", "claude-sonnet-4-5-20250929")


def prompt_from_brief(brief: dict[str, Any]) -> str:
    return (
        "你是一个高尔夫策略复盘助手。只根据下面 JSON 事实写中文复盘，"
        "不要编造天气、旗位、用户意图或没有给出的挥杆原因。"
        "明确区分：数据/geometry 缺口、执行结果、策略建议。"
        "输出结构：1 总结，2 关键洞/关键杆，3 下次可执行建议，4 还需要的数据。\n\n"
        f"{json.dumps(brief, ensure_ascii=False, indent=2)}"
    )


def call_llm(brief: dict[str, Any], *, provider: TextProvider | None = None, max_tokens: int = 1800) -> str:
    selected = provider or build_text_provider()
    return selected.chat(
        [
            LLMMessage(
                role="system",
                content="Use only the supplied AI Caddie facts. Do not infer private data or missing context.",
            ),
            LLMMessage(role="user", content=prompt_from_brief(brief)),
        ],
        max_tokens=max_tokens,
    )


def maybe_call_llm(brief: dict[str, Any]) -> tuple[str | None, str | None]:
    try:
        return call_llm(brief), None
    except Exception as exc:
        return None, redact_secret_text(exc)


def call_anthropic(brief: dict[str, Any], *, model: str = DEFAULT_MODEL) -> str:
    return call_llm(
        brief,
        provider=AnthropicProvider(
            api_key_present=bool(os.getenv("ANTHROPIC_API_KEY")),
            model=model,
        ),
    )


def maybe_call_anthropic(brief: dict[str, Any]) -> tuple[str | None, str | None]:
    return maybe_call_llm(brief)
