import Foundation

/// Use case: ingest local markdown into RAG.
///
/// Orchestrates the pipeline: list files from a source store, filter, normalize,
/// chunk, and write to an output sink. Depends on ``SourceStoreProtocol`` and
/// ``OutputSinkProtocol``; domain logic is delegated to ``FilteringService``,
/// ``NormalizationService``, and ``ChunkingService``.
struct IngestLocalMarkdownUseCase {
    private let sourceStore: SourceStoreProtocol
    private let outputSink: OutputSinkProtocol
    private let filterRule: FilterRule

    /// Creates the use case with injected dependencies.
    /// - Parameters:
    ///   - sourceStore: Port for listing and reading markdown files.
    ///   - outputSink: Port for writing chunks (e.g. RAG service).
    ///   - filterRule: Optional filter rule; defaults to ``FilteringService/defaultFilterRule()``.
    init(
        sourceStore: SourceStoreProtocol,
        outputSink: OutputSinkProtocol,
        filterRule: FilterRule? = nil
    ) {
        self.sourceStore = sourceStore
        self.outputSink = outputSink
        self.filterRule = filterRule ?? FilteringService.defaultFilterRule()
    }

    /// Runs the pipeline: list → filter → normalize → chunk → write to sink.
    /// - Parameters:
    ///   - sourceId: Source identifier (e.g. "local").
    ///   - basePath: Root path to scan for markdown files.
    ///   - collection: Target RAG collection name.
    ///   - dryRun: If `true`, chunks are not written to the sink.
    /// - Returns: An ``IngestSummary`` with counts and any errors.
    /// - Throws: ``MdIngestError`` for list failures or invalid state.
    func execute(
        sourceId: String,
        basePath: String,
        collection: String,
        dryRun: Bool
    ) throws -> IngestSummary {
        let absoluteBase = (basePath as NSString).expandingTildeInPath
        let relativePaths: [String]
        do {
            relativePaths = try sourceStore.listFiles(basePath: absoluteBase)
        } catch {
            throw MdIngestError.ioError("Failed to list files: \(error.localizedDescription)")
        }

        var errors: [String] = []
        var filesProcessed = 0
        var allChunks: [ChunkPayload] = []

        for rel in relativePaths {
            do {
                guard let md = try sourceStore.readFile(sourceId: sourceId, basePath: absoluteBase, relativePath: rel) else {
                    continue
                }
                if !FilteringService.applyFilter(file: md, rule: filterRule) {
                    continue
                }
                let norm = NormalizationService.normalize(md)
                let chunks = ChunkingService.chunksForDocument(
                    text: norm.content,
                    sourceId: norm.sourceId,
                    filename: norm.filename,
                    path: norm.path,
                    url: norm.url
                )
                if chunks.isEmpty {
                    continue
                }
                filesProcessed += 1
                allChunks.append(contentsOf: chunks)
            } catch {
                errors.append("\(rel): \(error.localizedDescription)")
            }
        }

        var chunksIndexed = 0
        if !dryRun && !allChunks.isEmpty {
            do {
                chunksIndexed = try outputSink.writeChunks(collection: collection, chunks: allChunks)
            } catch {
                errors.append("output_sink: \(error.localizedDescription)")
            }
        }

        return IngestSummary(
            filesProcessed: filesProcessed,
            chunksIndexed: chunksIndexed,
            errors: errors
        )
    }
}
