from __future__ import annotations

from typing import Any


def build_oauth_feasibility_status() -> dict[str, Any]:
    return {
        "name": "garmin_oauth_feasibility",
        "state": "not_available",
        "detail": (
            "Official Garmin OAuth is tracked as a replaceable connector path, "
            "but golf scorecard and shot access are not proven for this product yet."
        ),
        "canSync": False,
        "reauthRequired": False,
        "track": "official_oauth",
        "feasibilityQuestions": [
            "Can official OAuth access golf scorecards?",
            "Can official OAuth access golf GPS shot records or FIT golf data?",
            "Can official OAuth expose course or golf activity metadata for history review?",
            "Can official OAuth support identity or a future connector migration if golf data is unavailable?",
        ],
    }
