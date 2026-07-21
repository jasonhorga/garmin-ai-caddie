"""Reconcile offline mobile live events against synced round facts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_caddie.reports.annotations import add_annotation, list_annotations
from ai_caddie.caddie.decision import audit_decision, store_decision_audit
from ai_caddie.caddie.mobile_event_store import FileEventStore
from ai_caddie.history.history import HistoryData, OWNER_ID
from ai_caddie.caddie.mobile_live import mobile_event_log


def _event_rows(round_id: str, *, root: Path | str | None = None, player_id: str = OWNER_ID) -> list[dict[str, Any]]:
    # The mobile event log is per-player partitioned (mobile_live.mobile_event_log): the owner keeps
    # the flat shared log; a member's live events live under their own partition. Read the ACTING
    # player's log so a member's reconciliation sees THEIR own offline activity (and an owner sees
    # only the owner's) — never another player's. mobile_event_log applies the per-player path
    # itself, so pass player_id here (NOT a pre-resolved evidence_root, which would double-nest the
    # path to data/players/<id>/data/mobile_events/... and read empty).
    path = mobile_event_log(root, player_id=player_id)
    rows: list[dict[str, Any]] = []
    for row in FileEventStore(path.parent).read_rows(round_id):
        event = row.get("event")
        if isinstance(event, dict):
            rows.append({**event, "serverSequence": row.get("serverSequence")})
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
        shot_round_id = shot.get("roundId")
        if shot_round_id is None:
            shot_round_id = shot.get("scorecardId")
        if str(shot_round_id) != requested:
            continue
        hole = int(shot.get("hole") or 0)
        per_hole[hole] = per_hole.get(hole, 0) + 1
        facts.append(
            {
                "kind": "club",
                "hole": hole,
                "clubName": shot.get("club") or shot.get("clubName"),
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


def _payload_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _non_empty_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _media_context_row(event: dict[str, Any], payload: dict[str, Any], *, kind: str, hole: int) -> dict[str, Any]:
    media_type = str(payload.get("mediaType") or kind)
    media_id = _non_empty_text(payload.get("mediaId"))
    note = _payload_value(payload, "note", "text")
    local_value = media_id or media_type
    row: dict[str, Any] = {
        "eventId": event.get("eventId"),
        "roundId": event.get("roundId"),
        "kind": kind,
        "hole": hole,
        "localValue": str(local_value),
        "mediaType": media_type,
    }
    if media_id:
        row["mediaId"] = media_id
    else:
        row["mediaState"] = "missing_media_id"
    if note:
        row["note"] = str(note).strip()
    duration_s = payload.get("durationS")
    if duration_s is not None:
        row["durationS"] = duration_s
    return row


def _suggestion(
    suggestion_id: str,
    *,
    target_type: str,
    target_id: str,
    kind: str,
    payload: dict[str, Any],
    reason: str,
    confidence: str = "medium",
) -> dict[str, Any]:
    return {
        "id": suggestion_id,
        "targetType": target_type,
        "targetId": target_id,
        "kind": kind,
        "payload": {
            **payload,
            "source": "mobile_reconciliation",
            "sourceSuggestionId": suggestion_id,
        },
        "reason": reason,
        "confidence": confidence,
    }


def _annotation_suggestions(
    *,
    conflicts: list[dict[str, Any]],
    local_only: list[dict[str, Any]],
    garmin_only: list[dict[str, Any]],
    candidate_audits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for conflict in conflicts:
        event_id = str(conflict.get("eventId") or "")
        kind = str(conflict.get("kind") or "")
        ref = str(conflict.get("ref") or "")
        local_value = conflict.get("localValue")
        garmin_value = conflict.get("garminValue")
        if not event_id or not ref:
            continue
        if kind == "putt":
            suggestions.append(
                _suggestion(
                    f"{event_id}:putt-correction",
                    target_type="hole",
                    target_id=ref,
                    kind="putt_correction",
                    payload={"from": garmin_value, "to": local_value, "sourceEventId": event_id},
                    reason="Local putting input differs from the synced Garmin scorecard.",
                )
            )
        elif kind == "score":
            suggestions.append(
                _suggestion(
                    f"{event_id}:score-correction",
                    target_type="hole",
                    target_id=ref,
                    kind="score_correction",
                    payload={
                        "from": garmin_value,
                        "to": local_value,
                        "sourceEventId": event_id,
                    },
                    reason="Local score input can correct the derived score for this hole.",
                )
            )

    garmin_shots_by_hole: dict[int, list[dict[str, Any]]] = {}
    for row in garmin_only:
        if row.get("kind") != "club":
            continue
        hole = int(row.get("hole") or 0)
        garmin_shots_by_hole.setdefault(hole, []).append(row)

    for row in local_only:
        event_id = str(row.get("eventId") or "")
        kind = str(row.get("kind") or "")
        hole = int(row.get("hole") or 0)
        local_value = row.get("localValue")
        if not event_id:
            continue
        if kind == "score":
            if local_value is None:
                continue
            suggestions.append(
                _suggestion(
                    f"{event_id}:score-correction",
                    target_type="hole",
                    target_id=f"{row.get('roundId') or ''}:{hole}",
                    kind="score_correction",
                    payload={"from": None, "to": local_value, "sourceEventId": event_id},
                    reason="Local score input fills a hole missing from synced Garmin facts.",
                )
            )
        elif kind == "putt":
            if local_value is None:
                continue
            suggestions.append(
                _suggestion(
                    f"{event_id}:putt-correction",
                    target_type="hole",
                    target_id=f"{row.get('roundId') or ''}:{hole}",
                    kind="putt_correction",
                    payload={"from": None, "to": local_value, "sourceEventId": event_id},
                    reason="Local putt input fills a hole missing from synced Garmin facts.",
                )
            )
        elif kind == "club":
            candidates = garmin_shots_by_hole.get(hole) or []
            if candidates:
                garmin = candidates.pop(0)
                suggestions.append(
                    _suggestion(
                        f"{event_id}:club-correction",
                        target_type="shot",
                        target_id=str(garmin.get("ref") or ""),
                        kind="club_correction",
                        payload={"from": garmin.get("garminValue"), "to": local_value, "sourceEventId": event_id},
                        reason="Local club input can correct the nearest unmatched Garmin shot on the same hole.",
                    )
                )
        elif kind == "penalty":
            suggestions.append(
                _suggestion(
                    f"{event_id}:penalty-correction",
                    target_type="hole",
                    target_id=f"{row.get('roundId') or ''}:{hole}",
                    kind="penalty_correction",
                    payload={"strokes": local_value, "sourceEventId": event_id},
                    reason="Local penalty marker was not present in synced Garmin facts.",
                )
            )
        elif kind == "note":
            note_text = str(local_value or "").strip()
            if note_text:
                suggestions.append(
                    _suggestion(
                        f"{event_id}:hole-note",
                        target_type="hole",
                        target_id=f"{row.get('roundId') or ''}:{hole}",
                        kind="hole_note",
                        payload={"text": note_text, "sourceEventId": event_id},
                        reason="Local mobile note can be preserved as an auditable hole note.",
                    )
                )
        elif kind in {"photo", "video"}:
            media_type = str(row.get("mediaType") or kind)
            media_id = _non_empty_text(row.get("mediaId"))
            if not media_id:
                continue
            suggestion_id = f"{event_id}:media-context"
            payload: dict[str, Any] = {
                "mediaType": media_type,
                "sourceEventId": event_id,
            }
            payload["mediaId"] = media_id
            note = str(row.get("note") or "").strip()
            if note:
                payload["text"] = note
            if row.get("durationS") is not None:
                payload["durationS"] = row["durationS"]
            suggestions.append(
                _suggestion(
                    suggestion_id,
                    target_type="hole",
                    target_id=f"{row.get('roundId') or ''}:{hole}",
                    kind="hole_note",
                    payload=payload,
                    reason=f"Offline {media_type} context can be preserved as auditable media evidence for this hole.",
                    confidence="medium",
                )
            )

    for audit in candidate_audits:
        event_id = str(audit.get("eventId") or "")
        decision_id = str(audit.get("decisionId") or "")
        if not event_id or not decision_id:
            continue
        suggestions.append(
            _suggestion(
                f"{event_id}:caddie-feedback",
                target_type="decision",
                target_id=decision_id,
                kind="caddie_feedback",
                payload={
                    "decisionId": decision_id,
                    "actualShot": audit.get("actualShot"),
                    "sourceEventId": event_id,
                },
                reason="Offline live event includes an actual shot that can audit this caddie decision.",
            )
        )

    return [row for row in suggestions if row.get("targetId")]


def reconcile_mobile_round_events(
    round_id: str,
    data: HistoryData,
    *,
    root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> dict[str, Any]:
    events = _event_rows(round_id, root=root, player_id=player_id)
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
            local_value = _payload_value(payload, "strokes", "score")
            garmin = scores.get(hole)
            garmin_value = garmin.get("strokes") if garmin else None
            if garmin_value is None:
                local_only.append(
                    {
                        "eventId": event.get("eventId"),
                        "roundId": event.get("roundId"),
                        "kind": kind,
                        "hole": hole,
                        "localValue": local_value,
                    }
                )
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
            local_value = _payload_value(payload, "putts", "count")
            garmin = scores.get(hole)
            garmin_value = garmin.get("putts") if garmin else None
            if garmin_value is None:
                local_only.append(
                    {
                        "eventId": event.get("eventId"),
                        "roundId": event.get("roundId"),
                        "kind": kind,
                        "hole": hole,
                        "localValue": local_value,
                    }
                )
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

        if kind == "penalty":
            local_value = _payload_value(payload, "penalties", "count")
            local_only.append(
                {
                    "eventId": event.get("eventId"),
                    "roundId": event.get("roundId"),
                    "kind": kind,
                    "hole": hole,
                    "localValue": local_value,
                }
            )
            continue

        if kind == "note":
            local_value = _payload_value(payload, "note", "text")
            local_only.append(
                {
                    "eventId": event.get("eventId"),
                    "roundId": event.get("roundId"),
                    "kind": kind,
                    "hole": hole,
                    "localValue": local_value,
                }
            )
            continue

        if kind == "club":
            club_name = _payload_value(payload, "clubName", "club")
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
                local_only.append(
                    {
                        "eventId": event.get("eventId"),
                        "roundId": event.get("roundId"),
                        "kind": kind,
                        "hole": hole,
                        "localValue": club_name,
                }
            )
            continue

        if kind in {"photo", "video"}:
            local_only.append(_media_context_row(event, payload, kind=kind, hole=hole))
            continue

        local_only.append(
            {
                "eventId": event.get("eventId"),
                "roundId": event.get("roundId"),
                "kind": kind,
                "hole": hole,
                "localValue": payload,
            }
        )

    garmin_only = [
        {
            "kind": shot["kind"],
            "hole": shot["hole"],
            "garminValue": shot["clubName"],
            "ref": ref,
        }
        for ref, shot in sorted(unmatched_shots.items())
    ]
    annotation_suggestions = _annotation_suggestions(
        conflicts=conflicts,
        local_only=local_only,
        garmin_only=garmin_only,
        candidate_audits=candidate_audits,
    )
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
            "annotationSuggestionCount": len(annotation_suggestions),
        },
        "matched": matched,
        "localOnly": local_only,
        "garminOnly": garmin_only,
        "conflicts": conflicts,
        "candidateDecisionAudits": candidate_audits,
        "annotationSuggestions": annotation_suggestions,
    }


def _existing_source_suggestion_ids(*, root: Path | str | None = None, player_id: str = OWNER_ID) -> set[str]:
    ids: set[str] = set()
    for record in list_annotations(root=root, player_id=player_id):
        payload = record.get("payload")
        if isinstance(payload, dict) and payload.get("sourceSuggestionId"):
            ids.add(str(payload["sourceSuggestionId"]))
    return ids


def apply_mobile_reconciliation_suggestions(
    round_id: str,
    data: HistoryData,
    *,
    suggestion_ids: list[str] | None = None,
    root: Path | str | None = None,
    annotations_root: Path | str | None = None,
    decision_audit_root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> dict[str, Any]:
    reconciliation = reconcile_mobile_round_events(round_id, data, root=root, player_id=player_id)
    suggestions = {str(row.get("id")): row for row in reconciliation.get("annotationSuggestions", [])}
    requested_ids = list(suggestion_ids or suggestions.keys())
    existing_ids = _existing_source_suggestion_ids(root=annotations_root, player_id=player_id)
    events_by_id = {str(row.get("eventId")): row for row in _event_rows(round_id, root=root, player_id=player_id) if row.get("eventId")}
    annotations: list[dict[str, Any]] = []
    decision_audits: list[dict[str, Any]] = []
    skipped: list[str] = []
    missing: list[str] = []

    for suggestion_id in requested_ids:
        row = suggestions.get(str(suggestion_id))
        if not row:
            missing.append(str(suggestion_id))
            continue
        if str(suggestion_id) in existing_ids:
            skipped.append(str(suggestion_id))
            continue
        payload = dict(row.get("payload") or {})
        record = add_annotation(
            str(row["targetType"]),
            str(row["targetId"]),
            str(row["kind"]),
            payload,
            root=annotations_root,
            player_id=player_id,
        )
        annotations.append(record)
        existing_ids.add(str(suggestion_id))
        audit_record = _store_caddie_feedback_audit(
            row,
            events_by_id=events_by_id,
            root=decision_audit_root,
            player_id=player_id,
        )
        if audit_record:
            decision_audits.append(audit_record)

    return {
        "schema": "ai-caddie-mobile-reconciliation-apply-v1",
        "roundId": str(round_id),
        "appliedCount": len(annotations),
        "decisionAuditCount": len(decision_audits),
        "skippedCount": len(skipped),
        "missingSuggestionIds": missing,
        "skippedSuggestionIds": skipped,
        "annotations": annotations,
        "decisionAudits": decision_audits,
    }


def _store_caddie_feedback_audit(
    suggestion: dict[str, Any],
    *,
    events_by_id: dict[str, dict[str, Any]],
    root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> dict[str, Any] | None:
    if suggestion.get("kind") != "caddie_feedback":
        return None
    payload = suggestion.get("payload") if isinstance(suggestion.get("payload"), dict) else {}
    event_id = str(payload.get("sourceEventId") or "")
    event_payload = events_by_id.get(event_id, {}).get("payload")
    if not isinstance(event_payload, dict):
        return None
    decision = event_payload.get("decision")
    if not isinstance(decision, dict):
        return None
    actual_shot = payload.get("actualShot")
    if not isinstance(actual_shot, dict):
        actual_shot = event_payload.get("actualShot")
    audit = audit_decision(decision, actual_shot if isinstance(actual_shot, dict) else None)
    return store_decision_audit(audit, decision_id=str(payload.get("decisionId") or suggestion.get("targetId") or ""), root=root, player_id=player_id)
