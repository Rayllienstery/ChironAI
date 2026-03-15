import Foundation

/// Raw markdown file as read from a source (e.g. filesystem).
///
/// Represents a single file before normalization and chunking.
struct MarkdownFile: Equatable {
    /// Identifier of the source (e.g. "local", crawl job id).
    let sourceId: String
    /// Base filename (last path component).
    let filename: String
    /// Full raw content of the file.
    let content: String
    /// Relative path from the source root.
    let path: String
}
