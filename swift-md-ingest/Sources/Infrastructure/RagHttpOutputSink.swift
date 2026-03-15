import Foundation

/// HTTP implementation of ``OutputSinkProtocol`` for the RAG service.
///
/// POSTs chunks to `{baseURL}/v1/ingest/chunks` with body `{ "collection", "chunks" }`.
/// Base URL is taken from `baseURLString`, or from the `RAG_SERVICE_URL` environment variable,
/// or defaults to `http://localhost:5001`.
final class RagHttpOutputSink: OutputSinkProtocol {
    private let baseURL: URL
    private let session: URLSession

    /// Creates a sink with the given base URL or environment fallback.
    /// - Parameters:
    ///   - baseURLString: Optional base URL (e.g. `"http://localhost:5001"`); `nil` uses `RAG_SERVICE_URL` or default.
    ///   - session: URL session for the request; defaults to `.shared`.
    /// - Returns: `nil` if the resolved URL string is invalid.
    init?(baseURLString: String?, session: URLSession = .shared) {
        let urlString = (baseURLString ?? ProcessInfo.processInfo.environment["RAG_SERVICE_URL"] ?? "http://localhost:5001")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: urlString) else {
            return nil
        }
        self.baseURL = url
        self.session = session
    }

    func writeChunks(collection: String, chunks: [ChunkPayload]) throws -> Int {
        let endpoint = baseURL.appendingPathComponent("v1/ingest/chunks")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let payload = RagIngestRequestPayload(collection: collection, chunks: chunks)
        request.httpBody = try JSONEncoder().encode(payload)

        let semaphore = DispatchSemaphore(value: 0)
        var result: Result<Int, Error> = .failure(MdIngestError.httpError("Unknown error"))

        let task = session.dataTask(with: request) { [baseURL] data, response, error in
            defer { semaphore.signal() }
            if let error = error {
                result = .failure(MdIngestError.httpError("RAG service not reachable at \(baseURL): \(error.localizedDescription)"))
                return
            }
            guard let httpResponse = response as? HTTPURLResponse else {
                result = .failure(MdIngestError.httpError("Invalid HTTP response"))
                return
            }
            guard (200..<300).contains(httpResponse.statusCode) else {
                if httpResponse.statusCode == 404 {
                    result = .failure(MdIngestError.httpError("RAG service does not expose /v1/ingest/chunks yet."))
                } else {
                    result = .failure(MdIngestError.httpError("RAG ingest failed with status \(httpResponse.statusCode)"))
                }
                return
            }
            guard let data = data, !data.isEmpty else {
                result = .success(chunks.count)
                return
            }
            do {
                if let json = try JSONSerialization.jsonObject(with: data, options: []) as? [String: Any],
                   let points = json["points_written"] as? Int {
                    result = .success(points)
                } else {
                    result = .success(chunks.count)
                }
            } catch {
                result = .success(chunks.count)
            }
        }
        task.resume()
        semaphore.wait()

        switch result {
        case .success(let count):
            return count
        case .failure(let error):
            throw error
        }
    }
}
