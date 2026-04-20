# Trading Sentinel Copilot Guidance

This file documents the local agent playbook for this repository.

## How to invoke

Use plain chat commands in Copilot chat:

- Skill usage: "Use skill <skill-name> for <task>"
- Agent usage: "Use agent <agent-name>"

Examples:

- "Use skill systematic-debugging to diagnose this failing test"
- "Use skill design-taste-frontend to redesign Dashboard page"
- "Use agent CODE_AUDITOR"
- "Use agent tester"

## Installed Agents

### CODE_AUDITOR

- File: `.github/agents/CODE_AUDITOR.md`
- Purpose: Deep security, correctness, and financial-safety audit for all 3 containers
- Best for:
  - Cross-container logic audits
  - Trading safety rule validation
  - Known-quirk verification and critical bug hunts

### tester

- File: `.github/agents/tester.md`
- Purpose: End-to-end and container-level test generation and validation
- Best for:
  - Python/Node/Agent test creation
  - Integration and callback-flow tests
  - Guardrail and regression test coverage

## Installed Skills

### Existing local skill

- `emil-design-eng` -> `.github/skills/Designer_Emil.md`

### Superpowers skills (obra/superpowers)

- `brainstorming` -> `.github/skills/Brainstorming.md`
- `test-driven-development` -> `.github/skills/Test_Driven_Development.md`
- `systematic-debugging` -> `.github/skills/Systematic_Debugging.md`
- `writing-plans` -> `.github/skills/Writing_Plans.md`
- `executing-plans` -> `.github/skills/Executing_Plans.md`
- `verification-before-completion` -> `.github/skills/Verification_Before_Completion.md`
- `subagent-driven-development` -> `.github/skills/Subagent_Driven_Development.md`
- `dispatching-parallel-agents` -> `.github/skills/Dispatching_Parallel_Agents.md`
- `finishing-a-development-branch` -> `.github/skills/Finishing_Development_Branch.md`
- `receiving-code-review` -> `.github/skills/Receiving_Code_Review.md`
- `requesting-code-review` -> `.github/skills/Requesting_Code_Review.md`
- `using-git-worktrees` -> `.github/skills/Using_Git_Worktrees.md`
- `using-superpowers` -> `.github/skills/Using_Superpowers.md`
- `writing-skills` -> `.github/skills/Writing_Skills.md`

### Impeccable skill (pbakaus/impeccable)

- `impeccable` -> `.github/skills/Impeccable.md`
- Notes:
  - Imported with one-time `<post-update-cleanup>` block removed
  - Supports mode arguments from the skill itself: `craft`, `teach`, `extract`

### Taste skills (leonxlnx/taste-skill)

- `design-taste-frontend` -> `.github/skills/Taste_Skill.md`
- `full-output-enforcement` -> `.github/skills/Output_Skill.md`
- `gpt-taste` -> `.github/skills/GPT_TasteSkill.md`
- `redesign-existing-projects` -> `.github/skills/Redesign_Skill.md`
- `high-end-visual-design` -> `.github/skills/Soft_Skill.md`
- `minimalist-ui` -> `.github/skills/Minimalist_Skill.md`
- `industrial-brutalist-ui` -> `.github/skills/Brutalist_Skill.md`
- `stitch-design-taste` -> `.github/skills/Stitch_Skill.md`

## Quick command snippets

- Debug failing test:
  - "Use skill systematic-debugging to find root cause for this failure"
- Enforce TDD cycle:
  - "Use skill test-driven-development for this feature"
- Write implementation plan first:
  - "Use skill writing-plans for this requirement"
- Execute from existing plan:
  - "Use skill executing-plans for docs/...plan...md"
- Ask for strict code review:
  - "Use skill requesting-code-review on this change"
- Receive and apply review safely:
  - "Use skill receiving-code-review on this PR feedback"
- Frontend generation with strong style:
  - "Use skill impeccable craft <feature>"
  - "Use skill design-taste-frontend for this page"
  - "Use skill redesign-existing-projects for this existing UI"

## Current inventory count

- Agents: 2
- Skills: 24 total in `.github/skills` (23 imported in this session/request + 1 pre-existing `emil-design-eng`)
