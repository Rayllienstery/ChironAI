# Integrating UIKit views with UIViewRepresentable in SwiftUI

Platform: iOS
Framework: SwiftUI
MinOS: iOS 14
Difficulty: intermediate
Concept Mode: all
RAG Strict: false

## Question

You need to reuse a custom UIKit view (for example, a complex map view) inside a SwiftUI screen.
Explain:

- how to wrap the UIKit view using `UIViewRepresentable`;
- how to configure and update the view in `makeUIView` and `updateUIView`;
- how to propagate SwiftUI state changes into the UIKit view and send callbacks back to SwiftUI;
- common pitfalls (state duplication, threading, view lifecycle assumptions).

## Expected Concepts

- UIViewRepresentable
- makeUIView
- updateUIView
- bridging state
- callbacks

## RAG Requirement

The answer should align with SwiftUI documentation on UIKit integration.

## Notes

Tests practical knowledge of bridging old UIKit components into a SwiftUI world.

