import Foundation

/// CLI entry point: composes dependencies and runs the ingest use case.
///
/// Parses arguments with ``CLIParser``, builds ``FileSystemSourceStore`` and
/// ``RagHttpOutputSink``, runs ``IngestLocalMarkdownUseCase``, and prints
/// the result as JSON to stdout. Exit code 0 on success, 1 on errors or invalid args.
@main
enum SwiftMdIngestCLI {
    static func main() {
        do {
            let options = try CLIParser.parse(arguments: CommandLine.arguments)
            let sourceStore = FileSystemSourceStore()
            guard let outputSink = RagHttpOutputSink(baseURLString: nil) else {
                fputs("Error: Invalid RAG_SERVICE_URL\n", stderr)
                exit(1)
            }
            let useCase = IngestLocalMarkdownUseCase(
                sourceStore: sourceStore,
                outputSink: outputSink
            )
            let summary = try useCase.execute(
                sourceId: options.sourceId,
                basePath: options.sourcePath,
                collection: options.collection,
                dryRun: options.dryRun
            )
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            let data = try encoder.encode(summary)
            if let json = String(data: data, encoding: .utf8) {
                print(json)
            } else {
                fputs("Failed to encode JSON\n", stderr)
                exit(1)
            }
            if !summary.errors.isEmpty {
                exit(1)
            }
            exit(0)
        } catch {
            if let mdError = error as? MdIngestError {
                fputs("Error: \(mdError.localizedDescription)\n", stderr)
            } else {
                fputs("Error: \(error.localizedDescription)\n", stderr)
            }
            exit(1)
        }
    }
}
