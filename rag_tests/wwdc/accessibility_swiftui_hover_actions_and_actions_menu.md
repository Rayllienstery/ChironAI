# SwiftUI accessibility: hover overlays and actions menu

Platform: macOS
Framework: SwiftUI
MinOS: macOS 15
Difficulty: advanced
Rag Required: no
Concept Mode: all
RAG Strict: true

## Question

The SwiftUI accessibility WWDC session shows a macOS app where hovering over a trip image reveals extra actions (location, recording, rating).  
Explain:

- why such hover-only content can be hard to reach with VoiceOver and other assistive technologies;
- how to use SwiftUI accessibility APIs to extract actions from a hover overlay and expose them as custom actions on the main element (for example via an actions menu);
- how to append additional information like a rating to the main element’s label so that important details are announced together;
- general guidance from the session on ensuring that dynamic or hover-only content is reachable with accessibility technologies.

Describe how you would refactor the trip view so that VoiceOver users can access the same actions (location, recording, rating) without having to discover the hover interaction.

## Expected Concepts

- hover overlay
- accessibility actions
- actions menu
- rating in label
- VoiceOver navigation
- SwiftUI accessibility

## RAG Requirement

The answer should rely on the specific macOS trip example from the SwiftUI accessibility WWDC session.

## Notes

This test should make RAG retrieve WWDC content about hover overlays and accessibility actions.*** End Patch
