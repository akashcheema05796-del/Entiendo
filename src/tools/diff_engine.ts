/**
 * diff_engine.ts
 * Implements architectural fix for Gap 2 (Diff Engine Fragility).
 * Uses SEARCH/REPLACE blocks for deterministic code modification.
 */

const BLOCK_PATTERN = /<<<<\n([\s\S]*?)\n====\n([\s\S]*?)\n>>>>/g;

export interface DiffResult {
  success: boolean;
  message: string;
}

export function applySearchReplace(source: string, llmOutput: string): { modified: string, appliedBlocks: number, error?: string } {
  const blocks = Array.from(llmOutput.matchAll(BLOCK_PATTERN));
  
  if (blocks.length === 0) {
    return { modified: source, appliedBlocks: 0, error: 'No SEARCH/REPLACE blocks found in output.' };
  }

  let modified = source;
  for (let i = 0; i < blocks.length; i++) {
    const [_, searchText, replaceText] = blocks[i];
    
    if (!modified.includes(searchText)) {
      return { modified: source, appliedBlocks: 0, error: `Block ${i + 1}: SEARCH text not found in source exactly.` };
    }
    
    // Apply only the first occurrence for safety, as per plan (Aider style)
    modified = modified.replace(searchText, replaceText);
  }

  return { modified, appliedBlocks: blocks.length };
}
