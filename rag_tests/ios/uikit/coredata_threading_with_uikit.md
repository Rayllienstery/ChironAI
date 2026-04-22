# Core Data threading and UIKit integration

Platform: iOS
Framework: UIKit
MinOS: iOS 15
Difficulty: advanced
Concept Mode: all
RAG Strict: false

## Question

You use Core Data in a UIKit app with multiple contexts (main and background).
Explain:

- how to correctly use a main-queue context for UI and a background context for heavy work;
- how to merge changes from the background context back into the main context;
- how to avoid threading violations when passing managed objects between threads;
- best practices for keeping UITableView/UICollectionView in sync with Core Data changes.

## Expected Concepts

- NSManagedObjectContext
- main queue context
- background context
- merge changes
- threading violation

## RAG Requirement

The answer should align with Core Data concurrency documentation.

## Notes

Combines persistence and UIKit, a common Senior-level responsibility.

