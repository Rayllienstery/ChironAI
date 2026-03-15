import Foundation

/// Rule for filtering markdown files by path patterns and size.
///
/// Used by the ingestion pipeline to include or exclude files:
/// exclude patterns are applied first; if any include patterns are set,
/// the file must match at least one. Optional min/max character limits apply.
struct FilterRule: Codable, Equatable {
    /// Glob-like include patterns (e.g. `["**/*.md"]`). Empty means no include filter.
    var includePatterns: [String]
    /// Glob-like exclude patterns. Matching files are skipped.
    var excludePatterns: [String]
    /// Minimum content length in characters; 0 disables.
    var minSizeChars: Int
    /// Maximum content length in characters; 0 disables.
    var maxSizeChars: Int
}
