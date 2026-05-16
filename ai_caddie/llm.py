"""Optional LLM wording layer for AI Caddie reports.

Only sanitized `llmBrief` objects are sent to the model. Raw Garmin files,
cookies, tokens, and local paths are not included.
"""

from __future__ import annotations

from typing import Any
import json
import os

DEFAULT_MODEL = os.getenv("AI_CADDIE_MODEL", "claude-sonnet-4-5-20250929")


def prompt_from_brief(brief: dict[str, Any]) -> str:
    return (
        "你是一个高尔夫策略复盘助手。只根据下面 JSON 事实写中文复盘，"
        "不要编造天气、旗位、用户意图或没有给出的挥杆原因。"
        "明确区分：数据/geometry 缺口、执行结果、策略建议。"
        "输出结构：1 总结，2 关键洞/关键杆，3 下次可执行建议，4 还需要的数据。\n\n"
        f"{json.dumps(brief, ensure_ascii=False, indent=2)}"
    )


def call_anthropic(brief: dict[str, Any], *, model: str = DEFAULT_MODEL) -> str:
    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=1800,
        messages=[{"role": "user", "content": prompt_from_brief(brief)}],
    )
    return msg.content[0].text


def maybe_call_anthropic(brief: dict[str, Any]) -> tuple[str | None, str | None]:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None, "ANTHROPIC_API_KEY is not set"
    try:
        return call_anthropic(brief), None
    except Exception as exc:
        return None, str(exc)
