import React, { createContext, useContext, useRef, useState, useEffect } from 'react';
import { io, Socket } from 'socket.io-client';
import { GraphNode, GraphEdge, ProjectGraph } from '../types/project_graph.ts';

interface SocketContextValue {
  socket: Socket | null;
  selectedNodeIds: Set<string>;
  setSelectedNodeIds: React.Dispatch<React.SetStateAction<Set<string>>>;
  graphData: ProjectGraph | null;
  setGraphData: React.Dispatch<React.SetStateAction<ProjectGraph | null>>;
  expandedNodeIds: Set<string>;
  setExpandedNodeIds: React.Dispatch<React.SetStateAction<Set<string>>>;
}

const SocketContext = createContext<SocketContextValue>({
  socket: null,
  selectedNodeIds: new Set(),
  setSelectedNodeIds: () => {},
  graphData: null,
  setGraphData: () => {},
  expandedNodeIds: new Set(),
  setExpandedNodeIds: () => {},
});

export function SocketProvider({ children }: { children: React.ReactNode }) {
  const socketRef = useRef<Socket | null>(null);
  const [selectedNodeIds, setSelectedNodeIds] = useState<Set<string>>(new Set());
  const [graphData, setGraphData] = useState<ProjectGraph | null>(null);
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    const socket = io();
    socketRef.current = socket;

    socket.on('graph_data', (data: ProjectGraph) => {
      setGraphData(data);
    });

    socket.on('node_expanded', (data: { nodeId: string; childNodes: GraphNode[]; childEdges: GraphEdge[] }) => {
      setExpandedNodeIds(prev => new Set([...prev, data.nodeId]));
      setGraphData(prev => {
        if (!prev) return prev;
        const existingIds = new Set(prev.nodes.map(n => n.id));
        const newNodes = data.childNodes.filter(n => !existingIds.has(n.id));
        const existingEdgeIds = new Set(prev.edges.map(e => e.id));
        const newEdges = data.childEdges.filter(e => !existingEdgeIds.has(e.id));
        return { ...prev, nodes: [...prev.nodes, ...newNodes], edges: [...prev.edges, ...newEdges] };
      });
    });

    return () => { socket.disconnect(); };
  }, []);

  return (
    <SocketContext.Provider value={{
      socket: socketRef.current,
      selectedNodeIds, setSelectedNodeIds,
      graphData, setGraphData,
      expandedNodeIds, setExpandedNodeIds,
    }}>
      {children}
    </SocketContext.Provider>
  );
}

export function useSocket() { return useContext(SocketContext); }
