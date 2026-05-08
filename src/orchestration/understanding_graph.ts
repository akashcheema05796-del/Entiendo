import { fileWalkerNode, dependencyAnalyzerNode, symbolExtractorNode, graphBuilderNode, UnderstandingState } from './understanding_nodes.ts';

export async function runUnderstandingAgent(state: UnderstandingState): Promise<void> {
  let current: UnderstandingState = { ...state };

  const nodes = [fileWalkerNode, dependencyAnalyzerNode, symbolExtractorNode, graphBuilderNode];

  for (const node of nodes) {
    const patch = await node(current);
    current = { ...current, ...patch };
    if (current.error) {
      console.error('[Understanding Agent] Error:', current.error);
      break;
    }
  }
}
