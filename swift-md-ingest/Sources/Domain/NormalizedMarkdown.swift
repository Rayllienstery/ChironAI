import Foundation

/// Markdown after normalization (trimmed content, resolved path).
///
/// Produced by ``NormalizationService`` from a ``MarkdownFile``
/// and used as input to chunking.
struct NormalizedMarkdown: Equatable {
    /// Identifier of the source.
    let sourceId: String
    /// Base filename.
    let filename: String
    /// Cleaned content (whitespace trimmed).
    let content: String
    /// Path used for metadata (path or filename).
    let path: String
    /// Optional URL for the document; nil if not set.
    let url: String?
    /// Optional section hierarchy from headings; nil if not computed.
    let sectionPath: [String]?
}
