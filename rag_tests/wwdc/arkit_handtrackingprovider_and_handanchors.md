# ARKit hand tracking with HandTrackingProvider and HandAnchor

Platform: visionOS
Framework: ARKit
MinOS: visionOS 1.0
Difficulty: advanced
Rag Required: no
Concept Mode: all
RAG Strict: true

## Question

In \"Meet ARKit for spatial computing\" the presenters introduce **hand tracking** using `HandTrackingProvider` and `HandAnchor`.  
Explain:

- what `HandTrackingProvider` does and how you enable it in an ARKit session (polling vs asynchronous updates);
- what a `HandAnchor` contains: chirality (left/right), skeleton, joints, local vs root transforms, tracked flags;
- how you can use hand joints (for example, the index fingertip) to drive interactions like grabbing, pushing or colliding with entities;
- how the WWDC example uses fingertip colliders and scene colliders to let the user push cubes around in an immersive space.

Provide a high-level Swift-like example showing:

1. Creating a session with `HandTrackingProvider`.  
2. Querying the latest `HandAnchor` and extracting the index fingertip joint.  
3. Using that joint to position a collider or visual indicator.

## Expected Concepts

- HandTrackingProvider
- HandAnchor
- skeleton
- joints
- chirality
- fingertip collider

## RAG Requirement

The answer should rely on the WWDC ARKit spatial computing example that uses hand tracking and fingertip colliders to interact with cubes.

## Notes

This test targets WWDC ARKit content specifically about hand tracking and its data model.*** End Patch
