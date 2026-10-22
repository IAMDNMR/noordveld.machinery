-- Apply explicitly after postgres_schema.sql in the isolated Studio database.
-- Existing packages and test runs are never replaced by this migration.
BEGIN;
CREATE TABLE studio_releases (
    owner TEXT NOT NULL,
    project TEXT NOT NULL REFERENCES studio_projects(id) ON DELETE RESTRICT,
    id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    created TEXT NOT NULL,
    actor TEXT NOT NULL,
    archive_sha256 TEXT NOT NULL,
    archive BYTEA NOT NULL,
    summary TEXT NOT NULL,
    PRIMARY KEY(owner,project,id)
);
CREATE TABLE studio_release_tests (
    owner TEXT NOT NULL,
    project TEXT NOT NULL,
    release TEXT NOT NULL,
    id TEXT PRIMARY KEY,
    actor TEXT NOT NULL,
    started TEXT NOT NULL,
    finished TEXT,
    status TEXT NOT NULL,
    result TEXT,
    FOREIGN KEY(owner,project,release) REFERENCES studio_releases(owner,project,id) ON DELETE RESTRICT
);
CREATE INDEX studio_release_history ON studio_releases(owner,project,created);
CREATE INDEX studio_release_test_history ON studio_release_tests(owner,project,release,started);
INSERT INTO studio_meta(key,value) VALUES ('release_schema_id','studio-releases-v1');
COMMIT;
