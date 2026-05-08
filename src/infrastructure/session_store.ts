import Database from 'better-sqlite3';
import { v4 as uuidv4 } from 'uuid';
import { ProjectGraph } from '../types/project_graph.ts';
import crypto from 'crypto';

/**
 * session_store.ts
 * Lightweight key-value cache for LangGraph state hydration.
 * Prevents raw code from being serialized into the graph state.
 * Also provides a persistent graph cache keyed by workspace path.
 */
export class SessionStore {
  private db: Database.Database;

  constructor(dbPath: string = '.session_cache.db') {
    this.db = new Database(dbPath);
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS cache (
        key   TEXT PRIMARY KEY,
        value TEXT,
        ttl   INTEGER
      );
      CREATE TABLE IF NOT EXISTS graph_cache (
        workspace_hash TEXT PRIMARY KEY,
        graph_json     TEXT,
        indexed_at     INTEGER,
        node_count     INTEGER,
        edge_count     INTEGER
      );
    `);
    setInterval(() => this.evictExpired(), 5 * 60 * 1000).unref();
  }

  // ── Ephemeral key-value store (TTL-based) ─────────────────────────────────

  put(value: unknown, ttlSeconds: number = 3600): string {
    const key = uuidv4();
    const expiresAt = Math.floor(Date.now() / 1000) + ttlSeconds;
    this.db.prepare('INSERT OR REPLACE INTO cache (key, value, ttl) VALUES (?, ?, ?)').run(
      key, JSON.stringify(value), expiresAt
    );
    return key;
  }

  get(key: string): unknown | null {
    const now = Math.floor(Date.now() / 1000);
    const row = this.db.prepare('SELECT value FROM cache WHERE key = ? AND ttl > ?').get(key, now) as { value: string } | undefined;
    return row ? JSON.parse(row.value) : null;
  }

  evictExpired(): void {
    this.db.prepare('DELETE FROM cache WHERE ttl <= ?').run(Math.floor(Date.now() / 1000));
  }

  // ── Persistent graph cache (no TTL — survives server restarts) ────────────

  saveGraph(workspacePath: string, graph: ProjectGraph): void {
    const hash = crypto.createHash('sha1').update(workspacePath).digest('hex');
    this.db.prepare(`
      INSERT OR REPLACE INTO graph_cache (workspace_hash, graph_json, indexed_at, node_count, edge_count)
      VALUES (?, ?, ?, ?, ?)
    `).run(hash, JSON.stringify(graph), Date.now(), graph.nodes.length, graph.edges.length);
  }

  loadGraph(workspacePath: string): ProjectGraph | null {
    const hash = crypto.createHash('sha1').update(workspacePath).digest('hex');
    const row = this.db.prepare('SELECT graph_json FROM graph_cache WHERE workspace_hash = ?').get(hash) as { graph_json: string } | undefined;
    return row ? JSON.parse(row.graph_json) as ProjectGraph : null;
  }

  isGraphFresh(workspacePath: string, maxAgeMs: number = 3_600_000): boolean {
    const hash = crypto.createHash('sha1').update(workspacePath).digest('hex');
    const row = this.db.prepare('SELECT indexed_at FROM graph_cache WHERE workspace_hash = ?').get(hash) as { indexed_at: number } | undefined;
    return !!row && (Date.now() - row.indexed_at) < maxAgeMs;
  }
}

export const store = new SessionStore();
