# 12 - Config and Pricing Reference

This document covers static config assets and runtime configuration behavior.

## Static Config Files

## `config/pricing_registry.json`

Purpose:
- Central pricing reference used by observability cost estimation and aggregation paths.

Used by:
- observability pricing/cost services in `modules/observability/services/*`.

Operational notes:
- Keep pricing entries consistent with model/service identifiers used in runtime diagnostics.
- Update with version control and include effective date in changelog/commit.

---

## Runtime Configuration (`core/config.py`)

Primary behavior:
- Loads settings from environment variables and `.env`.
- Exposes typed fields and derived path properties.
- Uses a cached singleton (`get_settings()`).

## Major setting groups

App and API:
- app name/env/debug/host/port
- API prefix
- CORS origins

Storage:
- local storage root
- per-domain directory names (workflow/documents/templates/outputs/executions/logs)

Azure OpenAI:
- endpoint, key, API version
- chat/reasoning/embedding deployments

Azure Document Intelligence:
- endpoint and key

Azure AI Search:
- endpoint, key, index name, vector field

Azure Blob Storage:
- connection/account URL
- container name
- storage root prefix

## Derived runtime paths

- storage root path
- workflow runs path
- documents path
- templates path
- outputs path
- executions path
- logs path

## Configuration Governance Checklist

- Never commit real secrets to version control.
- Keep `.env.example` aligned with required settings.
- Validate readiness endpoint after config changes.
- Confirm cloud credentials and index/container names match target environment.

## Recommended Environment Profiles

- `local` - file-based local run + optional cloud integrations
- `staging` - full cloud integrations and realistic payloads
- `production` - hardened keys, strict observability, controlled change management
