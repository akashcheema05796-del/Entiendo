import { describe, it, expect, beforeEach } from 'vitest';
import { SessionStore } from '../infrastructure/session_store.ts';

describe('SessionStore', () => {
  let store: SessionStore;

  beforeEach(() => {
    store = new SessionStore(':memory:');
  });

  it('stores and retrieves a value', () => {
    const key = store.put({ hello: 'world' });
    const value = store.get(key) as { hello: string };
    expect(value).not.toBeNull();
    expect(value.hello).toBe('world');
  });

  it('returns null for an unknown key', () => {
    expect(store.get('nonexistent-key')).toBeNull();
  });

  it('returns null for an already-expired entry', () => {
    const key = store.put('data', -1);
    expect(store.get(key)).toBeNull();
  });

  it('evicts expired entries', () => {
    const key = store.put('data', -1);
    store.evictExpired();
    expect(store.get(key)).toBeNull();
  });

  it('returns unique keys for each put', () => {
    const k1 = store.put('a');
    const k2 = store.put('b');
    expect(k1).not.toBe(k2);
  });

  it('stores different value types', () => {
    expect(store.get(store.put(42))).toBe(42);
    expect(store.get(store.put([1, 2, 3]))).toEqual([1, 2, 3]);
    expect(store.get(store.put(null))).toBeNull();
  });

  it('overwrites an existing key on duplicate', () => {
    const key = store.put('first');
    store.put('second');
    expect(store.get(key)).toBe('first');
  });
});
