import React, { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { GraphNode as GNode, GraphEdge as GEdge, ProjectGraph } from '../types/project_graph.ts';
import GraphNodeComp from './GraphNode.tsx';
import GraphEdgeComp from './GraphEdge.tsx';

interface GraphCanvasProps {
  graph: ProjectGraph;
  selectedNodeIds: Set<string>;
  onNodeClick: (nodeId: string, multi: boolean) => void;
  onNodeDoubleClick: (node: GNode) => void;
  width: number;
  height: number;
}

interface NodeState {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  fixed: boolean;
}

const REPULSION = 3000;
const SPRING_LENGTH = 120;
const SPRING_K = 0.05;
// Tighter orbit for contains edges (symbol children orbiting their parent file)
const ORBIT_SPRING_LENGTH = 50;
const ORBIT_SPRING_K = 0.18;
const DAMPING = 0.85;
const CENTER_GRAVITY = 0.008;
const MAX_ITER = 350;

const SYMBOL_KINDS = new Set(['function', 'class', 'interface', 'variable']);

export default function GraphCanvas({ graph, selectedNodeIds, onNodeClick, onNodeDoubleClick, width, height }: GraphCanvasProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });
  const [isDraggingCanvas, setIsDraggingCanvas] = useState(false);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const transformRef = useRef(transform);
  transformRef.current = transform;

  // Node physics state (mutable ref for perf — not React state)
  const physicsRef = useRef<Map<string, NodeState>>(new Map());
  const rafRef = useRef<number>(0);
  const iterRef = useRef(0);
  const [, forceRender] = useState(0);

  // Derived: which nodes are expanded (have symbol children)
  const expandedParentIds = useMemo(() => {
    const childIds = new Set(
      graph.edges.filter(e => e.kind === 'contains').map(e => e.target)
    );
    return new Set(
      graph.edges
        .filter(e => e.kind === 'contains' && SYMBOL_KINDS.has(
          graph.nodes.find(n => n.id === e.target)?.kind ?? ''
        ))
        .map(e => e.source)
    );
  }, [graph.edges, graph.nodes]);

  // Initialize physics from graph nodes
  useEffect(() => {
    const cx = width / 2;
    const cy = height / 2;
    const existing = physicsRef.current;
    const newMap = new Map<string, NodeState>();

    for (const node of graph.nodes) {
      const prev = existing.get(node.id);
      newMap.set(node.id, prev ?? {
        id: node.id,
        x: node.x ?? cx + (Math.random() - 0.5) * 400,
        y: node.y ?? cy + (Math.random() - 0.5) * 400,
        vx: 0, vy: 0, fixed: false,
      });
    }

    physicsRef.current = newMap;
    iterRef.current = 0;
  }, [graph.nodes.length, width, height]);

  // Force simulation loop
  useEffect(() => {
    const nodes = graph.nodes;
    const containsEdges = graph.edges.filter(e => e.kind === 'contains');
    const semanticEdges = graph.edges.filter(e => e.kind !== 'contains');

    const tick = () => {
      if (iterRef.current >= MAX_ITER) return;
      iterRef.current++;

      const physics = physicsRef.current;
      const cx = width / 2;
      const cy = height / 2;

      const nodeList = Array.from(physics.values());
      const limit = Math.min(nodeList.length, 100);

      // Repulsion — reduced between child nodes in the same orbit group
      for (let i = 0; i < limit; i++) {
        for (let j = i + 1; j < limit; j++) {
          const a = nodeList[i], b = nodeList[j];
          const dx = a.x - b.x || 0.1;
          const dy = a.y - b.y || 0.1;
          const dist2 = dx * dx + dy * dy;
          if (dist2 === 0) continue;
          // Reduce repulsion between close sibling symbol nodes
          const repulsion = dist2 < 1000 ? REPULSION * 0.3 : REPULSION;
          const force = repulsion / dist2;
          const fx = force * dx / Math.sqrt(dist2);
          const fy = force * dy / Math.sqrt(dist2);
          if (!a.fixed) { a.vx += fx; a.vy += fy; }
          if (!b.fixed) { b.vx -= fx; b.vy -= fy; }
        }
      }

      // Contains edges: tight orbit spring (symbol child stays near parent file)
      for (const edge of containsEdges) {
        const a = physics.get(edge.source), b = physics.get(edge.target);
        if (!a || !b) continue;
        const dx = b.x - a.x, dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (dist - ORBIT_SPRING_LENGTH) * ORBIT_SPRING_K;
        const fx = force * dx / dist, fy = force * dy / dist;
        if (!a.fixed) { a.vx += fx; a.vy += fy; }
        if (!b.fixed) { b.vx -= fx; b.vy -= fy; }
      }

      // Semantic edges: regular spring
      for (const edge of semanticEdges) {
        const a = physics.get(edge.source), b = physics.get(edge.target);
        if (!a || !b) continue;
        const dx = b.x - a.x, dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (dist - SPRING_LENGTH) * SPRING_K;
        const fx = force * dx / dist, fy = force * dy / dist;
        if (!a.fixed) { a.vx += fx; a.vy += fy; }
        if (!b.fixed) { b.vx -= fx; b.vy -= fy; }
      }

      // Damping + center gravity + integrate
      for (const n of nodeList) {
        if (n.fixed) continue;
        n.vx += (cx - n.x) * CENTER_GRAVITY;
        n.vy += (cy - n.y) * CENTER_GRAVITY;
        n.vx *= DAMPING;
        n.vy *= DAMPING;
        n.x += n.vx;
        n.y += n.vy;
      }

      forceRender(v => v + 1);
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [graph.nodes.length, graph.edges.length, width, height]);

  // Node drag
  const draggingNode = useRef<string | null>(null);

  const handleNodeMouseDown = useCallback((nodeId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    draggingNode.current = nodeId;
    const p = physicsRef.current.get(nodeId);
    if (p) p.fixed = true;
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (draggingNode.current) {
      const rect = e.currentTarget.getBoundingClientRect();
      const p = physicsRef.current.get(draggingNode.current);
      if (p) {
        p.x = (e.clientX - rect.left - transformRef.current.x) / transformRef.current.scale;
        p.y = (e.clientY - rect.top - transformRef.current.y) / transformRef.current.scale;
        p.vx = 0; p.vy = 0;
      }
      forceRender(v => v + 1);
    } else if (isDraggingCanvas && dragStart.current) {
      setTransform(t => ({ ...t, x: t.x + e.movementX, y: t.y + e.movementY }));
    }
  }, [isDraggingCanvas]);

  const handleMouseUp = useCallback(() => {
    draggingNode.current = null;
    setIsDraggingCanvas(false);
    dragStart.current = null;
  }, []);

  const handleCanvasMouseDown = useCallback((e: React.MouseEvent) => {
    setIsDraggingCanvas(true);
    dragStart.current = { x: e.clientX, y: e.clientY };
  }, []);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    setTransform(t => ({ ...t, scale: Math.min(Math.max(t.scale * factor, 0.2), 5) }));
  }, []);

  const getPos = (id: string) => physicsRef.current.get(id) ?? { x: 0, y: 0 };

  const visibleIds = new Set(graph.nodes.map(n => n.id));
  const visibleEdges = graph.edges.filter(e => visibleIds.has(e.source) && visibleIds.has(e.target));

  // Separate render layers: structural edges → semantic edges → parent nodes → child nodes
  const semanticEdges = visibleEdges.filter(e => e.kind !== 'contains');
  const containsEdges = visibleEdges.filter(e => e.kind === 'contains');
  const parentNodes = graph.nodes.filter(n => !SYMBOL_KINDS.has(n.kind));
  const childNodes = graph.nodes.filter(n => SYMBOL_KINDS.has(n.kind));

  return (
    <svg
      width={width}
      height={height}
      style={{ cursor: isDraggingCanvas ? 'grabbing' : 'grab', background: 'transparent' }}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onMouseDown={handleCanvasMouseDown}
      onWheel={handleWheel}
    >
      <defs>
        <filter id="glow">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      <g transform={`translate(${transform.x},${transform.y}) scale(${transform.scale})`}>
        {/* Contains edges (subtle dashed, drawn first/below) */}
        <g opacity={0.35}>
          {containsEdges.map(edge => {
            const sp = getPos(edge.source), tp = getPos(edge.target);
            return (
              <GraphEdgeComp
                key={edge.id}
                edge={edge}
                sourceX={sp.x} sourceY={sp.y}
                targetX={tp.x} targetY={tp.y}
                isHighlighted={false}
              />
            );
          })}
        </g>

        {/* Orbit halos for expanded parent nodes */}
        {Array.from(expandedParentIds).map(parentId => {
          const pos = getPos(parentId);
          return (
            <circle
              key={`halo-${parentId}`}
              cx={pos.x}
              cy={pos.y}
              r={ORBIT_SPRING_LENGTH + 15}
              fill="none"
              stroke="#6366f1"
              strokeWidth={0.5}
              strokeDasharray="4 4"
              opacity={0.2}
            />
          );
        })}

        {/* Semantic edges (imports, calls, etc.) */}
        <g>
          {semanticEdges.map(edge => {
            const sp = getPos(edge.source), tp = getPos(edge.target);
            const isHighlighted = selectedNodeIds.has(edge.source) || selectedNodeIds.has(edge.target);
            return (
              <GraphEdgeComp
                key={edge.id}
                edge={edge}
                sourceX={sp.x} sourceY={sp.y}
                targetX={tp.x} targetY={tp.y}
                isHighlighted={isHighlighted}
              />
            );
          })}
        </g>

        {/* Parent / file / directory nodes */}
        <g>
          {parentNodes.map(node => {
            const pos = getPos(node.id);
            const displayNode = { ...node, x: pos.x, y: pos.y };
            return (
              <GraphNodeComp
                key={node.id}
                node={displayNode}
                isSelected={selectedNodeIds.has(node.id)}
                isHovered={hoveredId === node.id}
                isExpanded={expandedParentIds.has(node.id)}
                onClick={e => {
                  e.stopPropagation();
                  onNodeClick(node.id, e.shiftKey || e.metaKey || e.ctrlKey);
                }}
                onDoubleClick={() => onNodeDoubleClick(node)}
                onMouseEnter={() => setHoveredId(node.id)}
                onMouseLeave={() => setHoveredId(null)}
                onMouseDown={e => handleNodeMouseDown(node.id, e)}
              />
            );
          })}
        </g>

        {/* Symbol child nodes (rendered on top of parents) */}
        <g>
          {childNodes.map(node => {
            const pos = getPos(node.id);
            const displayNode = { ...node, x: pos.x, y: pos.y };
            return (
              <GraphNodeComp
                key={node.id}
                node={displayNode}
                isSelected={selectedNodeIds.has(node.id)}
                isHovered={hoveredId === node.id}
                isExpanded={false}
                onClick={e => {
                  e.stopPropagation();
                  onNodeClick(node.id, e.shiftKey || e.metaKey || e.ctrlKey);
                }}
                onDoubleClick={() => onNodeDoubleClick(node)}
                onMouseEnter={() => setHoveredId(node.id)}
                onMouseLeave={() => setHoveredId(null)}
                onMouseDown={e => handleNodeMouseDown(node.id, e)}
              />
            );
          })}
        </g>
      </g>

      {/* Mini status bar */}
      <text x={12} y={height - 12} fill="#475569" fontSize={9} fontFamily="monospace">
        {Math.round(transform.scale * 100)}%  {graph.nodes.length} nodes  {graph.edges.length} edges
        {childNodes.length > 0 ? `  (${childNodes.length} symbols)` : ''}
      </text>
    </svg>
  );
}
