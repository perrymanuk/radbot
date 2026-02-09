import { useState, useEffect } from "react";

function getIsMobile(breakpoint: number): boolean {
  try {
    return window.innerWidth < breakpoint;
  } catch {
    return false;
  }
}

export function useIsMobile(breakpoint = 768) {
  const [isMobile, setIsMobile] = useState(() => getIsMobile(breakpoint));

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${breakpoint - 1}px)`);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    setIsMobile(mq.matches);
    return () => mq.removeEventListener("change", handler);
  }, [breakpoint]);

  return isMobile;
}
