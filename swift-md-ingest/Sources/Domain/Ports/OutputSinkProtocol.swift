import Foundation

/// Port for writing chunk payloads to a sink (e.g. RAG service).
///
/// Implementations might use HTTP (rag_service), a test double, or a no-op for dry runs.
/// The use case depends only on this protocol.
protocol OutputSinkProtocol {
    /// Writes chunks to the sink for the given collection.
    /// - Parameters:
    ///   - collection: Target RAG collection name.
    ///   - chunks: Chunk payloads to write.
    /// - Returns: Number of points/chunks written (as reported by the sink).
    func writeChunks(collection: String, chunks: [ChunkPayload]) throws -> Int
}
