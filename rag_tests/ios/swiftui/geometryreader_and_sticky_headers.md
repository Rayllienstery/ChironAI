# GeometryReader and sticky headers in SwiftUI

Platform: iOS
Framework: SwiftUI
MinOS: iOS 15
Difficulty: advanced
Concept Mode: all
RAG Strict: false

## Question

You implement a scrollable list with a header that shrinks and sticks to the top as the user scrolls.
Explain:

- how to use `GeometryReader` to read scroll offsets;
- how to avoid layout issues caused by GeometryReader taking all available space;
- how to combine it with `ScrollView` or `List` to create sticky headers;
- common pitfalls (coordSpace misuse, performance problems).

## Expected Concepts

- GeometryReader
- ScrollView
- coordinateSpace
- sticky header
- layout issues

## RAG Requirement

The answer should align with SwiftUI documentation and recommended patterns for GeometryReader.

## Notes

Tests nuanced understanding of GeometryReader and custom layouts in SwiftUI.

