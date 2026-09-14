import Foundation

/// Presentation-only helpers for Garmin course names.
///
/// Garmin's scorecard snapshot can contain a localized venue name while the
/// anonymous CourseView catalogue returns an English spelling for the same
/// global id.  This type combines those two already-provided values; it never
/// translates an English name and never uses a global id as a name lookup.
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
        let venue = String(parts[0]).trimmingCharacters(in: .whitespacesAndNewlines)
        guard parts.count > 1 else { return (venue, nil) }
        let suffix = String(parts[1]).trimmingCharacters(in: .whitespacesAndNewlines)
        return (venue, suffix.isEmpty ? nil : suffix)
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
