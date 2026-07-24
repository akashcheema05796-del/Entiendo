-- Document index — claimed by node `state.doc_index`.
-- Illustrative DDL for the greenfield demo. A `state` node claims the artifacts
-- that define the store (schema, migrations), not the data rows themselves.

CREATE TABLE doc_chunks (
    id         TEXT PRIMARY KEY,
    doc_id     TEXT NOT NULL,
    text       TEXT NOT NULL,
    embedding  BLOB NOT NULL          -- invariant: never null
);

CREATE INDEX doc_chunks_by_doc ON doc_chunks (doc_id);
