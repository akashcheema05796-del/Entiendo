import React from 'react';
import { GraphNode as GNode, NodeKind } from '../types/project_graph.ts';

interface GraphNodeProps {
  node: GNode;
  isSelected: boolean;
  isHovered: boolean;
  onClick: (e: React.MouseEvent) => void;
  onDoubleClick: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

const LANG_COLORS: Record<string, string> = {
  typescript:  '#6366f1',
  javascript:  '#f59e0b',
  python:      '#f59e0b',
  go:          '#06b6d4',
  rust:        '#ef4444',
  java:        '#f97316',
  markdown:    '#10b981',
  json:        '#94a3b8',
  yaml:        '#94a3b8',
  toml:        '#94a3b8',
  directory:   '#475569',
  unknown:     '#334155',
};

function nodeRadius(node: GNode): number {
  if (node.kind === 'directory') return 18;
  if (node.kind === 'function' || node.kind === 'class' || node.kind === 'interface') return 8;
  return Math.min(Math.log(node.loc + 1) * 3 + 8, 28);
}

function NodeShape({ node, color, r }: { node: GNode; color: string; r: number }) {
  switch (node.kind) {
    case 'directory':
      return <rect x={-r} y={-r} width={r * 2} height={r * 2} rx={4} fill={`${color}22`} stroke={`${color}88`} strokeWidth={1.5} />;
    case 'class':
      return <polygon points={`0,${-r} ${r * 0.87},${r * 0.5} ${-r * 0.87},${r * 0.5}`} fill={`${color}22`} stroke={`${color}88`} strokeWidth={1.5} />;
    case 'interface':
      return <polygon points={`0,${-r} ${r},0 0,${r} ${-r},0`} fill={`${color}22`} stroke={`${color}88`} strokeWidth={1.5} />;
    case 'function':
      return <circle r={r} fill={`${color}22`} stroke={`${color}88`} strokeWidth={1} />;
    default:
      return <circle r={r} fill={`${color}18`} stroke={`${color}66`} strokeWidth={1.5} />;
  }
}

export default function GraphNodeComp({ node, isSelected, isHovered, onClick, onDoubleClick, onMouseEnter, onMouseLeave }: GraphNodeProps) {
  const color = LANG_COLORS[node.language] ?? '#6366f1';
  const r = nodeRadius(node);
  const showLabel = isHovered || isSelected || node.kind === 'directory';

  return (
    <g
      transform={`translate(${node.x ?? 0},${node.y ?? 0})`}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      style={{ cursor: 'pointer' }}
    >
      {/* Selection glow */}
      {isSelected && <circle r={r + 6} fill="none" stroke={color} strokeWidth={2} opacity={0.6} />}
      {isSelected && <circle r={r + 10} fill="none" stroke={color} strokeWidth={1} opacity={0.2} />}

      <NodeShape node={node} color={color} r={r} />

      {/* Label */}
      {showLabel && (
        <text
          y={r + 12}
          textAnchor="middle"
          fill="white"
          fontSize={9}
          fontFamily="monospace"
          fontWeight={isSelected ? 'bold' : 'normal'}
          opacity={0.9}
          style={{ pointerEvents: 'none', userSelect: 'none' }}
        >
          {node.label.length > 20 ? node.label.slice(0, 18) + '…' : node.label}
        </text>
      )}
    </g>
  );
}
