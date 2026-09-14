import type { ExtractionMethod, NodeType } from "../../api/types";
import { LINK_FAMILIES, METHOD_STYLE, NODE_STYLE } from "../../graph/theme";

/** The entity type's graph mark, drawn from the same theme as the canvas. */
export function TypeGlyph({ type, size = 12 }: { type: NodeType; size?: number }) {
  const s = NODE_STYLE[type];
  const c = size / 2;
  const r = s.size >= 9 ? c - 1 : c - 2.5;
  const fill = s.color;
  let mark;
  if (s.shape === "ellipse") mark = <circle cx={c} cy={c} r={r} fill={fill} />;
  else if (s.shape === "rectangle") mark = <rect x={c - r} y={c - r} width={2 * r} height={2 * r} fill={fill} />;
  else if (s.shape === "round-rectangle") mark = <rect x={c - r} y={c - r} width={2 * r} height={2 * r} rx={2} fill={fill} />;
  else {
    const sides = s.shape === "diamond" ? 4 : s.shape === "hexagon" ? 6 : 3;
    const rotation = s.shape === "diamond" ? -Math.PI / 2 : s.shape === "triangle" ? -Math.PI / 2 : 0;
    const points = Array.from({ length: sides }, (_, k) => {
      const a = rotation + (k * 2 * Math.PI) / sides;
      return `${(c + (r + 0.5) * Math.cos(a)).toFixed(2)},${(c + (r + 0.5) * Math.sin(a) + (sides === 3 ? 1 : 0)).toFixed(2)}`;
    }).join(" ");
    mark = <polygon points={points} fill={fill} />;
  }
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true" style={{ flex: "none" }}>
      {mark}
    </svg>
  );
}

/** A short line in a link family's colour and an evidence method's dash; family null draws neutral ink. */
export function LineSample({ family, method = "structured", width = 24 }: { family: number | null; method?: ExtractionMethod; width?: number }) {
  const dash = METHOD_STYLE[method].dash;
  return (
    <svg width={width} height={10} viewBox={`0 0 ${width} 10`} aria-hidden="true" style={{ flex: "none" }}>
      <line
        x1={1}
        y1={5}
        x2={width - 1}
        y2={5}
        stroke={family === null ? "#aab5c0" : LINK_FAMILIES[family].color}
        strokeWidth={1.8}
        strokeDasharray={dash ? dash.join(" ") : undefined}
        strokeLinecap={method === "text_cooccurrence" ? "round" : "butt"}
      />
    </svg>
  );
}
