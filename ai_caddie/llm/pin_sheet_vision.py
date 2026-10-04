"""Read a course's daily hole-location sheet (洞位图) into per-hole pin facts.

The sheet is photographed by the player and read by the configured multimodal model. Only facts
printed on the sheet are returned; the app places the flag on its own green geometry
(`PinSheetPlacement` on iOS). Three tiers, best first, may be present for a hole:

* numbers: yards from the green's front-most point along the approach (``fromFrontYd``) and yards
  in from the left / right edge at that depth (``side`` L/R with ``fromSideYd``), or ``side`` C for
  the middle;
* the drawn flag dot as fractions of the drawn green (``dotU`` front→back, ``dotV`` left→right),
  which also disambiguates a concave green;
* a front / middle / back ``zone`` when that is all the sheet says.

A venue of nine-hole loops may number its sheet straight through (1–27) or per loop (A1…A9, or an
"A" section with holes 1–9). A per-loop sheet carries the printed loop label (``loop``) with the
hole number inside that loop, so the app never maps a later loop's 1–9 onto the first loop.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, cast

from ai_caddie.llm.llm_providers import LLMMediaPart, LLMMessage, MultimodalProvider

PIN_SHEET_SCHEMA = "ai-caddie-pin-sheet-v1"
MAX_SHEET_HOLE = 36
MAX_YARDS = 80
MAX_LOOP_LABEL = 12

_SYSTEM = (
    "You read golf hole-location sheets (pin sheets). Report only what is printed; never guess a "
    "number that is not on the sheet. Answer with one JSON object and nothing else."
)

_PROMPT = """This photo shows a golf course's daily hole-location sheet (洞位图 / Hole Locations).
Each box is one hole: a header like "Hole 20 | 40,6R", a drawing of the green with a flag dot, and
usually a red number for the green's depth. The tee/approach is marked "T" at the bottom of each box.

Conventions of the header pair "A,B<side>":
- A = yards from the green's FRONT-MOST point, measured along the approach (bottom → top).
- B = yards from the flag to the green edge on <side> (L = left edge, R = right edge), measured
  straight across at the flag's depth. "22C" means 22 yards deep on the centre line.

Hole numbering: if the sheet numbers holes straight through (1, 2, … 27), give that number and
"loop": null. If it numbers per loop or course (A1…A9, B1…, or a section titled "A" / "A场" /
"East" with holes 1–9), give the loop label as printed in "loop" (e.g. "A") and the hole number
inside that loop in "hole".

Give "date" only when a full date (with the year) is printed; otherwise null.

Return JSON exactly in this shape:
{"date": "YYYY-MM-DD" or null,
 "holes": [{"loop": <string or null>,
            "hole": <int as printed>,
            "fromFrontYd": <int or null>,
            "side": "L" | "R" | "C" | null,
            "fromSideYd": <int or null>,
            "depthYd": <int or null, the red green-depth number>,
            "dotU": <0..1 or null, flag dot position from the drawn green's front (0) to back (1)>,
            "dotV": <0..1 or null, flag dot position from the drawn green's left (0) to right (1)>,
            "zone": "front" | "middle" | "back" | null}]}

Include every hole box you can see, across all photos. If a sheet has no numbers, still give dotU /
dotV from the drawing, or a zone if that is all it states. Use null for anything not shown."""


class PinSheetReadError(RuntimeError):
    """The model reply could not be turned into any usable pin."""


@dataclass(frozen=True)
class PinSheetImage:
    mime_type: str
    data: bytes


def read_pin_sheet(images: Iterable[PinSheetImage], provider: object) -> dict[str, Any]:
    """Ask the multimodal provider to read the sheet and return the normalised payload."""
    chat_multimodal = getattr(provider, "chat_multimodal", None)
    if not callable(chat_multimodal):
        raise PinSheetReadError("the configured model cannot read images")
    media = [LLMMediaPart(media_type="image", mime_type=image.mime_type, data=image.data) for image in images]
    if not media:
        raise PinSheetReadError("no image")
    reply = cast(MultimodalProvider, provider).chat_multimodal(
        [LLMMessage("system", _SYSTEM), LLMMessage("user", _PROMPT)],
        media,
        max_tokens=4000,
    )
    return parse_pin_sheet_reply(reply)


def parse_pin_sheet_reply(reply: str) -> dict[str, Any]:
    """Normalise a model reply: strip code fences, validate every field, drop unusable holes."""
    root = _json_object(reply)
    rows = root.get("holes")
    if not isinstance(rows, list):
        raise PinSheetReadError("the reply has no holes")
    # One row per (loop, hole): the same box seen in two overlapping photos keeps its first read,
    # while A1 and B1 stay distinct holes.
    holes: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        normalised = _hole(row)
        if normalised is None:
            continue
        key = (normalised["loop"] or "", normalised["hole"])
        if key not in holes:
            holes[key] = normalised
    if not holes:
        raise PinSheetReadError("no hole on the sheet has a usable flag position")
    labelled = {loop for loop, _ in holes if loop}
    if labelled and any(not loop for loop, _ in holes):
        raise PinSheetReadError("the sheet mixes per-loop and straight-through hole numbers")
    if labelled and any(number > 18 for _, number in holes):
        raise PinSheetReadError("a per-loop hole number is out of range")
    return {
        "schema": PIN_SHEET_SCHEMA,
        "date": _date(root.get("date")),
        "holes": [holes[key] for key in sorted(holes)],
    }


def _json_object(reply: str) -> dict[str, Any]:
    text = (reply or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise PinSheetReadError("the reply is not JSON")
    try:
        root = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise PinSheetReadError("the reply is not valid JSON") from exc
    if not isinstance(root, dict):
        raise PinSheetReadError("the reply is not a JSON object")
    return root


def _hole(row: object) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    number = _int(row.get("hole"), 1, MAX_SHEET_HOLE)
    if number is None:
        return None
    from_front = _int(row.get("fromFrontYd"), 0, MAX_YARDS)
    side = row.get("side")
    side = side.strip().upper() if isinstance(side, str) else None
    if side not in {"L", "R", "C"}:
        side = None
    from_side = _int(row.get("fromSideYd"), 0, MAX_YARDS) if side in {"L", "R"} else None
    # A numeric position needs its depth and, off the centre line, its side distance.
    has_numbers = from_front is not None and (side == "C" or (side in {"L", "R"} and from_side is not None))
    dot_u = _fraction(row.get("dotU"))
    dot_v = _fraction(row.get("dotV"))
    has_dot = dot_u is not None and dot_v is not None
    zone = row.get("zone")
    zone = zone.strip().lower() if isinstance(zone, str) else None
    if zone not in {"front", "middle", "back"}:
        zone = None
    if not (has_numbers or has_dot or zone):
        return None
    return {
        "loop": _loop(row.get("loop")),
        "hole": number,
        "fromFrontYd": from_front if has_numbers else None,
        "side": side if has_numbers else None,
        "fromSideYd": from_side if has_numbers else None,
        "depthYd": _int(row.get("depthYd"), 1, MAX_YARDS),
        "dotU": dot_u if has_dot else None,
        "dotV": dot_v if has_dot else None,
        "zone": zone,
    }


def _loop(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    label = value.strip().upper()
    if not label or len(label) > MAX_LOOP_LABEL or label in {"NULL", "NONE"}:
        return None
    return label


def _int(value: object, low: int, high: int) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not re.fullmatch(r"\d+(\.\d+)?", value):
            return None
        value = float(value)
    if not isinstance(value, (int, float)):
        return None
    number = int(round(float(value)))
    return number if low <= number <= high else None


def _fraction(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return round(number, 3) if 0.0 <= number <= 1.0 else None


def _date(value: object) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return None
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return None
