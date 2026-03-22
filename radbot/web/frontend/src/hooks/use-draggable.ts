import { useState, useRef, useCallback, useEffect } from "react";

interface UseDraggableOptions {
  storageKey: string;
  defaultPosition: { x: number; y: number }; // offsets from bottom-right
  elementSize: number;
  tapThreshold?: number;
  onTap: () => void;
  disabled?: boolean;
}

interface Position {
  top: number;
  left: number;
}

function clamp(pos: Position, size: number): Position {
  const maxTop = window.innerHeight - size;
  const maxLeft = window.innerWidth - size;
  return {
    top: Math.max(0, Math.min(pos.top, maxTop)),
    left: Math.max(0, Math.min(pos.left, maxLeft)),
  };
}

function loadPosition(key: string, defaultPos: { x: number; y: number }, size: number): Position {
  try {
    const stored = localStorage.getItem(key);
    if (stored) {
      const parsed = JSON.parse(stored) as Position;
      return clamp(parsed, size);
    }
  } catch {
    // ignore
  }
  return {
    top: window.innerHeight - defaultPos.y - size,
    left: window.innerWidth - defaultPos.x - size,
  };
}

export function useDraggable(options: UseDraggableOptions) {
  const { storageKey, defaultPosition, elementSize, tapThreshold = 5, onTap, disabled } = options;

  const [position, setPosition] = useState<Position>(() =>
    loadPosition(storageKey, defaultPosition, elementSize),
  );
  const [isDragging, setIsDragging] = useState(false);

  const draggingRef = useRef(false);
  const startPointerRef = useRef({ x: 0, y: 0 });
  const startPosRef = useRef({ top: 0, left: 0 });
  const cumulativeDistRef = useRef(0);
  const lastPointerRef = useRef({ x: 0, y: 0 });

  // Re-clamp on resize / orientation change
  useEffect(() => {
    const onResize = () => setPosition((p) => clamp(p, elementSize));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [elementSize]);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.currentTarget.setPointerCapture(e.pointerId);
      draggingRef.current = true;
      cumulativeDistRef.current = 0;
      startPointerRef.current = { x: e.clientX, y: e.clientY };
      lastPointerRef.current = { x: e.clientX, y: e.clientY };
      startPosRef.current = { ...position };
    },
    [position],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!draggingRef.current) return;

      const dx = e.clientX - lastPointerRef.current.x;
      const dy = e.clientY - lastPointerRef.current.y;
      cumulativeDistRef.current += Math.abs(dx) + Math.abs(dy);
      lastPointerRef.current = { x: e.clientX, y: e.clientY };

      if (cumulativeDistRef.current >= tapThreshold) {
        setIsDragging(true);
        const newPos = clamp(
          {
            top: startPosRef.current.top + (e.clientY - startPointerRef.current.y),
            left: startPosRef.current.left + (e.clientX - startPointerRef.current.x),
          },
          elementSize,
        );
        setPosition(newPos);
      }
    },
    [elementSize, tapThreshold],
  );

  const finishDrag = useCallback(
    (wasTap: boolean) => {
      draggingRef.current = false;
      if (cumulativeDistRef.current >= tapThreshold) {
        // Was a drag — persist position
        setPosition((pos) => {
          try {
            localStorage.setItem(storageKey, JSON.stringify(pos));
          } catch {
            // ignore
          }
          return pos;
        });
      } else if (wasTap && !disabled) {
        onTap();
      }
      setIsDragging(false);
    },
    [tapThreshold, storageKey, disabled, onTap],
  );

  const onPointerUp = useCallback(
    (_e: React.PointerEvent) => finishDrag(true),
    [finishDrag],
  );

  const onPointerCancel = useCallback(
    (_e: React.PointerEvent) => finishDrag(false),
    [finishDrag],
  );

  return {
    position,
    isDragging,
    handlers: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel },
  };
}
