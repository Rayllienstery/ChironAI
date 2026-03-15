import Foundation

/// Result of a single ingest run.
///
/// Returned by ``IngestLocalMarkdownUseCase/execute(sourceId:basePath:collection:dryRun:)``
/// and printed as JSON by the CLI.
struct IngestSummary: Codable {
    /// Number of markdown files that produced at least one chunk.
    var filesProcessed: Int
    /// Number of chunks written to the sink (0 when dry run).
    var chunksIndexed: Int
    /// Non-fatal errors collected during the run (e.g. per-file read failures).
    var errors: [String]
}
