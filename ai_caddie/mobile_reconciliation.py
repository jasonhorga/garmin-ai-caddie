"""Reconcile offline mobile live events against synced round facts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_caddie.history import HistoryData
from ai_caddie.mobile_live import mobile_event_log


def _event_rows(round_id: str, *, root: Path | str | None = None) -> list[dict[str, Any]]:
    path = mobile_event_log(root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("roundId")) == str(round_id):
            event = row.get("event")
            if isinstance(event, dict):
                rows.append({"serverSequence": row.get("serverSequence"), **event})
    return rows


def _round_row(round_id: str, data: HistoryData) -> dict[str, Any]:
    requested = str(round_id)
    return next(
        (
            row
            for row in data.rounds
            if requested in {str(row.get("id") or ""), *(str(item) for item in (row.get("ids") or []))}
        ),
        {},
    )


def _hole_scores(round_row: dict[str, Any]) -> dict[int, dict[str, Any]]:
    scores: dict[int, dict[str, Any]] = {}
    for index, hole in enumerate(round_row.get("holes") or [], start=1):
        number = int(hole.get("number") or index)
        scores[number] = {
            "strokes": hole.get("strokes"),
            "putts": hole.get("putts"),
            "ref": f"{round_row.get('id')}:{number}",
        }
    return scores


def _shot_facts(round_id: str, data: HistoryData) -> list[dict[str, Any]]:
    per_hole: dict[int, int] = {}
    facts: list[dict[str, Any]] = []
    requested = str(round_id)
    for shot in data.shots:
        if str(shot.get("roundId")) != requested:
            continue
        hole = int(shot.get("hole") or 0)
        per_hole[hole] = per_hole.get(hole, 0) + 1
        facts.append(
            {
                "kind": "club",
                "hole": hole,
                "clubName": shot.get("club"),
                "ref": f"{requested}:{hole}:{per_hole[hole]}",
            }
        )
    return facts


def _candidate_audit(event: dict[str, Any]) -> dict[str, Any] | None:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    decision_id = payload.get("decisionId")
    if not decision_id:
        return None
    return {
        "decisionId": str(decision_id),
        "eventId": event.get("eventId"),
        "roundId": event.get("roundId"),
        "hole": event.get("hole"),
        "kind": event.get("kind"),
        "actualShot": payload.get("actualShot") or payload,
    }


def reconcile_mobile_round_events(
    round_id: str,
    data: HistoryData,
    *,
    root: Path | str | None = None,
) -> dict[str, Any]:
    events = _event_rows(round_id, root=root)
    round_row = _round_row(round_id, data)
    scores = _hole_scores(round_row)
    shots = _shot_facts(round_id, data)
    unmatched_shots = {shot["ref"]: shot for shot in shots}
    matched: list[dict[str, Any]] = []
    local_only: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    candidate_audits: list[dict[str, Any]] = []

    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        kind = str(event.get("kind") or "")
        hole = int(event.get("hole") or 0)
        audit = _candidate_audit(event)
        if audit:
            candidate_audits.append(audit)

        if kind == "score":
            local_value = payload.get("strokes")
            garmin = scores.get(hole)
            garmin_value = garmin.get("strokes") if garmin else None
            if garmin_value is None:
                local_only.append({"eventId": event.get("eventId"), "kind": kind, "hole": hole, "localValue": local_value})
            elif local_value == garmin_value:
                matched.append({"eventId": event.get("eventId"), "kind": kind, "hole": hole, "ref": garmin["ref"]})
            else:
                conflicts.append(
                    {
                        "eventId": event.get("eventId"),
                        "kind": kind,
                        "hole": hole,
                        "localValue": local_value,
                        "garminValue": garmin_value,
                        "ref": garmin["ref"],
                    }
                )
            continue

        if kind == "putt":
            local_value = payload.get("putts")
            garmin = scores.get(hole)
            garmin_value = garmin.get("putts") if garmin else None
            if garmin_value is None:
                local_only.append({"eventId": event.get("eventId"), "kind": kind, "hole": hole, "localValue": local_value})
            elif local_value == garmin_value:
                matched.append({"eventId": event.get("eventId"), "kind": kind, "hole": hole, "ref": garmin["ref"]})
            else:
                conflicts.append(
                    {
                        "eventId": event.get("eventId"),
                        "kind": kind,
                        "hole": hole,
                        "localValue": local_value,
                        "garminValue": garmin_value,
                        "ref": garmin["ref"],
                    }
                )
            continue

        if kind == "club":
            club_name = payload.get("clubName")
            match = next(
                (
                    shot
                    for shot in unmatched_shots.values()
                    if shot.get("hole") == hole and str(shot.get("clubName")) == str(club_name)
                ),
                None,
            )
            if match:
                matched.append({"eventId": event.get("eventId"), "kind": kind, "hole": hole, "ref": match["ref"]})
                unmatched_shots.pop(str(match["ref"]), None)
            else:
                local_only.append({"eventId": event.get("eventId"), "kind": kind, "hole": hole, "localValue": club_name})
            continue

        local_only.append({"eventId": event.get("eventId"), "kind": kind, "hole": hole, "localValue": payload})

    garmin_only = [
        {
            "kind": shot["kind"],
            "hole": shot["hole"],
            "garminValue": shot["clubName"],
            "ref": ref,
        }
        for ref, shot in sorted(unmatched_shots.items())
    ]
    return {
        "schema": "ai-caddie-mobile-reconciliation-v1",
        "roundId": str(round_id),
        "summary": {
            "eventCount": len(events),
            "matchedCount": len(matched),
            "localOnlyCount": len(local_only),
            "garminOnlyCount": len(garmin_only),
            "conflictCount": len(conflicts),
            "candidateDecisionAuditCount": len(candidate_audits),
        },
        "matched": matched,
        "localOnly": local_only,
        "garminOnly": garmin_only,
        "conflicts": conflicts,
        "candidateDecisionAudits": candidate_audits,
    }
