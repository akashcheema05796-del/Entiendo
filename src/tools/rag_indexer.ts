import { QdrantClient } from '@qdrant/js-client-rest';
import { GoogleGenAI } from '@google/genai';
import { chunkFile } from './ast_chunker.ts';
import fs from 'fs';
import path from 'path';

const COLLECTION_PREFIX = 'entiendo_';
const VECTOR_SIZE = 768; // text-embedding-004 output dimension
const CODE_EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.jsx', '.py', '.go', '.rs', '.java', '.cpp', '.c', '.md', '.json']);
const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', '__pycache__', '.next', 'build']);

interface MemChunk {
  vector: number[];
  content: string;
  file: string;
}

function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  return denom === 0 ? 0 : dot / denom;
}

export class RagIndexer {
  private qdrant: QdrantClient;
  private genai: GoogleGenAI;
  private qdrantAvailable = false;

  // In-memory fallback store keyed by sessionId
  private memStore = new Map<string, MemChunk[]>();

  // Per-session indexing promise so deep_explanation can await it
  private indexingPromises = new Map<string, Promise<void>>();

  constructor() {
    this.qdrant = new QdrantClient({ url: process.env.QDRANT_URL || 'http://localhost:6333' });
    this.genai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY || '' });
  }

  private collectionName(sessionId: string): string {
    return `${COLLECTION_PREFIX}${sessionId.replace(/[^a-z0-9]/gi, '_').toLowerCase()}`;
  }

  private async checkQdrant(): Promise<boolean> {
    try {
      await this.qdrant.getCollections();
      this.qdrantAvailable = true;
      return true;
    } catch {
      this.qdrantAvailable = false;
      return false;
    }
  }

  // Returns a promise that resolves when indexing for this session is done.
  // Callers can await this before retrieving.
  waitForIndex(sessionId: string): Promise<void> {
    return this.indexingPromises.get(sessionId) ?? Promise.resolve();
  }

  indexRepo(
    repoPath: string,
    sessionId: string,
    onProgress?: (msg: string) => void
  ): Promise<boolean> {
    // Store the promise so retrieve() can wait on it
    let resolve!: () => void;
    const gate = new Promise<void>(r => { resolve = r; });
    this.indexingPromises.set(sessionId, gate);

    const work = this._indexRepo(repoPath, sessionId, onProgress).finally(resolve);
    return work;
  }

  private async _indexRepo(
    repoPath: string,
    sessionId: string,
    onProgress?: (msg: string) => void
  ): Promise<boolean> {
    const files = this.getCodeFiles(repoPath).slice(0, 60);
    onProgress?.(`[RAG] Indexing ${files.length} files...`);

    // Embed all chunks regardless of backend
    const chunks: { content: string; file: string; vector: number[] }[] = [];
    for (const filePath of files) {
      try {
        const content = fs.readFileSync(filePath, 'utf-8');
        const relativePath = path.relative(repoPath, filePath);
        const fileChunks = chunkFile(relativePath, content).slice(0, 8);
        for (const chunk of fileChunks) {
          const vector = await this.embed(chunk.content);
          if (vector) chunks.push({ content: chunk.content, file: relativePath, vector });
        }
      } catch { /* skip unreadable files */ }
    }

    // Always populate in-memory store as the guaranteed fallback
    this.memStore.set(sessionId, chunks);

    if (await this.checkQdrant()) {
      try {
        const collection = this.collectionName(sessionId);
        const existing = await this.qdrant.getCollections();
        if (existing.collections.some(c => c.name === collection)) {
          await this.qdrant.deleteCollection(collection);
        }
        await this.qdrant.createCollection(collection, {
          vectors: { size: VECTOR_SIZE, distance: 'Cosine' },
        });
        if (chunks.length > 0) {
          await this.qdrant.upsert(collection, {
            wait: true,
            points: chunks.map((c, i) => ({
              id: i + 1,
              vector: c.vector,
              payload: { content: c.content, file: c.file },
            })),
          });
        }
        onProgress?.(`[RAG] Indexed ${chunks.length} chunks into Qdrant.`);
        return true;
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        onProgress?.(`[RAG] Qdrant write failed (${message}) — using in-memory fallback.`);
      }
    } else {
      onProgress?.(`[RAG] Qdrant unavailable — using in-memory cosine search (${chunks.length} chunks).`);
    }

    return false;
  }

  async retrieve(query: string, sessionId: string, topK = 5): Promise<string[]> {
    const queryVec = await this.embed(query);
    if (!queryVec) return [];

    // Try Qdrant first
    if (this.qdrantAvailable) {
      try {
        const results = await this.qdrant.search(this.collectionName(sessionId), {
          vector: queryVec,
          limit: topK,
          with_payload: true,
        });
        const hits = results
          .filter(r => r.score > 0.4)
          .map(r => `// ${r.payload?.file}\n${r.payload?.content}`);
        if (hits.length > 0) return hits;
      } catch { /* fall through to memory */ }
    }

    // In-memory cosine fallback
    const store = this.memStore.get(sessionId);
    if (!store || store.length === 0) return [];

    return store
      .map(c => ({ score: cosineSimilarity(queryVec, c.vector), c }))
      .filter(x => x.score > 0.4)
      .sort((a, b) => b.score - a.score)
      .slice(0, topK)
      .map(x => `// ${x.c.file}\n${x.c.content}`);
  }

  private async embed(text: string): Promise<number[] | null> {
    try {
      const response = await this.genai.models.embedContent({
        model: 'text-embedding-004',
        contents: text.slice(0, 2048),
      });
      const values = (response as any).embeddings?.[0]?.values ?? (response as any).embedding?.values;
      return Array.isArray(values) ? values : null;
    } catch {
      return null;
    }
  }

  private getCodeFiles(dir: string): string[] {
    const results: string[] = [];
    const walk = (d: string) => {
      try {
        for (const entry of fs.readdirSync(d)) {
          if (SKIP_DIRS.has(entry)) continue;
          const full = path.join(d, entry);
          const stat = fs.statSync(full);
          if (stat.isDirectory()) walk(full);
          else if (CODE_EXTENSIONS.has(path.extname(entry))) results.push(full);
        }
      } catch { /* ignore permission errors */ }
    };
    walk(dir);
    return results;
  }
}

export const ragIndexer = new RagIndexer();
