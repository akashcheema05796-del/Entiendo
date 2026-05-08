import { QdrantClient } from '@qdrant/js-client-rest';
import { GoogleGenAI } from '@google/genai';
import { chunkFile } from './ast_chunker.ts';
import fs from 'fs';
import path from 'path';

const COLLECTION_PREFIX = 'entiendo_';
const VECTOR_SIZE = 768; // text-embedding-004 output dimension
const CODE_EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.jsx', '.py', '.go', '.rs', '.java', '.cpp', '.c', '.md', '.json']);
const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', '__pycache__', '.next', 'build']);

export class RagIndexer {
  private qdrant: QdrantClient;
  private genai: GoogleGenAI;
  private available = false;

  constructor() {
    this.qdrant = new QdrantClient({ url: process.env.QDRANT_URL || 'http://localhost:6333' });
    this.genai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY || '' });
  }

  private collectionName(sessionId: string): string {
    return `${COLLECTION_PREFIX}${sessionId.replace(/[^a-z0-9]/gi, '_').toLowerCase()}`;
  }

  async checkAvailability(): Promise<boolean> {
    try {
      await this.qdrant.getCollections();
      this.available = true;
      return true;
    } catch {
      this.available = false;
      return false;
    }
  }

  async indexRepo(
    repoPath: string,
    sessionId: string,
    onProgress?: (msg: string) => void
  ): Promise<boolean> {
    if (!(await this.checkAvailability())) {
      onProgress?.('[RAG] Qdrant unavailable — skipping index. Using direct LLM fallback.');
      return false;
    }

    const collection = this.collectionName(sessionId);

    try {
      const existing = await this.qdrant.getCollections();
      if (existing.collections.some(c => c.name === collection)) {
        await this.qdrant.deleteCollection(collection);
      }
      await this.qdrant.createCollection(collection, {
        vectors: { size: VECTOR_SIZE, distance: 'Cosine' },
      });

      const files = this.getCodeFiles(repoPath).slice(0, 60);
      onProgress?.(`[RAG] Indexing ${files.length} files into vector store...`);

      const points: { id: number; vector: number[]; payload: Record<string, string> }[] = [];
      let pointId = 1;

      for (const filePath of files) {
        try {
          const content = fs.readFileSync(filePath, 'utf-8');
          const relativePath = path.relative(repoPath, filePath);
          const chunks = chunkFile(relativePath, content).slice(0, 8);

          for (const chunk of chunks) {
            const vector = await this.embed(chunk.content);
            if (vector) {
              points.push({
                id: pointId++,
                vector,
                payload: { content: chunk.content, file: relativePath, name: chunk.name },
              });
            }
          }
        } catch { /* skip unreadable files */ }
      }

      if (points.length > 0) {
        await this.qdrant.upsert(collection, { wait: true, points });
      }

      onProgress?.(`[RAG] Indexed ${points.length} chunks. Semantic search ready.`);
      return true;
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      onProgress?.(`[RAG] Indexing error: ${message}`);
      return false;
    }
  }

  async retrieve(query: string, sessionId: string, topK = 5): Promise<string[]> {
    if (!this.available) return [];

    const collection = this.collectionName(sessionId);
    try {
      const vector = await this.embed(query);
      if (!vector) return [];

      const results = await this.qdrant.search(collection, {
        vector,
        limit: topK,
        with_payload: true,
      });

      return results
        .filter(r => r.score > 0.4)
        .map(r => `// ${r.payload?.file}\n${r.payload?.content}`);
    } catch {
      return [];
    }
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
