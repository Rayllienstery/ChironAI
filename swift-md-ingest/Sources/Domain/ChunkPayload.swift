import Foundation

/// A single chunk payload sent to the RAG ingest endpoint.
///
/// Matches the contract expected by rag_service (POST /v1/ingest/chunks).
/// Each chunk includes text and metadata for retrieval and attribution.
struct ChunkPayload: Codable {
    /// The chunk text content.
    var text: String
    /// Source identifier.
    var sourceId: String
    /// Path or filename for attribution.
    var path: String
    /// Optional URL; empty string if none.
    var url: String
    /// Section heading path (e.g. from markdown `#` hierarchy).
    var sectionPath: [String]
}
