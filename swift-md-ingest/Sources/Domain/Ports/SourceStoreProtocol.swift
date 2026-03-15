import Foundation

/// Port for listing and reading markdown files from a source.
///
/// Implementations might use the filesystem, a remote API, or a test double.
/// The use case depends only on this protocol, not on concrete types.
protocol SourceStoreProtocol {
    /// Lists relative paths of `.md` files under the given base path (recursive).
    /// - Parameter basePath: Absolute directory path to scan.
    /// - Returns: Array of relative paths (e.g. `["a/b.md", "c.md"]`).
    func listFiles(basePath: String) throws -> [String]

    /// Reads one file into a ``MarkdownFile``.
    /// - Parameters:
    ///   - sourceId: Source identifier to attach to the result.
    ///   - basePath: Base directory path.
    ///   - relativePath: Path relative to base (from ``listFiles(basePath:)``).
    /// - Returns: A ``MarkdownFile``, or `nil` if the file is unreadable (e.g. encoding).
    func readFile(sourceId: String, basePath: String, relativePath: String) throws -> MarkdownFile?
}
