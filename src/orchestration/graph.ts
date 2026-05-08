import { StateGraph, END, START } from '@langchain/langgraph';
import { AgentStateAnnotation } from './state.ts';
import { entryNode, microLogicNode, diagramNode, macro_structure_node, deepExplanation_node, refactorNode, testNode, errorNode, routeByIntent } from './nodes.ts';

/**
 * graph.ts
 * The orchestration layer defining the cyclic workflows.
 */

export function buildGraph() {
  const workflow = new StateGraph(AgentStateAnnotation)
    .addNode('entry', entryNode)
    .addNode('macro_structure', macro_structure_node)
    .addNode('micro_logic', microLogicNode)
    .addNode('diagram', diagramNode)
    .addNode('deep_explanation', deepExplanation_node)
    .addNode('refactor', refactorNode)
    .addNode('test', testNode)
    .addNode('error_handler', errorNode);

  workflow.addEdge(START, 'entry');

  workflow.addConditionalEdges('entry', routeByIntent, {
    macro_structure: 'macro_structure',
    micro_logic: 'micro_logic',
    diagram: 'diagram',
    deep_explanation: 'deep_explanation',
    refactor: 'refactor',
    test: 'test',
    error: 'error_handler',
  });

  workflow.addEdge('macro_structure', END);
  workflow.addEdge('micro_logic', END);
  workflow.addEdge('diagram', END);
  workflow.addEdge('deep_explanation', END);
  workflow.addEdge('refactor', END);
  workflow.addEdge('test', END);
  workflow.addEdge('error_handler', END);

  return workflow.compile();
}

export const graph = buildGraph();
