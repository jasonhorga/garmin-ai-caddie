/// Serializes a `Double` value according to ECMA-262 §7.1.12.1 (Number::toString).
///
/// This produces the shortest decimal representation that uniquely identifies
/// the IEEE 754 double-precision value, formatted per ECMAScript rules.
internal func _serializeNumber(_ value: Double) throws -> String {
    // NaN and Infinity are not permitted in JSON
    guard value.isFinite else {
        throw JSONCanonicalizationError.invalidNumber
    }

    // Positive and negative zero both serialize as "0"
    if value.isZero {
        return "0"
    }

    // Handle sign
    let isNegative = value.sign == .minus
    let absValue = isNegative ? -value : value

    // Extract significant digits and decimal position using Swift's
    // shortest round-trippable representation (same digits as ECMAScript).
    let (digits, n) = _extractDigitsAndExponent(absValue)
    let k = digits.count

    // ECMAScript formatting rules (ECMA-262 §7.1.12.1 steps 5-9):
    let result: String
    if k <= n && n <= 21 {
        // Step 5: integer with trailing zeros (e.g., "295147905179352830000")
        result = digits + .init(repeating: "0", count: n - k)
    }
    else if 0 < n && n < k {
        // Step 6: decimal number (e.g., "333333333.3333333", "4.5")
        let intPart = String(digits.prefix(n))
        let fracPart = String(digits.suffix(k - n))
        result = intPart + "." + fracPart
    }
    else if -6 < n && n <= 0 {
        // Step 7: 0.000...digits (e.g., "0.000001")
        result = "0." + .init(repeating: "0", count: -n) + digits
    }
    else {
        // Steps 8-9: exponential notation (e.g., "1e+30", "1.7976931348623157e+308")
        let exponent = n - 1
        let exponentSign = exponent >= 0 ? "+" : ""
        if k == 1 {
            result = digits + "e" + exponentSign + .init(exponent)
        }
        else {
            result = .init(digits.prefix(1)) + "." + .init(digits.dropFirst()) + "e" + exponentSign + .init(exponent)
        }
    }

    return isNegative ? "-" + result : result
}

/// Extracts the significant digits and decimal exponent position from a positive `Double`.
///
/// Uses Swift's `String(Double)` which produces the shortest round-trippable
/// decimal representation (Ryu algorithm), identical digits to ECMAScript's.
///
/// Returns `(digits, n)` where:
/// - `digits` is a string of significant decimal digits (no leading/trailing zeros)
/// - `n` is the decimal position such that `value = Integer(digits) × 10^(n - digits.count)`
private func _extractDigitsAndExponent(_ value: Double) -> (String, Int) {
    let str = String(value)

    // Split off exponent part (e.g., "1.5e+30" → mantissa="1.5", exp=30)
    let mantissaStr: Substring
    let exponentOffset: Int
    if let eIndex = str.firstIndex(where: { $0 == "e" || $0 == "E" }) {
        mantissaStr = str[str.startIndex..<eIndex]
        exponentOffset = .init(str[str.index(after: eIndex)...])!
    }
    else {
        mantissaStr = str[...]
        exponentOffset = 0
    }

    // Remove decimal point, track how many digits were before it
    let allDigits: String
    let decimalPos: Int
    if let dotIndex = mantissaStr.firstIndex(of: ".") {
        let beforeDot = mantissaStr[mantissaStr.startIndex..<dotIndex]
        let afterDot = mantissaStr[mantissaStr.index(after: dotIndex)...]
        allDigits = .init(beforeDot) + .init(afterDot)
        decimalPos = beforeDot.count
    }
    else {
        allDigits = .init(mantissaStr)
        decimalPos = allDigits.count
    }

    // Strip leading zeros
    var startIdx = allDigits.startIndex
    var leadingZeroCount = 0
    while startIdx < allDigits.endIndex && allDigits[startIdx] == "0" {
        startIdx = allDigits.index(after: startIdx)
        leadingZeroCount += 1
    }

    // Strip trailing zeros
    var endIdx = allDigits.endIndex
    while endIdx > startIdx && allDigits[allDigits.index(before: endIdx)] == "0" {
        endIdx = allDigits.index(before: endIdx)
    }

    if startIdx >= endIdx {
        return ("0", 0)
    }

    let digits = String(allDigits[startIdx..<endIdx])

    // The decimal position in ECMAScript terms simplifies to:
    // n = decimalPos - leadingZeroCount + exponentOffset
    let n = decimalPos - leadingZeroCount + exponentOffset

    return (digits, n)
}
