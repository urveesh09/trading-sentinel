# AGENTS.md — Trading Sentinel Workflow

## IMPORTANT: Production and Dev are separate working copies

**`C:\Users\Urveesh\Desktop\Production_Trading-sentinel` is the PRODUCTION working copy.**

**`C:\Users\Urveesh\Desktop\trading-sentinel` is the DEV working copy.**

These two folders represent different branches/environments. Keep this distinction clear at all times:

- **Production is not to be edited directly.** Do not implement fixes, features, refactors, experiments, configuration changes, or other code changes in the Production folder.
- **All requested changes must be made in the Dev folder** (`C:\Users\Urveesh\Desktop\trading-sentinel`).
- Dev will usually be ahead of Production, or at least on par with it.
- Production is updated from Dev on a daily basis **through GitHub only**. Changes should flow through the normal GitHub commit/push/PR/merge workflow rather than direct edits or ad-hoc copying into the Production folder.

## Which folder to use for each request

### When asked to assess Sentinel performance

Inspect the logs and runtime evidence from the **Production** working copy:

`C:\Users\Urveesh\Desktop\Production_Trading-sentinel`

Performance assessment must be based on Production logs and Production behavior, because that is the live/operational version being evaluated. Do not use Dev logs as a substitute unless explicitly requested.

### When asked to make changes

Make the changes in the **Dev** working copy:

`C:\Users\Urveesh\Desktop\trading-sentinel`

Implement, test, and validate changes in Dev first. Do not modify the Production working copy directly. Once changes are ready, they are promoted to Production through GitHub as part of the daily update process.

## Default operating rule

**Assess Production. Change Dev. Promote through GitHub. Never edit Production directly.**

If a request appears to require a direct Production edit, stop and clarify the intended GitHub-based promotion path before making that change.

## 5.6 Sol delegation and supervision

When the user commands **5.6 Sol** to do something, 5.6 Sol's primary responsibility is to coordinate the work efficiently:

- **Spin up 5.6 Terra and 5.6 Luna subagents** to perform the hard labour and execution-heavy parts of the task.
- **5.6 Sol supervises the subagents**, breaks the task into clear assignments, and makes the overall plan.
- **5.6 Sol researches when asked** and supplies the subagents with the relevant direction or context.
- **5.6 Sol reviews and double-checks the subagents' work** and makes any corrections it believes are needed before considering the task complete.
- Use this delegation model to avoid wasting unnecessary tokens while maintaining high-quality, independently checked results.

The intended workflow is: **5.6 Sol plans and supervises; 5.6 Terra and 5.6 Luna execute the hard labour; 5.6 Sol verifies, corrects, and delivers the final result.**
