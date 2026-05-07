import { StateGraph, END, START } from '@langchain/langgraph';
import { AgentStateAnnotation } from './state.ts';
import { entryNode, microLogicNode, errorNode, routeByIntent } from './nodes.ts';

/**
 * graph.ts
 * The orchestration layer defining the cyclic workflows.
 */

export function buildGraph() {
  const workflow = new StateGraph(AgentStateAnnotation)
    .addNode('entry', entryNode)
    .addNode('micro_logic', microLogicNode)
    .addNode('error', errorNode);

  workflow.addEdge(START, 'entry');

  workflow.addConditionalEdges('entry', routeByIntent, {
    macro_structure: 'error', // Placeholder
    micro_logic: 'micro_logic',
    deep_explanation: 'error', // Placeholder
    refactor: 'error', // Placeholder
    error: 'error',
  });

  workflow.addEdge('micro_logic', END);
  workflow.addEdge('error', END);

  return workflow.compile();
}

export const graph = buildGraph();
