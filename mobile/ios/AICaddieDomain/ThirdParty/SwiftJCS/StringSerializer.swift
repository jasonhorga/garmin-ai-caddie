import Foundation

/// Serializes a Swift `String` to a JCS-compliant JSON string according to RFC 8785 §3.2.2.2.
///
/// Applies ECMAScript JSON string serialization rules:
/// - Predefined control character escapes: `\b`, `\t`, `\n`, `\f`, `\r`
/// - Other control characters (U+0000–U+001F): `\uhhhh` with lowercase hex
/// - Backslash and double quote: `\\` and `\"`
/// - All other characters: output as-is
/// - Lone surrogates (U+D800–U+DFFF) cause an error
internal func _serializeString(_ string: String, into buffer: inout Data) throws {
    buffer.append(0x22) // opening "

    for scalar in string.unicodeScalars {
        let value = scalar.value

        // Reject lone surrogates (should not appear in valid Swift strings,
        // but guard against it for correctness)
        if value >= 0xD800 && value <= 0xDFFF {
            throw JSONCanonicalizationError.invalidUnicode
        }

        switch value {
        case 0x08: // backspace
            buffer.append(contentsOf: [0x5c, 0x62]) // \b
        case 0x09: // tab
            buffer.append(contentsOf: [0x5c, 0x74]) // \t
        case 0x0A: // newline
            buffer.append(contentsOf: [0x5c, 0x6e]) // \n
        case 0x0C: // form feed
            buffer.append(contentsOf: [0x5c, 0x66]) // \f
        case 0x0D: // carriage return
            buffer.append(contentsOf: [0x5c, 0x72]) // \r
        case 0x00...0x1F: // other control characters → \uhhhh
            buffer.append(0x5c) // backslash
            buffer.append(0x75) // u
            let hex = String(value, radix: 16)
            let padded = String(repeating: "0", count: 4 - hex.count) + hex
            buffer.append(contentsOf: padded.utf8)
        case 0x22: // double quote
            buffer.append(contentsOf: [0x5c, 0x22]) // \"
        case 0x5C: // backslash
            buffer.append(contentsOf: [0x5c, 0x5c]) // \\
        default:
            // Output the scalar's UTF-8 encoding directly
            let utf8 = String(scalar).utf8
            buffer.append(contentsOf: utf8)
        }
    }

    buffer.append(0x22) // closing "
}
