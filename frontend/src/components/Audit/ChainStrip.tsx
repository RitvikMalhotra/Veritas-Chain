import { useEffect, useRef } from "react";

const INK = "#e4eaef";
const INK_3 = "#85919d";
const BAR = "#26313c";
const EMPTY = "#1a222b";
const RULE = "#3a4755";
const CRIT = "#e5484d";
const CRIT_INK = "#ff8078";
const MONO = '"Atkinson Hyperlegible Mono Variable", ui-monospace, monospace';

/**
 * The chain drawn to scale: block 1 at the left, the head at the right. Ticks are the blocks that recorded the
 * current selection; failed checks are painted at their true index.
 */
export function ChainStrip({
  total,
  ticks,
  highlight,
  problems,
  label,
}: {
  total: number | null;
  ticks: number[];
  highlight: number | null;
  problems: number[];
  label: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const draw = () => {
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      const ctx = canvas.getContext("2d");
      if (!ctx || width === 0) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      const barY = 14;
      const barH = 8;
      ctx.fillStyle = total ? BAR : EMPTY;
      ctx.beginPath();
      ctx.roundRect(0, barY, width, barH, 2);
      ctx.fill();
      if (!total) return;

      const x = (idx: number, inset = 2) => Math.round(((idx - 1) / Math.max(total - 1, 1)) * (width - inset));
      ctx.font = `11px ${MONO}`;
      ctx.textBaseline = "alphabetic";
      const step = total > 40000 ? 10000 : total > 8000 ? 5000 : total > 2000 ? 1000 : 500;
      for (let k = 0; k <= total; k += step) {
        const px = k === 0 ? 0 : x(k);
        ctx.fillStyle = RULE;
        ctx.fillRect(px, barY + barH + 2, 1, 4);
        const text = k === 0 ? "1" : k >= 1000 ? `${k / 1000}k` : String(k);
        const tw = ctx.measureText(text).width;
        if (px + tw / 2 > width - 40) continue; // keep clear of the head cap
        ctx.fillStyle = INK_3;
        ctx.fillText(text, Math.min(Math.max(px - tw / 2, 0), width - tw), height - 1);
      }

      ctx.fillStyle = INK;
      for (const idx of ticks) ctx.fillRect(x(idx), barY - 5, 1.5, barH + 10);
      if (highlight !== null) {
        ctx.fillRect(x(highlight) - 1, barY - 9, 3.5, barH + 18);
      }
      for (const idx of problems) {
        const px = x(idx, 3);
        ctx.fillStyle = CRIT;
        ctx.fillRect(px - 1, 0, 3, barY + barH + 6);
      }
      if (problems.length) {
        const px = x(problems[0], 3);
        ctx.font = `600 11px ${MONO}`;
        const text = `#${problems[0].toLocaleString("en-IN")}${problems.length > 1 ? ` +${problems.length - 1}` : ""}`;
        const tw = ctx.measureText(text).width;
        ctx.fillStyle = CRIT_INK;
        ctx.fillText(text, px - tw - 6 > 0 ? px - tw - 6 : px + 6, 10);
      }
      ctx.fillStyle = INK;
      ctx.fillRect(width - 3, barY - 4, 3, barH + 8); // head
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    document.fonts?.ready.then(draw);
    return () => observer.disconnect();
  }, [total, ticks, highlight, problems]);

  return <canvas ref={canvasRef} role="img" aria-label={label} style={{ display: "block", width: "100%", height: 34 }} />;
}
