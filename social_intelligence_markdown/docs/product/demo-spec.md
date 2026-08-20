# Reddit-First Demo Specification

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

The required demonstration is Reddit-first. X, LinkedIn and other networks are bonus connectors and must not be required for the core story.

## Demo script

1. Create or open a campaign with product context, audience, keywords, competitor terms, and promotion posture.

2. Run Reddit discovery. Show live progress and retrieval-source counts.

3. Open the Opportunity Inbox and show raw-candidate count versus relevant/high-priority count.

4. Select a high-value opportunity. Show source thread, scores, rationale, and recommended action.

5. Generate a response draft. Explain that the model may recommend no product mention despite high relevance.

6. Edit one phrase to demonstrate versioning. Approve the final exact text.

7. Launch the browser preparation flow. CUA navigates to the correct thread and fills the composer with the approved text, then stops before submit.

8. Return to the dashboard. Select an emerging theme built from several conversations.

9. Generate an original Reddit post and optional cross-channel variants. Generate an image or short video via Higgsfield.

10. Show the same campaign/opportunity from an MCP client and queue a draft for review, proving the headless/agent-native architecture.

## Demo fallback strategy

| **Failure**                           | **Fallback**                                                                                                   |
|---------------------------------------|----------------------------------------------------------------------------------------------------------------|
| Live Reddit search is blocked or slow | Use pre-discovered real URLs from the same day and run the fetch/extract path.                                 |
| Thread extraction is incomplete       | Show URL Context result, then CUA escalation for the exact thread.                                             |
| Browser session/login issue           | Use an isolated prepared demo browser profile; do not bypass access controls.                                  |
| Higgsfield generation is slow         | Show a queued job plus a previously generated asset from the same media brief while preserving job provenance. |
| Model output is weak                  | Use a saved labeled conversation and demonstrate regenerate/edit/review rather than hiding the failure.        |

## Demo success statement

A successful demo should make the following story obvious: one campaign produces a noisy set of Reddit conversations; the system reduces them to a small set of high-quality, explainable opportunities; the operator generates and edits a response; explicit approval is captured; CUA navigates to the correct Reddit composer and fills the exact approved content; the final submit remains under human control in the preferred demo mode.

The second wow moment is trend-to-content: select a recurring market pain, generate an original post and media brief, and create an image/video job through Higgsfield.
