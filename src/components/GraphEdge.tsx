import React from 'react';
import { GraphEdge as GEdge } from '../types/project_graph.ts';

interface GraphEdgeProps {
  edge: GEdge;
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  isHighlighted: boolean;
}

const EDGE_COLORS: Record<string, string> = {
  imports:    '#6366f1',
  calls:      '#10b981',
  inherits:   '#f59e0b',
  implements: '#8b5cf6',
  uses_type:  '#94a3b8',
  contains:   '#1e293b',
};

export default function GraphEdgeComp({ edge, sourceX, sourceY, targetX, targetY, isHighlighted }: GraphEdgeProps) {
  const color = EDGE_COLORS[edge.kind] ?? '#475569';
  const opacity = edge.kind === 'contains' ? 0.08 : isHighlighted ? 0.9 : 0.25;

  // Midpoint for label
  const mx = (sourceX + targetX) / 2;
  const my = (sourceY + targetY) / 2;

  return (
    <g>
      <line
        x1={sourceX} y1={sourceY} x2={targetX} y2={targetY}
        stroke={color}
        strokeWidth={isHighlighted ? 2 : edge.kind === 'contains' ? 0.5 : 1}
        strokeOpacity={opacity}
        strokeDasharray={edge.kind === 'uses_type' ? '4 2' : undefined}
      />
      {isHighlighted && edge.label && (
        <text x={mx} y={my - 4} fill={color} fontSize={8} textAnchor="middle" opacity={0.8}>
          {edge.label}
        </text>
      )}
    </g>
  );
}
