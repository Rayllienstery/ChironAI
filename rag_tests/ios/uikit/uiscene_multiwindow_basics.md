# UIScene and multiwindow basics for UIKit apps

Platform: iOS
Framework: UIKit
MinOS: iOS 13
Difficulty: intermediate
Concept Mode: all
RAG Strict: false

## Question

You migrate an older single-window UIKit app to use `UIScene` and support multiple windows
on iPadOS. Explain:

- how `UISceneDelegate` and `UIWindowScene` fit into the app lifecycle;
- how to set up the initial window and root view controller per scene;
- how to handle state restoration when multiple scenes are active;
- pitfalls when sharing global singletons across scenes.

## Expected Concepts

- UIScene
- UIWindowScene
- UISceneDelegate
- multiwindow
- app lifecycle

## RAG Requirement

The answer should align with Apple documentation on scenes and multiwindow support.

## Notes

Tests knowledge of modern UIKit app structure beyond the legacy AppDelegate-only model.

