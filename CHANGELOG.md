# Changelog

## [v0.5.0] — 2026-01-18

### 🚨 Breaking (internal)
- Products primary key switched to `id_uuid` (UUID)
- Legacy `products.id` column fully removed
- All relations migrated to UUID-only model

### ✅ Added
- Stable UUID-based product model
- Clean API contracts using UUID identifiers only
- Deterministic Alembic migrations for PK transition
- Worker and background jobs aligned with UUID model

### 🔧 Changed
- ORM models synchronized with actual DB schema
- Search, jobs, queueing, and state machine updated
- Removed legacy compatibility paths

### 🧹 Removed
- Legacy product ID usage
- Temporary migration code
- Obsolete DB indexes and constraints

### 🧠 Notes
This release freezes the database schema and establishes
a stable foundation for future features (events, search,
ACL, multi-tenant support).