import { StateGraph, END, START } from '@langchain/langgraph';
import { CodingAgentStateAnnotation } from './state.ts';
import { explainNode, diagramNode, codeModifyNode, generateTestsNode, routeByTask } from './coding_nodes.ts';

export function buildCodingGraph() {
  const workflow = new StateGraph(CodingAgentStateAnnotation)
    .addNode('explain', explainNode)
    .addNode('diagram', diagramNode)
    .addNode('code_modify', codeModifyNode)
    .addNode('generate_tests', generateTestsNode);

  workflow.addConditionalEdges(START, routeByTask, {
    explain: 'explain',
    diagram: 'diagram',
    code_modify: 'code_modify',
    generate_tests: 'generate_tests',
  });

  workflow.addEdge('explain', END);
  workflow.addEdge('diagram', END);
  workflow.addEdge('code_modify', END);
  workflow.addEdge('generate_tests', END);

  return workflow.compile();
}

export const graph = buildCodingGraph();
