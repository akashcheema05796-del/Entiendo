import Database from 'better-sqlite3';
import { v4 as uuidv4 } from 'uuid';

/**
 * session_store.ts
 * Lightweight key-value cache for LangGraph state hydration.
 * Prevents raw code from being serialized into the graph state.
 */
export class SessionStore {
  private db: Database.Database;

  constructor(dbPath: string = '.session_cache.db') {
    this.db = new Database(dbPath);
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS cache (
        key TEXT PRIMARY KEY,
        value TEXT,
        ttl INTEGER
      )
    `);
  }

  put(value: any, ttlSeconds: number = 3600): string {
    const key = uuidv4();
    const expiresAt = Math.floor(Date.now() / 1000) + ttlSeconds;
    const stmt = this.db.prepare('INSERT OR REPLACE INTO cache (key, value, ttl) VALUES (?, ?, ?)');
    stmt.run(key, JSON.stringify(value), expiresAt);
    return key;
  }

  get(key: string): any | null {
    const now = Math.floor(Date.now() / 1000);
    const stmt = this.db.prepare('SELECT value FROM cache WHERE key = ? AND ttl > ?');
    const row = stmt.get(key, now) as { value: string } | undefined;
    return row ? JSON.parse(row.value) : null;
  }

  evictExpired(): void {
    const now = Math.floor(Date.now() / 1000);
    const stmt = this.db.prepare('DELETE FROM cache WHERE ttl <= ?');
    stmt.run(now);
  }
}

export const store = new SessionStore();
