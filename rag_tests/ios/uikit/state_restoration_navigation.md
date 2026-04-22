# State restoration with UINavigationController

Platform: iOS
Framework: UIKit
MinOS: iOS 15
Difficulty: advanced
Concept Mode: all
RAG Strict: false

## Question

You want to support state restoration for a navigation-based app using `UINavigationController`.
Explain:

- how to assign restoration identifiers and classes to view controllers;
- how the restoration process recreates the navigation stack after relaunch;
- where to save and restore per-screen state safely in the lifecycle;
- pitfalls when view controllers depend on external coordinators or services during restoration.

## Expected Concepts

- state restoration
- UINavigationController
- restorationIdentifier
- restorationClass
- UIViewController lifecycle

## RAG Requirement

The answer should align with UIKit state restoration documentation.

## Notes

Focuses on more advanced UIKit behavior beyond basic lifecycle.

