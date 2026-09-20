import Foundation

/// Presentation-only helpers for Garmin course names.
///
/// Garmin's scorecard snapshot and its locale-aware CourseView catalogue can
/// provide localized venue names for the same global id. This type combines
/// those already-provided values; it never translates an English name and never
/// uses a global id as a name lookup.
public enum GarminCourseNameAuthority {
    public static let garminSnapshotNameSource = "garmin_scorecard_snapshot"

    public static func normalize(_ raw: String?) -> String {
        guard let raw else { return "" }
        return raw
            .split(whereSeparator: { $0.isWhitespace })
            .map(String.init)
            .joined(separator: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public static func split(_ raw: String?) -> (venue: String, suffix: String?) {
        let normalized = normalize(raw)
        guard !normalized.isEmpty else { return ("", nil) }
        let parts = normalized.split(separator: "~", maxSplits: 1, omittingEmptySubsequences: true)
        var venue = String(parts[0]).trimmingCharacters(in: .whitespacesAndNewlines)
        var suffix: String? = parts.count > 1
            ? String(parts[1]).trimmingCharacters(in: .whitespacesAndNewlines)
            : nil
        // Legacy Garmin rows sometimes omit the `~` separator, e.g. `Black
        // Knight B/C` or `Black Knight AC`. Treat that trailing combination as
        // a route label, never as part of the physical venue.
        let tokens = venue.split(whereSeparator: { $0.isWhitespace })
        if let last = tokens.last,
           tokens.count > 1,
           isCompositeSegment(String(last)) {
            venue = tokens.dropLast().map(String.init).joined(separator: " ")
            if suffix?.isEmpty != false { suffix = String(last) }
        }
        return (venue, suffix?.isEmpty == false ? suffix : nil)
    }

    public static func containsChinese(_ raw: String?) -> Bool {
        normalize(raw).unicodeScalars.contains { scalar in
            (0x3400...0x4DBF).contains(scalar.value)
                || (0x4E00...0x9FFF).contains(scalar.value)
                || (0x20000...0x2FA1F).contains(scalar.value)
        }
    }

    /// A/C, A+B, and compact AB/AC/AF/ABC values describe a played combination,
    /// not one selectable CourseView loop.
    public static func isCompositeSegment(_ raw: String?) -> Bool {
        guard let raw else { return false }
        let value = normalize(raw)
        guard !value.isEmpty else { return false }
        if value.contains("/") || value.contains("+") { return true }
        let compact = value.replacingOccurrences(of: " ", with: "").uppercased()
        return compact.range(of: "^[A-H]{2,4}$", options: .regularExpression) != nil
    }

    public static func selectableName(_ raw: String?) -> String {
        let normalized = normalize(raw)
        let parts = split(normalized)
        guard let suffix = parts.suffix, isCompositeSegment(suffix) else { return normalized }
        return parts.venue
    }

    /// Resolve the backend course-name contract for a catalogue/package row.
    ///
    /// The returned value is always the physical venue title. A playable loop
    /// is separate metadata (`canonicalSegment`); it is never appended to the
    /// shared course title. `venueName` can replace the provider spelling only
    /// when its source is the explicit Garmin scorecard snapshot marker. A
    /// manual or unmarked cached value is never allowed to relabel a CourseView
    /// row. The same rule is mirrored by the Web helper and Python authority.
    public static func canonicalName(
        providerName: String?,
        venueName: String? = nil,
        venueNameSource: String? = nil,
        segmentLabel: String? = nil
    ) -> String {
        _ = segmentLabel
        let provider = selectableName(providerName)
        let providerParts = split(provider)
        let source = normalize(venueNameSource).lowercased()
        let trustedVenue: String = source == garminSnapshotNameSource
            ? split(venueName).venue
            : ""
        let venue = trustedVenue.isEmpty ? providerParts.venue : trustedVenue
        guard !venue.isEmpty else { return provider }

        return venue
    }

    /// Return the factual single-loop label without allowing a played
    /// combination (`A/C`, `AB`, ...) to masquerade as one selectable loop.
    public static func canonicalSegment(
        providerName: String?,
        segmentLabel: String? = nil
    ) -> String? {
        let providerSuffix = split(selectableName(providerName)).suffix.flatMap { suffix in
            isCompositeSegment(suffix) ? nil : suffix
        }
        if let providerSuffix, !providerSuffix.isEmpty { return providerSuffix }
        guard let segmentLabel else { return nil }
        let normalized = normalize(segmentLabel)
        guard !normalized.isEmpty, !isCompositeSegment(normalized) else { return nil }
        return normalized
    }

    /// Preserve Garmin's factual single-loop name and add the Chinese suffix once.
    /// `A` becomes `A 场`, while an existing name such as `老球场` remains unchanged.
    public static func userFacingSegmentTitle(label: String?, holes: Int?) -> String {
        if holes == 18 { return "全场" }
        guard holes == 9 else { return "洞组" }
        guard let label else { return "9 洞组" }
        let normalized = normalize(label)
        guard !normalized.isEmpty else { return "9 洞组" }
        guard !isCompositeSegment(normalized) else { return "9 洞组" }
        return normalized.hasSuffix("场") ? normalized : "\(normalized) 场"
    }

    /// Physical venue portion of `canonicalName`, used for round/history titles.
    public static func canonicalVenueName(
        providerName: String?,
        venueName: String? = nil,
        venueNameSource: String? = nil,
        segmentLabel: String? = nil
    ) -> String {
        split(canonicalName(
            providerName: providerName,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel
        )).venue
    }

    /// Use a trusted Garmin-backed venue and the provider row's current single
    /// loop suffix. The provider suffix wins because it identifies the row the
    /// player is currently selecting; trusted names only supply the venue.
    public static func mergedName(
        providerName: String?,
        trustedNames: [String?],
        trustedNameSources: [String?] = []
    ) -> String {
        let provider = split(providerName)
        // A persisted option may predate the explicit source field. In that
        // case its `venueName` could be an old presentation alias, so it is
        // deliberately ignored unless the provider string itself is Chinese.
        // Fresh API rows carry a parallel Garmin source marker and are trusted.
        let trustedEntries: [(venue: String, suffix: String?)] = trustedNames.enumerated().compactMap { index, raw in
            guard let source = trustedNameSources[safe: index],
                  source?.trimmingCharacters(in: .whitespacesAndNewlines)
                    .caseInsensitiveCompare(Self.garminSnapshotNameSource) == .orderedSame else {
                return nil
            }
            let parts = split(raw)
            guard !parts.venue.isEmpty else { return nil }
            return (parts.venue, parts.suffix)
        }
        let trustedVenues = trustedEntries.map(\.venue)
        let venue = trustedVenues.first(where: containsChinese)
            ?? trustedVenues.first
            ?? provider.venue
        guard !venue.isEmpty else { return normalize(providerName) }

        let trustedSingleSuffix = trustedEntries.compactMap { entry -> String? in
            let suffix = entry.suffix
            guard let suffix, !isCompositeSegment(suffix) else { return nil }
            return suffix
        }.first
        let suffix: String?
        if let providerSuffix = provider.suffix, !isCompositeSegment(providerSuffix) {
            suffix = providerSuffix
        } else {
            suffix = trustedSingleSuffix
        }
        guard let suffix, !suffix.isEmpty else { return venue }
        return "\(venue) ~ \(suffix)"
    }

    public static func mergedVenue(
        providerName: String?,
        trustedNames: [String?],
        trustedNameSources: [String?] = []
    ) -> String {
        let merged = mergedName(
            providerName: providerName,
            trustedNames: trustedNames,
            trustedNameSources: trustedNameSources
        )
        return split(merged).venue
    }
}

private extension Array {
    subscript(safe index: Index) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}
