import Foundation

/// Builds `ai-caddie-live-round-package-v2` JSON that satisfies the Watch decoder's round-identity
/// gate (B4b-2 §6): every loop names all nine of its holes on their canonical rows. A test keeps the
/// literal facts it asserts on by passing that round hole's JSON in `overrides`; every other hole is
/// a generated par-4 row. The lower-level pieces (`loopRow`, `hole`, `json`) let negative tests
/// break exactly one invariant at a time.
enum WatchPackageFixture {
    static let v2Schema = "ai-caddie-live-round-package-v2"

    struct Loop {
        let globalId: Int
        let half: String

        init(_ globalId: Int, _ half: String) {
            self.globalId = globalId
            self.half = half
        }

        var sourceStartHole: Int { half == "back" ? 10 : 1 }
    }

    /// The canonical `roundLoops` row for the loop at `index`; each argument overrides one field.
    static func loopRow(
        _ loop: Loop,
        index: Int,
        roundStartHole: Int? = nil,
        sourceStartHole: Int? = nil,
        holeCount: Int = 9
    ) -> String {
        let start = roundStartHole ?? (1 + index * 9)
        let source = sourceStartHole ?? loop.sourceStartHole
        return "{\"globalId\":\(loop.globalId),\"half\":\"\(loop.half)\","
            + "\"roundStartHole\":\(start),\"sourceStartHole\":\(source),\"holeCount\":\(holeCount)}"
    }

    static func roundLoops(_ loops: [Loop]) -> String {
        var rows: [String] = []
        for index in loops.indices {
            rows.append(loopRow(loops[index], index: index))
        }
        return "[" + rows.joined(separator: ",") + "]"
    }

    static func loopKey(_ loops: [Loop]) -> String {
        loops.map { "\($0.globalId):\($0.half)" }.joined(separator: "+")
    }

    /// The canonical row for round hole `number` played on the loop at `loopIndex`.
    /// `sourceLocalHole` overrides only that field (to build a hole that is off its row).
    static func hole(
        number: Int,
        loop: Loop,
        loopIndex: Int,
        par: Int = 4,
        sourceLocalHole: Int? = nil
    ) -> String {
        let canonicalLocal = loop.sourceStartHole + (number - (1 + loopIndex * 9))
        let local = sourceLocalHole ?? canonicalLocal
        let courseHole = loop.half == "all" ? number : canonicalLocal
        return "{\"number\":\(number),\"par\":\(par),\"sourceGlobalId\":\(loop.globalId),"
            + "\"sourceLocalHole\":\(local),\"courseHoleNumber\":\(courseHole)}"
    }

    /// Every canonical hole of `loops` in round order; `overrides[n]` replaces round hole `n`'s row
    /// with a test's literal JSON (which must itself sit on that row).
    static func holes(_ loops: [Loop], overrides: [Int: String] = [:]) -> [String] {
        var rows: [String] = []
        for index in loops.indices {
            for offset in 0..<9 {
                let number = 1 + index * 9 + offset
                rows.append(overrides[number] ?? hole(number: number, loop: loops[index], loopIndex: index))
            }
        }
        return rows
    }

    /// Assemble a package from raw parts. `extra` is appended verbatim as further top-level
    /// members (for example `"coursePrep":{...}`), without a leading comma.
    static func json(
        schema: String = WatchPackageFixture.v2Schema,
        roundId: String,
        course: String,
        holes holeRows: [String],
        roundLoops loopRows: String,
        loopKey key: String,
        extra: String = ""
    ) -> String {
        var members = [
            "\"schema\":\"\(schema)\"",
            "\"roundId\":\"\(roundId)\"",
            "\"course\":" + course,
            "\"holes\":[" + holeRows.joined(separator: ",") + "]",
            "\"roundLoops\":" + loopRows,
            "\"loopKey\":\"\(key)\"",
        ]
        if !extra.isEmpty { members.append(extra) }
        return "{" + members.joined(separator: ",") + "}"
    }

    /// A contract-valid package for `loops` (nine holes each).
    static func packageData(
        schema: String = WatchPackageFixture.v2Schema,
        roundId: String,
        course: String,
        loops: [Loop],
        overrides: [Int: String] = [:],
        extra: String = ""
    ) -> Data {
        Data(json(
            schema: schema,
            roundId: roundId,
            course: course,
            holes: holes(loops, overrides: overrides),
            roundLoops: roundLoops(loops),
            loopKey: loopKey(loops),
            extra: extra
        ).utf8)
    }
}
