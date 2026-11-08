import Foundation

/// Cross-target identity for Garmin fallback pixels.  Keep the wire/cache style in the shared
/// domain so the iPhone, Watch and transfer metadata cannot silently drift apart.
public enum GarminRasterContract {
    public static let assetStyleVersion = "garmin-raster-v1"
}
