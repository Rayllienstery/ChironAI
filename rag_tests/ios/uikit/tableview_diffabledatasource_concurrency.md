# UITableViewDiffableDataSource and concurrency

Platform: iOS
Framework: UIKit
MinOS: iOS 15
Difficulty: advanced
Concept Mode: all
RAG Strict: true

## Question

You use `UITableViewDiffableDataSource` to show data that is loaded and updated
from multiple async sources (network, local cache).
Explain:

- how to construct and apply snapshots safely from background tasks;
- why snapshots should be applied on the main thread only;
- how to avoid race conditions when multiple updates arrive in quick succession;
- best practices for batching changes and keeping the UI consistent.

## Expected Concepts

- UITableViewDiffableDataSource
- NSDiffableDataSourceSnapshot
- main thread
- race condition
- batching updates

## RAG Requirement

The answer must reference Apple documentation on diffable data sources and thread-safety.

## Notes

Tests understanding of modern list APIs plus concurrency in UIKit.

