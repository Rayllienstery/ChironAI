import Foundation

/// Domain service that normalizes raw markdown content.
///
/// Produces a ``NormalizedMarkdown`` with trimmed content and resolved path,
/// suitable for chunking.
enum NormalizationService {
    /// Normalizes a raw markdown file (trim whitespace, set path).
    /// - Parameter md: The raw ``MarkdownFile`` from the source.
    /// - Returns: A ``NormalizedMarkdown`` with cleaned content and path.
    static func normalize(_ md: MarkdownFile) -> NormalizedMarkdown {
        let content = md.content.trimmingCharacters(in: .whitespacesAndNewlines)
        return NormalizedMarkdown(
            sourceId: md.sourceId,
            filename: md.filename,
            content: content,
            path: md.path.isEmpty ? md.filename : md.path,
            url: nil,
            sectionPath: nil
        )
    }
}
