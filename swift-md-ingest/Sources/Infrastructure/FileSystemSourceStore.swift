import Foundation

/// File system implementation of ``SourceStoreProtocol``.
///
/// Recursively lists `.md` files under a base path and reads their content as UTF-8.
/// Path handling is cross-platform (handles both `/` and `\`).
final class FileSystemSourceStore: SourceStoreProtocol {
    private let fileManager: FileManager

    /// Creates a store using the given file manager.
    /// - Parameter fileManager: Defaults to `FileManager.default`.
    init(fileManager: FileManager = .default) {
        self.fileManager = fileManager
    }

    func listFiles(basePath: String) throws -> [String] {
        let url = URL(fileURLWithPath: basePath)
        var results: [String] = []
        guard let enumerator = fileManager.enumerator(at: url, includingPropertiesForKeys: nil) else {
            return []
        }
        let basePathNorm = url.path.hasSuffix("/") ? url.path : url.path + "/"
        let baseNorm = basePathNorm.replacingOccurrences(of: "\\", with: "/")
        for case let fileURL as URL in enumerator {
            if fileURL.hasDirectoryPath { continue }
            if fileURL.pathExtension.lowercased() == "md" {
                let filePathNorm = fileURL.path.replacingOccurrences(of: "\\", with: "/")
                let relPath = filePathNorm.hasPrefix(baseNorm)
                    ? String(filePathNorm.dropFirst(baseNorm.count)).trimmingCharacters(in: CharacterSet(charactersIn: "/\\"))
                    : filePathNorm
                results.append(relPath)
            }
        }
        return results
    }

    func readFile(sourceId: String, basePath: String, relativePath: String) throws -> MarkdownFile? {
        let fullPath = (basePath as NSString).appendingPathComponent(relativePath)
        let url = URL(fileURLWithPath: fullPath)
        let data = try Data(contentsOf: url)
        guard let content = String(data: data, encoding: .utf8) else {
            return nil
        }
        return MarkdownFile(
            sourceId: sourceId,
            filename: (relativePath as NSString).lastPathComponent,
            content: content,
            path: relativePath
        )
    }
}
