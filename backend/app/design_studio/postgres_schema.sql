-- Proposed isolated Design Studio schema v1. Review and apply manually only
-- after provider, database, backup and migration ownership are approved.
-- Never run against Neo4j or an existing SQLite draft database.
BEGIN;
CREATE TABLE studio_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO studio_meta (key, value) VALUES ('schema_id', 'noordveld-design-studio-postgres-v1');
CREATE TABLE studio_drafts (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    spec_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX studio_drafts_owner ON studio_drafts(owner);
CREATE TABLE studio_projects (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    current_revision INTEGER NOT NULL CHECK (current_revision > 0)
);
CREATE INDEX studio_projects_owner ON studio_projects(owner);
CREATE TABLE studio_revisions (
    project_id TEXT NOT NULL REFERENCES studio_projects(id) ON DELETE RESTRICT,
    revision INTEGER NOT NULL CHECK (revision > 0),
    definition_json TEXT NOT NULL,
    actor TEXT NOT NULL,
    operation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (project_id, revision)
);
COMMIT;
