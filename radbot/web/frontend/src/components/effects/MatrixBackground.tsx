import { useEffect, useRef } from "react";

const CHARS =
  "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const FONT_SIZE = 14;
const DROP_SPEED = 0.05;

export default function MatrixBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let columns = 0;
    let drops: number[] = [];

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      columns = Math.floor(canvas.width / FONT_SIZE);
      drops = new Array(columns).fill(0).map(() => Math.random() * -100);
    };

    resize();
    window.addEventListener("resize", resize);

    const draw = () => {
      ctx.fillStyle = "rgba(14, 20, 25, 0.05)";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.fillStyle = "#0f0";
      ctx.font = `${FONT_SIZE}px "Source Code Pro", monospace`;
      ctx.shadowColor = "#0f0";
      ctx.shadowBlur = 8;

      for (let i = 0; i < columns; i++) {
        if (drops[i] >= 0) {
          const char = CHARS[Math.floor(Math.random() * CHARS.length)];
          const x = i * FONT_SIZE;
          const y = drops[i] * FONT_SIZE;
          ctx.fillText(char, x, y);
        }

        drops[i] += DROP_SPEED + Math.random() * 0.02;

        if (drops[i] * FONT_SIZE > canvas.height && Math.random() > 0.975) {
          drops[i] = Math.random() * -20;
        }
      }

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(animRef.current);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 z-[-1] pointer-events-none opacity-30"
    />
  );
}
