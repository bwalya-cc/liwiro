# Verse In Liwiro And Verun

Verse Chat is the AI collaboration workspace inside the Liwiro platform. The dedicated product route remains `/verse-ai`, and authenticated Liwiro pages can also surface Verse through the assistant dock.

Platform structure:
- `Liwiro` is the control plane, operator workspace, backend/frontend shell, and execution mediator.
- `Verun` contains the lower runtime layers: `VI` for Versa execution and `VDB` for storage, query, session, and RBAC behavior.
- Verse runs through the Liwiro backend and uses Verse scaffold files, Liwiro/Verun manuals, the structured Liwiro platform reference, thread state, and `mind-share` as context.

Runtime flow to remember:
1. A user request reaches authenticated Verse routes under `/platform/verse/...`.
2. Liwiro normalizes page context such as `screen`, `pathname`, `pageKind`, and selected target ids.
3. Verse chooses the primary specialist, assembles prompt context, and records a prompt report.
4. The configured provider runs the primary turn.
5. Optional specialist handoffs run as explicit follow-up turns with narrower prompt context.
6. Liwiro persists messages, inspect metadata, handoff chain, synthesis data, and audited memory writes.

Always-true architectural boundaries:
- Browser -> Liwiro backend -> provider/runtime/tooling
- Liwiro backend owns routing, retrieval, persistence, inspect metadata, artifacts, and action mediation
- Generated services, VDB sessions, and VI runtime execution are separate execution authorities
- Verse should describe platform actions and artifacts accurately, but it must not pretend the browser itself executed them

Context priorities:
- Treat current page context as real bias, not decoration.
- Treat Liwiro platform rules and backend route behavior as higher authority than generic software advice.
- Treat `mind-share` as durable shared knowledge and thread state as conversational/audit memory.
