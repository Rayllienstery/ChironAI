import Foundation

/// Parses command-line arguments into ``CLIOptions``.
///
/// Expects: `<source_path> [--source-id ID] [--collection NAME] [--dry-run]`.
enum CLIParser {
    /// Parses the given argument list (e.g. `CommandLine.arguments`).
    /// - Parameter arguments: Full argv-style array; the first element (executable name) is skipped.
    /// - Returns: Parsed ``CLIOptions`` with defaults for omitted flags.
    /// - Throws: ``MdIngestError/invalidArguments(_:)`` if required args are missing or unknown flags appear.
    static func parse(arguments: [String]) throws -> CLIOptions {
        var args = arguments.dropFirst()
        guard let sourcePath = args.first else {
            throw MdIngestError.invalidArguments("Usage: swift-md-ingest <source_path> [--source-id ID] [--collection NAME] [--dry-run]")
        }
        args = args.dropFirst()
        var sourceId = "local"
        var collection = "webcrawl"
        var dryRun = false

        while let arg = args.first {
            args = args.dropFirst()
            switch arg {
            case "--source-id":
                guard let value = args.first else {
                    throw MdIngestError.invalidArguments("--source-id requires a value")
                }
                sourceId = value
                args = args.dropFirst()
            case "--collection":
                guard let value = args.first else {
                    throw MdIngestError.invalidArguments("--collection requires a value")
                }
                collection = value
                args = args.dropFirst()
            case "--dry-run":
                dryRun = true
            default:
                throw MdIngestError.invalidArguments("Unknown argument: \(arg)")
            }
        }

        return CLIOptions(
            sourcePath: sourcePath,
            sourceId: sourceId,
            collection: collection,
            dryRun: dryRun
        )
    }
}
