import { describe, it, expect } from 'vitest';
import { applySearchReplace } from '../tools/diff_engine.ts';

describe('applySearchReplace', () => {
  it('applies a single block', () => {
    const source = 'const x = 1;\nconst y = 2;';
    const llmOutput = '<<<<\nconst x = 1;\n====\nconst x = 10;\n>>>>';
    const { modified, appliedBlocks, error } = applySearchReplace(source, llmOutput);
    expect(error).toBeUndefined();
    expect(appliedBlocks).toBe(1);
    expect(modified).toBe('const x = 10;\nconst y = 2;');
  });

  it('applies multiple blocks sequentially', () => {
    const source = 'a\nb\nc';
    const llmOutput = '<<<<\na\n====\nX\n>>>>\n<<<<\nb\n====\nY\n>>>>';
    const { modified, appliedBlocks } = applySearchReplace(source, llmOutput);
    expect(appliedBlocks).toBe(2);
    expect(modified).toBe('X\nY\nc');
  });

  it('returns error when no blocks found', () => {
    const { error, appliedBlocks } = applySearchReplace('source', 'no blocks here');
    expect(error).toBe('No SEARCH/REPLACE blocks found in output.');
    expect(appliedBlocks).toBe(0);
  });

  it('returns error when search text not found in source', () => {
    const source = 'const x = 1;';
    const llmOutput = '<<<<\nconst z = 99;\n====\nconst z = 100;\n>>>>';
    const { error, appliedBlocks } = applySearchReplace(source, llmOutput);
    expect(error).toBeTruthy();
    expect(appliedBlocks).toBe(0);
  });

  it('returns original source unchanged on error', () => {
    const source = 'original content';
    const llmOutput = '<<<<\nnot found\n====\nreplacement\n>>>>';
    const { modified } = applySearchReplace(source, llmOutput);
    expect(modified).toBe(source);
  });
});
