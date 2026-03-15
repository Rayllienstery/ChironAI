import Foundation

/// Domain service that splits normalized text into chunks for RAG.
///
/// Uses paragraph-based splitting with markdown heading awareness,
/// min/max chunk size, and a minimum word count per chunk.
/// Mirrors the Python fallback chunking policy (e.g. ``chunkMaxSize`` 1200, ``chunkMinSize`` 300).
enum ChunkingService {
    /// Maximum chunk size in characters.
    static let chunkMaxSize = 1200
    /// Minimum chunk size in characters.
    static let chunkMinSize = 300

    /// Splits text into chunks with section path and returns RAG payloads.
    /// - Parameters:
    ///   - text: Normalized markdown content.
    ///   - sourceId: Source identifier for metadata.
    ///   - filename: Filename for metadata.
    ///   - path: Path for metadata.
    ///   - url: Optional URL; stored in each chunk.
    /// - Returns: Array of ``ChunkPayload`` for the sink.
    static func chunksForDocument(
        text: String,
        sourceId: String,
        filename: String,
        path: String,
        url: String?
    ) -> [ChunkPayload] {
        let rawChunks = splitMarkdownIntoChunks(text)
        let pathValue = path.isEmpty ? filename : path
        let urlValue = url ?? ""
        return rawChunks.map { chunkText, sectionPath in
            ChunkPayload(
                text: chunkText,
                sourceId: sourceId,
                path: pathValue,
                url: urlValue,
                sectionPath: sectionPath
            )
        }
    }

    private static func chunkQualityOk(_ text: String) -> Bool {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return false }
        let words = trimmed.split(whereSeparator: { $0.isWhitespace })
        return words.count >= 25
    }

    private static func splitMarkdownIntoChunks(
        _ md: String,
        maxChunkSize: Int? = nil,
        minChunkSize: Int? = nil
    ) -> [(text: String, sectionPath: [String])] {
        guard !md.isEmpty else { return [] }
        let maxSize = maxChunkSize ?? chunkMaxSize
        let minSize = minChunkSize ?? chunkMinSize
        let rawParagraphs = md.components(separatedBy: "\n\n")
        let paragraphs = rawParagraphs.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }

        var chunks: [(String, [String])] = []
        var current: [String] = []
        var currentLen = 0
        var sectionPath: [String] = []

        for paragraph in paragraphs {
            let stripped = paragraph.trimmingCharacters(in: .whitespaces)
            if stripped.hasPrefix("#") {
                var depth = 0
                for ch in stripped {
                    if ch == "#" { depth += 1 } else { break }
                }
                let title = stripped.drop(while: { $0 == "#" || $0.isWhitespace })
                if depth >= 1 && !title.isEmpty {
                    let titleString = String(title)
                    if depth - 1 < sectionPath.count {
                        sectionPath = Array(sectionPath.prefix(depth - 1))
                    }
                    sectionPath.append(titleString)
                }
            }
            let additionalLen = paragraph.count + 2
            if currentLen + additionalLen > maxSize && !current.isEmpty {
                let text = current.joined(separator: "\n\n")
                chunks.append((text, sectionPath))
                current = [paragraph]
                currentLen = additionalLen
            } else {
                current.append(paragraph)
                currentLen += additionalLen
            }
        }
        if !current.isEmpty {
            let text = current.joined(separator: "\n\n")
            chunks.append((text, sectionPath))
        }
        return chunks.filter { chunkQualityOk($0.0) && $0.0.count >= minSize }
    }
}
