import Foundation

/// Parsed command-line options for the ingest CLI.
///
/// Produced by ``CLIParser/parse(arguments:)`` and passed to the use case.
struct CLIOptions {
    /// Directory path to scan for markdown files.
    var sourcePath: String
    /// Source identifier (e.g. `"local"`).
    var sourceId: String
    /// Target RAG collection name (e.g. `"webcrawl"`).
    var collection: String
    /// If `true`, do not write chunks to the sink.
    var dryRun: Bool
}
