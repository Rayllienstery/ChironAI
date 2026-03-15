import Foundation

/// Errors thrown by the markdown ingestion pipeline.
///
/// Used for invalid CLI arguments, file I/O failures, and RAG HTTP errors.
enum MdIngestError: Error, LocalizedError {
    /// Invalid or missing command-line arguments.
    case invalidArguments(String)
    /// File system error (e.g. list or read failure).
    case ioError(String)
    /// RAG service HTTP or connection error.
    case httpError(String)

    var errorDescription: String? {
        switch self {
        case .invalidArguments(let message):
            return message
        case .ioError(let message):
            return message
        case .httpError(let message):
            return message
        }
    }
}
