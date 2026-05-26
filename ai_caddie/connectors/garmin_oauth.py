from __future__ import annotations

from typing import Any


def _capability_matrix() -> list[dict[str, Any]]:
    return [
        {
            "key": "scorecards",
            "label": "Golf scorecards",
            "state": "unproven",
            "evidence": "Official Garmin OAuth access to golf scorecard records is not documented for this build.",
            "nextStep": "Verify whether the developer program can read golf scorecard records for a consented account.",
            "canReplaceCnConnector": False,
            "migrationValue": True,
        },
        {
            "key": "golf_shots",
            "label": "Golf GPS shots",
            "state": "unproven",
            "evidence": "The public OAuth track has not proven access to Garmin Golf GPS shot records.",
            "nextStep": "Probe whether activity details or golf-specific endpoints expose shot coordinates and club metadata.",
            "canReplaceCnConnector": False,
            "migrationValue": True,
        },
        {
            "key": "fit_golf_activity",
            "label": "FIT golf activity",
            "state": "unproven",
            "evidence": "FIT download availability for golf score and shot payloads is not confirmed through official OAuth.",
            "nextStep": "Test whether OAuth-authorized activity export includes golf FIT files with scorecard or shot fields.",
            "canReplaceCnConnector": False,
            "migrationValue": True,
        },
        {
            "key": "course_metadata",
            "label": "Course metadata",
            "state": "unproven",
            "evidence": "Course identity and geometry metadata access is not proven through official OAuth.",
            "nextStep": "Check whether official activity metadata includes stable course identifiers or hole context.",
            "canReplaceCnConnector": False,
            "migrationValue": True,
        },
        {
            "key": "identity",
            "label": "Identity",
            "state": "possible",
            "evidence": "OAuth can still be useful for account identity or future migration even if golf data is unavailable.",
            "nextStep": "Keep connector interfaces replaceable so identity-only OAuth can coexist with CN Web Session sync.",
            "canReplaceCnConnector": False,
            "migrationValue": True,
        },
    ]


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
        "capabilities": _capability_matrix(),
    }
