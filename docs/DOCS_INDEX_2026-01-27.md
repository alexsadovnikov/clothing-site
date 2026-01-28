# Docs Index (as of 2026-01-27)

This folder is the **single source of truth** for deployed architecture and operational decisions.

## Canonical docs
| Doc | Purpose | Status |
|---|---|---|
| ARCHITECTURE.md | Overall infra + runtime view (edge → docker → monitoring) | Active |
| AI_ROADMAP.md | AI rollout plan and milestones | Active |
| ADR-001-imports-and-entrypoint.md | Python imports/entrypoint conventions and rationale | Active |
| ADR-003-ai-gateway.md | Decision: external AI gateway + provider switching | **New (2026-01-27)** |
| AI_INFRA_ARCHITECTURE_2026-01-27.md | Detailed AI infra + data-flow + config | **New (2026-01-27)** |

## Diagrams
| File | What it shows | Source |
|---|---|---|
| AI_INFRA_FLOW_2026-01-27.drawio | AI infra + request flow + trust boundaries | generated 2026-01-27 |
| voicecrm_clothing_infra_v15_neat.drawio | Infra V15 (edge + docker + monitoring) | existing |
| Data-flow diagrams.pdf | Diagram style reference (DFD) | existing |

## Naming & versioning rules
- Filenames include **date** when they reflect a production state: `*_YYYY-MM-DD.*`
- ADRs are immutable once accepted; changes become a **new ADR**.
- Diagrams must include:
  - boundaries (PUBLIC / HOST / INTERNAL docker)
  - ports and host bindings
  - auth headers/secrets ownership
  - data stores vs compute separation

## What changed on 2026-01-27 (AI)
- Added **AI Gateway** (EU VPS) + public domain `ai.voicecrm.online`
- Switched clothing-site to `AI_PROVIDER=gateway`
- Introduced `AI_GATEWAY_TIMEOUT_S`
- Standardized internal auth header: `X-AI-Internal-Token`
