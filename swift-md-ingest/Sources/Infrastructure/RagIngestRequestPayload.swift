import Foundation

/// Request body for POST /v1/ingest/chunks (RAG service contract).
///
/// Used by ``RagHttpOutputSink`` to encode the JSON payload.
struct RagIngestRequestPayload: Codable {
    /// Target collection name.
    var collection: String
    /// Chunk payloads to ingest.
    var chunks: [ChunkPayload]
}
