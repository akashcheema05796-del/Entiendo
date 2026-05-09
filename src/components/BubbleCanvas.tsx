import React, { useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Box, Zap } from 'lucide-react';

export interface Bubble {
  id: string;
  x: number;
  y: number;
  size: number;
  color: string;
  label: string;
  filePath?: string;
  type: 'file' | 'folder' | 'agent';
  driftX: number;
  driftY: number;
  driftDuration: number;
}

interface BubbleCanvasProps {
  bubbles: Bubble[];
  onBubbleClick: (bubble: Bubble) => void;
}

export default function BubbleCanvas({ bubbles, onBubbleClick }: BubbleCanvasProps) {
  // Compute static nearest-neighbour connections once per bubble set change
  const connections = useMemo(() => {
    const pairs: { x1: number; y1: number; x2: number; y2: number; color: string }[] = [];
    const seen = new Set<string>();
    bubbles.slice(0, 30).forEach((b, i) => {
      const nearest = bubbles
        .filter((_, j) => j !== i)
        .sort((a, c) => Math.hypot(a.x - b.x, a.y - b.y) - Math.hypot(c.x - b.x, c.y - b.y))
        .slice(0, 1);
      for (const n of nearest) {
        const key = [b.id, n.id].sort().join('|');
        if (!seen.has(key)) {
          seen.add(key);
          pairs.push({ x1: b.x, y1: b.y, x2: n.x, y2: n.y, color: b.color });
        }
      }
    });
    return pairs;
  }, [bubbles.map(b => b.id).join(',')]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {/* Static connection lines based on initial positions */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-[0.07]">
        {connections.map((c, i) => (
          <line key={i} x1={c.x1} y1={c.y1} x2={c.x2} y2={c.y2} stroke={c.color} strokeWidth="0.5" />
        ))}
      </svg>

      {/* Bubbles — animated purely via Framer Motion, no RAF/setState loop */}
      <AnimatePresence>
        {bubbles.map(bubble => (
          <motion.div
            key={bubble.id}
            initial={{ scale: 0, opacity: 0, x: bubble.x, y: bubble.y }}
            animate={{
              scale: 1,
              opacity: 0.85,
              x: [bubble.x, bubble.x + bubble.driftX, bubble.x - bubble.driftX * 0.6, bubble.x],
              y: [bubble.y, bubble.y + bubble.driftY, bubble.y - bubble.driftY * 0.6, bubble.y],
            }}
            exit={{ scale: 0, opacity: 0, transition: { duration: 0.3 } }}
            transition={{
              scale: { duration: 0.5, ease: 'easeOut' },
              opacity: { duration: 0.5 },
              x: { duration: bubble.driftDuration, repeat: Infinity, repeatType: 'reverse', ease: 'easeInOut' },
              y: { duration: bubble.driftDuration * 1.3, repeat: Infinity, repeatType: 'reverse', ease: 'easeInOut' },
            }}
            onClick={() => onBubbleClick(bubble)}
            className="absolute rounded-full border flex items-center justify-center backdrop-blur-sm shadow-lg pointer-events-auto cursor-pointer"
            style={{
              width: bubble.size,
              height: bubble.size,
              left: 0,
              top: 0,
              backgroundColor: `${bubble.color}11`,
              borderColor: `${bubble.color}44`,
              boxShadow: `0 0 30px ${bubble.color}22`,
            }}
            whileHover={{
              scale: 1.25,
              backgroundColor: `${bubble.color}33`,
              borderColor: `${bubble.color}bb`,
              boxShadow: `0 0 40px ${bubble.color}55`,
              zIndex: 50,
            }}
            title={bubble.filePath ?? bubble.label}
          >
            <div className="flex flex-col items-center gap-0.5 overflow-hidden px-1.5">
              {bubble.type === 'file'
                ? <Box className="w-2.5 h-2.5 flex-shrink-0" style={{ color: bubble.color }} />
                : <Zap className="w-2.5 h-2.5 flex-shrink-0" style={{ color: bubble.color }} />}
              <span className="text-[6px] font-mono font-bold text-slate-300 truncate w-full text-center leading-none">
                {bubble.label}
              </span>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
