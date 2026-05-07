import { StateGraph, END, START } from '@langchain/langgraph';
import { AgentStateAnnotation } from './state.ts';
import { entryNode, microLogicNode, macro_structure_node, deepExplanation_node, errorNode, routeByIntent } from './nodes.ts';

/**
 * graph.ts
 * The orchestration layer defining the cyclic workflows.
 */

export function buildGraph() {
  const workflow = new StateGraph(AgentStateAnnotation)
    .addNode('entry', entryNode)
    .addNode('macro_structure', macro_structure_node)
    .addNode('micro_logic', microLogicNode)
    .addNode('deep_explanation', deepExplanation_node)
    .addNode('error_handler', errorNode);

  workflow.addEdge(START, 'entry');

  workflow.addConditionalEdges('entry', routeByIntent, {
    macro_structure: 'macro_structure',
    micro_logic: 'micro_logic',
    deep_explanation: 'deep_explanation',
    refactor: 'error_handler', // Placeholder for now
    error: 'error_handler',
  });

  workflow.addEdge('macro_structure', END);
  workflow.addEdge('micro_logic', END);
  workflow.addEdge('deep_explanation', END);
  workflow.addEdge('error_handler', END);

  return workflow.compile();
}

export const graph = buildGraph();
