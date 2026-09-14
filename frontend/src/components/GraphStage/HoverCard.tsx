import type { GraphIndex } from "../../graph/elements";
import type { HoverTarget } from "../../graph/useCytoscape";
import { familyOf, LINK_FAMILIES, strongestMethod } from "../../graph/theme";
import { displayLabel, formatCount } from "../../lib/format";
import { LineSample, TypeGlyph } from "../ui/glyphs";
import styles from "./HoverCard.module.css";

const WIDTH = 248;
const HEIGHT = 112; // tallest card, for flipping above the pointer near the bottom edge

/** A preview of what a click would select, placed beside the pointer and kept inside the canvas. */
export function HoverCard({ target, index, rankOf, bounds }: { target: HoverTarget; index: GraphIndex; rankOf: (id: string) => number | null; bounds: { width: number; height: number } }) {
  const label = (id: string) => {
    const node = index.nodes.get(id);
    return node ? displayLabel(node.type, node.label) : id;
  };
  let body;
  if (target.kind === "node") {
    const node = index.nodes.get(target.id);
    if (!node) return null;
    const rank = rankOf(node.id);
    const links = index.edgesByNode.get(node.id)?.length ?? 0;
    body = (
      <>
        <strong>{displayLabel(node.type, node.label)}</strong>
        <div className={styles.type}>
          <TypeGlyph type={node.type} />
          {node.type}
        </div>
        <div className={styles.id}>{node.id}</div>
        <div className={styles.facts}>
          <span>
            <b>{formatCount(node.source_document_count)}</b> source {node.source_document_count === 1 ? "record" : "records"}
          </span>
          <span>
            <b>{formatCount(links)}</b> links drawn
          </span>
          {rank ? (
            <span>
              rank <b>{rank}</b>
            </span>
          ) : null}
        </div>
      </>
    );
  } else {
    const edge = index.edges.get(target.id);
    if (!edge) return null;
    const family = familyOf(edge.type);
    body = (
      <>
        <strong>{edge.type}</strong>
        <div className={styles.type}>
          <LineSample family={family} method={strongestMethod(edge.extraction_methods)} width={18} />
          {LINK_FAMILIES[family].label}
        </div>
        <div className={styles.route}>
          {label(edge.source)} → {label(edge.target)}
        </div>
        <div className={styles.facts}>
          <span>
            <b>{formatCount(edge.count)}</b> {edge.count === 1 ? "record" : "records"}
          </span>
          <span>{edge.extraction_methods.join(" + ")}</span>
        </div>
      </>
    );
  }

  // Beside the pointer, flipped left or up near the far edges so the card never leaves the canvas.
  const left = target.x + 16 + WIDTH > bounds.width - 8 ? target.x - WIDTH - 16 : target.x + 16;
  const top = target.y + 16 + HEIGHT > bounds.height - 8 ? target.y - HEIGHT - 16 : target.y + 16;
  const style = { left: Math.max(8, left), top: Math.max(8, top) };
  return (
    <div className={styles.card} style={style} role="tooltip">
      {body}
    </div>
  );
}
