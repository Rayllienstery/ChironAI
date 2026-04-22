# ARKit scene reconstruction vs plane detection

Platform: visionOS
Framework: ARKit
MinOS: visionOS 1.0
Difficulty: intermediate
Rag Required: no
Concept Mode: all
RAG Strict: true

## Question

The WWDC ARKit spatial computing session compares **plane detection** and **scene reconstruction**.  
Explain:

- what `PlaneDetectionProvider` and `PlaneAnchor` give you (alignments, semantic classifications, common use cases like simple physics or placing content on tables/floors);
- what `SceneReconstructionProvider` and `MeshAnchor` provide instead (polygonal meshes with per-face classifications) and when you should use them;
- how classifications differ between planes and meshes and what types of surfaces/objects can be detected;
- performance/complexity trade-offs mentioned in the session when choosing between plane detection and full scene reconstruction.

Give practical guidance for a developer deciding whether to rely only on plane detection or to enable scene reconstruction for a mixed-reality app.

## Expected Concepts

- PlaneDetectionProvider
- PlaneAnchor
- SceneReconstructionProvider
- MeshAnchor
- semantic classification
- scene geometry

## RAG Requirement

The answer should be grounded in the WWDC ARKit spatial computing session that discusses plane detection vs scene reconstruction.

## Notes

This test is intended to trigger WWDC ARKit content about scene understanding APIs.*** End Patch
