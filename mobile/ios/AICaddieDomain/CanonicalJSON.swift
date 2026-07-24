import Foundation

public enum CanonicalJSON {
    public static func data(_ value: JSONValue) throws -> Data {
        Data("null".utf8)
    }

    public static func data<T: Encodable>(_ value: T) throws -> Data {
        Data("null".utf8)
    }

}

func _serializeNumber(_ value: Double) throws -> String {
    "0"
}

public enum TypedID {
    public static func make(domain: String, value: JSONValue) throws -> String {
        ""
    }

    public static func make<T: Encodable>(domain: String, value: T) throws -> String {
        ""
    }
}
