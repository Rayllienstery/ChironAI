# ARKit world tracking: WorldTrackingProvider and WorldAnchor

Platform: visionOS
Framework: ARKit
MinOS: visionOS 1.0
Difficulty: intermediate
Rag Required: no
Concept Mode: all
RAG Strict: true

## Question

In the WWDC session \"Meet ARKit for spatial computing\" Apple explains the new ARKit architecture based on sessions, data providers and anchors.  
Explain:

- what `WorldTrackingProvider` is responsible for and how it fits into the session + data provider model;
- what a `WorldAnchor` represents, how it differs from unanchored content and how ARKit persists world anchors across launches and locations;
- how ARKit handles maps per physical location and what happens when you move between spaces (e.g. home vs office);
- how to safely use world tracking data when doing your own rendering (Device pose vs anchors).

Provide a short conceptual example (pseudocode or Swift) that:

1. Creates a session with `WorldTrackingProvider`.  
2. Adds a `WorldAnchor` at a position relative to the app origin.  
3. Explains what happens to that anchor when the app relaunches in the same physical location.

## Expected Concepts

- WorldTrackingProvider
- WorldAnchor
- ARKit session
- data providers
- maps per location
- persistence of anchors

## RAG Requirement

The answer should be based on the WWDC \"Meet ARKit for spatial computing\" session, not just generic ARKit docs.

## Notes

This test is aimed at selecting WWDC ARKit content about world tracking and persistent anchors.*** End Patch
