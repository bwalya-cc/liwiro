# Risks and Open Questions

> Use this file to preserve unresolved issues across threads.

## Entry Template

### [Risk or Question]
- Date:
- Raised By:
- Category:
- Description:
- Impact:
- Suggested Follow-Up:
- Related Thread:

### 2026-03-22T23:01:24.376502+00:00 | Ananse | Text | Medium confidence
Basis: Initial zshop architecture review
Thread: e8292a89ae5f488e8c6af3035438d95f
Content Type: text
Content:
### Risks
- **Unoptimized Media**: Large raw image uploads will increase storage costs and degrade frontend performance if not resized/optimized at the edge or during ingest.
- **Egress Costs**: Serving images directly from an object store origin without a CDN will lead to unpredictable and potentially high bandwidth costs.

### Open Questions
- What is the expected volume of images per collection?
- Do images require access control (private) or are they all public-facing?
