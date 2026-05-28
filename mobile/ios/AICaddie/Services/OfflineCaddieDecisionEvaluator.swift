import Foundation

public final class OfflineCaddieDecisionEvaluator {
    public init() {}

    public func selectedOption(in seed: CaddieContextSeed, strategyMode: String?) -> OfflineCaddieOption? {
        let preferredId = preferredOptionId(for: strategyMode) ?? seed.selectedOfflineOptionId
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
        guard let selected = selectedOption(in: seed, strategyMode: strategyMode) else {
            return nil
        }
        let optionRows = seed.offlineOptions.map(optionPayload)
        let selectedRow = optionPayload(selected)
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
            sequences: nil,
            selectedSequence: nil,
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

    private func optionPayload(_ option: OfflineCaddieOption) -> [String: JSONValue] {
        var row: [String: JSONValue] = [
            "id": .string(option.optionId),
            "label": .string(option.label),
            "clubName": .string(option.clubName),
            "carryM": .number(option.carryM),
            "carry_m": .number(option.carryM),
            "riskScore": .number(option.riskScore),
            "source": .string(option.source),
            "sourceRefs": .array(option.sourceRefs.map { .string($0) }),
            "clubRecommendation": .object([
                "clubs": .array([
                    .object([
                        "clubName": .string(option.clubName),
                        "median_m": .number(option.carryM),
                        "p10_m": jsonNumberOrNull(option.p10M),
                        "p90_m": jsonNumberOrNull(option.p90M),
                        "sampleSize": .number(Double(option.sampleSize ?? 0)),
                        "confidence": .string(option.confidence ?? "low"),
                        "sourceRefs": .array(option.sourceRefs.map { .string($0) }),
                    ])
                ])
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
