import Foundation

/// Domain service that filters markdown files by path patterns and size.
///
/// Uses include/exclude glob-like patterns and optional min/max character limits.
/// Provides a default rule that includes all `**/*.md` files.
enum FilteringService {
    /// Returns `true` if the file passes the rule.
    /// - Parameters:
    ///   - file: The markdown file to test.
    ///   - rule: Filter rule (include/exclude patterns, min/max size).
    /// - Returns: `true` to include the file, `false` to skip.
    static func applyFilter(file: MarkdownFile, rule: FilterRule) -> Bool {
        let pathValue = file.path.isEmpty ? file.filename : file.path
        for pattern in rule.excludePatterns {
            if pathMatches(pathValue, pattern: pattern) {
                return false
            }
        }
        if !rule.includePatterns.isEmpty {
            let included = rule.includePatterns.contains { pathMatches(pathValue, pattern: $0) }
            if !included {
                return false
            }
        }
        if rule.minSizeChars > 0 && file.content.count < rule.minSizeChars {
            return false
        }
        if rule.maxSizeChars > 0 && file.content.count > rule.maxSizeChars {
            return false
        }
        return true
    }

    /// Default filter rule: include all `**/*.md`, no exclusions, no size limits.
    static func defaultFilterRule() -> FilterRule {
        FilterRule(
            includePatterns: ["**/*.md"],
            excludePatterns: [],
            minSizeChars: 0,
            maxSizeChars: 0
        )
    }

    private static func pathMatches(_ path: String, pattern: String) -> Bool {
        let predicate = NSPredicate(format: "SELF LIKE %@", pattern)
        return predicate.evaluate(with: path) || path.contains(pattern)
    }
}
