import Foundation

public final class OfflineCaddieDecisionEvaluator {
    public init() {}

    public func selectedOption(
        in seed: CaddieContextSeed,
        strategyMode: String?,
        requestedOptionId: String? = nil
    ) -> OfflineCaddieOption? {
        let requested = requestedOptionId?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "-", with: "_")
        let preferredId = requested.flatMap { id in
            seed.offlineOptions.first(where: {
                $0.optionId.trimmingCharacters(in: .whitespacesAndNewlines)
                    .lowercased()
                    .replacingOccurrences(of: "-", with: "_") == id
            })?.optionId
        } ?? preferredOptionId(for: strategyMode) ?? seed.selectedOfflineOptionId
        if let preferredId,
           let option = seed.offlineOptions.first(where: { $0.optionId == preferredId }) {
            return option
        }
        return seed.offlineOptions.first
    }

    public func makeDecision(
        seed: CaddieContextSeed,
        request: CaddieDecisionRequest,
        strategyMode: String?
    ) -> CaddieDecisionResponse? {
        let requestedOptionId: String? = {
            guard case .string(let raw) = request.context["requestedOptionId"] else { return nil }
            return raw
        }()
        guard let selected = selectedOption(
            in: seed,
            strategyMode: strategyMode,
            requestedOptionId: requestedOptionId
        ) else {
            return nil
        }
        let canonicalSteps = canonicalPlanSteps(from: request.context) ?? canonicalPlanSteps(from: seed.context)
        let canonicalFirst = canonicalSteps?.first
        let optionRows = seed.offlineOptions.map { option in
            optionPayload(
                option,
                canonicalFirstStep: option.optionId == "stock" ? canonicalFirst : nil
            )
        }
        let selectedRow = optionPayload(
            selected,
            canonicalFirstStep: selected.optionId == "stock" ? canonicalFirst : nil
        )
        let canonicalSequence = canonicalSteps.flatMap {
            canonicalSequencePayload(steps: $0, selected: selected.optionId == "stock")
        }
        let evidenceRefs = uniqueRefs([seed.sourceRef] + selected.sourceRefs + (selected.sampleRefs ?? []))
        let missingData = seed.missingData + (selected.missingData ?? [])
        let decisionId = offlineDecisionId(seed: seed, request: request, selected: selected)

        return CaddieDecisionResponse(
            schema: "ai-caddie-decision-v2",
            decisionId: decisionId,
            sourceRef: seed.sourceRef,
            evidenceRefs: evidenceRefs,
            shotType: request.shotType,
            phase: phase(for: request.shotType),
            context: request.context,
            options: optionRows,
            selected: selectedRow,
            selectedOptionId: selected.optionId,
            selectedOption: selectedRow,
            sequences: canonicalSequence.map { [$0] },
            selectedSequence: canonicalSequence,
            avoidZones: [],
            forbiddenZones: [],
            acceptableMiss: [
                "target": .string("offline_seed"),
                "note": .string("Use the cached plan and avoid escalating risk without fresh geometry, wind, or lie evidence."),
            ],
            evidence: offlineEvidence(seed: seed, selected: selected),
            confidence: confidencePayload(selected),
            missingData: missingData,
            auditCriteria: auditCriteria(seed: seed, selected: selected)
        )
    }

    private func preferredOptionId(for strategyMode: String?) -> String? {
        switch strategyMode {
        case "protect_score":
            return "safe"
        case "attack":
            return "attack"
        case "stock":
            return "stock"
        default:
            return nil
        }
    }

    private func optionPayload(
        _ option: OfflineCaddieOption,
        canonicalFirstStep: [String: JSONValue]? = nil
    ) -> [String: JSONValue] {
        let canonicalName = canonicalFirstStep.flatMap { string($0["clubName"] ?? $0["club"]) }
        let clubName = canonicalName ?? option.clubName
        let carry = canonicalFirstStep.flatMap { number($0["targetCarry_m"] ?? $0["targetCarryM"]) }
            ?? option.carryM
        var clubRow: [String: JSONValue] = [
            "clubName": .string(clubName),
            "median_m": .number(carry),
            "p10_m": jsonNumberOrNull(option.p10M),
            "p90_m": jsonNumberOrNull(option.p90M),
            "sampleSize": .number(Double(option.sampleSize ?? 0)),
            "confidence": .string(option.confidence ?? "low"),
            "sourceRefs": .array(option.sourceRefs.map { .string($0) }),
        ]
        if let canonicalFirstStep {
            clubRow["planIndex"] = canonicalFirstStep["planIndex"] ?? .number(0)
        }
        var row: [String: JSONValue] = [
            "id": .string(option.optionId),
            "label": .string(option.label),
            "clubName": .string(clubName),
            "carryM": .number(carry),
            "carry_m": .number(carry),
            "riskScore": .number(option.riskScore),
            "source": .string(option.source),
            "sourceRefs": .array(option.sourceRefs.map { .string($0) }),
            "clubRecommendation": .object([
                "source": canonicalFirstStep == nil ? .string(option.source) : .string("course_prep"),
                "clubs": .array([.object(clubRow)])
            ]),
        ]
        if let p10M = option.p10M {
            row["p10M"] = .number(p10M)
        }
        if let p90M = option.p90M {
            row["p90M"] = .number(p90M)
        }
        if let sampleSize = option.sampleSize {
            row["sampleSize"] = .number(Double(sampleSize))
        }
        if let confidence = option.confidence {
            row["confidence"] = .string(confidence)
        }
        if let coverage = option.coverage {
            row["coverage"] = coveragePayload(coverage)
        }
        if let sampleRefs = option.sampleRefs {
            row["sampleRefs"] = .array(sampleRefs.map { .string($0) })
        }
        if let missingData = option.missingData {
            row["missingData"] = .array(missingData.map { .object($0) })
        }
        return row
    }

    private func canonicalPlanSteps(
        from context: [String: JSONValue]
    ) -> [[String: JSONValue]]? {
        guard case .array(let values) = context["canonicalShotPlan"] else { return nil }
        let rows = values.compactMap { value -> [String: JSONValue]? in
            guard case .object(let row) = value,
                  let rawName = string(row["clubName"] ?? row["club"]),
                  !rawName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                return nil
            }
            return row
        }
        return rows.isEmpty ? nil : rows
    }

    private func canonicalSequencePayload(
        steps: [[String: JSONValue]],
        selected: Bool
    ) -> [String: JSONValue]? {
        guard selected, !steps.isEmpty else { return nil }
        let clubs: [JSONValue] = steps.enumerated().compactMap { index, raw in
            guard let name = string(raw["clubName"] ?? raw["club"]) else { return nil }
            var row: [String: JSONValue] = [
                "clubName": .string(name),
                "role": raw["role"] ?? .string(index == 0 ? "advance" : "position"),
                "planIndex": raw["planIndex"] ?? .number(Double(index)),
            ]
            for key in [
                "targetCarry_m", "targetCarryM", "routeOffset_m", "routeOffsetM",
                "landing_m", "landingM", "expectedRemaining_m", "expectedRemainingM",
                "planVersion",
            ] {
                if let value = raw[key] { row[key] = value }
            }
            return .object(row)
        }
        guard !clubs.isEmpty else { return nil }
        let label = steps.compactMap { string($0["clubName"] ?? $0["club"]) }.joined(separator: "-")
        return [
            "id": .string("stock"),
            "label": .string(label),
            "strategyLabel": .string("推荐"),
            "clubs": .array(clubs),
            "planSource": .string("course_prep"),
            "planVersion": .string("ai-caddie-shot-plan-v1"),
        ]
    }

    private func string(_ value: JSONValue?) -> String? {
        guard case .string(let raw) = value else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private func number(_ value: JSONValue?) -> Double? {
        guard case .number(let raw) = value, raw.isFinite else { return nil }
        return raw
    }

    private func offlineEvidence(seed: CaddieContextSeed, selected: OfflineCaddieOption) -> [[String: JSONValue]] {
        seed.evidence + [
            [
                "label": .string("offline_caddie"),
                "value": .string("cached_decision"),
                "sourceRef": .string(seed.sourceRef),
            ],
            [
                "label": .string("offline_option"),
                "value": .string(selected.optionId),
                "clubName": .string(selected.clubName),
                "confidence": .string(selected.confidence ?? "low"),
            ],
        ]
    }

    private func confidencePayload(_ option: OfflineCaddieOption) -> [String: JSONValue] {
        var payload: [String: JSONValue] = [
            "level": .string(option.confidence ?? "low"),
            "source": .string("offline_package_seed"),
            "sampleSize": .number(Double(option.sampleSize ?? 0)),
        ]
        if let coverage = option.coverage {
            payload["coverage"] = coveragePayload(coverage)
        }
        return payload
    }

    private func auditCriteria(seed: CaddieContextSeed, selected: OfflineCaddieOption) -> [[String: JSONValue]] {
        [
            [
                "label": .string("offline_selected_option"),
                "targetOptionId": .string(selected.optionId),
                "sourceRef": .string(seed.sourceRef),
            ],
            [
                "label": .string("club_profile_confidence"),
                "clubName": .string(selected.clubName),
                "confidence": .string(selected.confidence ?? "low"),
                "sampleSize": .number(Double(selected.sampleSize ?? 0)),
            ],
        ]
    }

    private func coveragePayload(_ coverage: OfflineOptionCoverage) -> JSONValue {
        .object([
            "ready": .number(Double(coverage.ready)),
            "total": .number(Double(coverage.total)),
            "pct": .number(coverage.pct),
        ])
    }

    private func jsonNumberOrNull(_ value: Double?) -> JSONValue {
        guard let value else {
            return .null
        }
        return .number(value)
    }

    private func uniqueRefs(_ refs: [String]) -> [String] {
        var seen: Set<String> = []
        var output: [String] = []
        for ref in refs {
            let trimmed = ref.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty, !seen.contains(trimmed) else {
                continue
            }
            seen.insert(trimmed)
            output.append(trimmed)
        }
        return output
    }

    private func phase(for shotType: String) -> String {
        switch shotType {
        case "tee":
            return "Tee"
        case "recovery":
            return "Recovery"
        default:
            return "Approach"
        }
    }

    private func offlineDecisionId(
        seed: CaddieContextSeed,
        request: CaddieDecisionRequest,
        selected: OfflineCaddieOption
    ) -> String {
        let raw = "offline-\(seed.sourceRef)-\(request.shotType)-\(selected.optionId)"
        return raw
            .replacingOccurrences(of: ":", with: "-")
            .replacingOccurrences(of: " ", with: "-")
    }
}
