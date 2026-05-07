import { v4 as uuidv4 } from 'uuid';

/**
 * ast_chunker.ts
 * Basic chunking logic (Simplified for demo)
 */

export interface CodeChunk {
  id: string;
  content: string;
  fileName: string;
  type: 'function' | 'class' | 'module';
  name: string;
}

export function chunkFile(fileName: string, content: string): CodeChunk[] {
  // Simplified chunking: in a real implementation we would use tree-sitter
  // to extract functions and classes with real metadata.
  
  const chunks: CodeChunk[] = [];
  
  // Split by double newlines for basic partitioning
  const parts = content.split(/\n\n+/);
  
  parts.forEach((part, i) => {
    chunks.push({
      id: uuidv4(),
      content: part,
      fileName,
      type: 'module',
      name: `${fileName}_chunk_${i}`
    });
  });

  return chunks;
}
