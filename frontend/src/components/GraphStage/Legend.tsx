import type { Meta } from "../../api/types";
import { NODE_TYPES } from "../../api/types";
import { LINK_FAMILIES, METHODS, METHOD_STYLE } from "../../graph/theme";
import { formatCount } from "../../lib/format";
import { Button } from "../ui/controls";
import { LineSample, TypeGlyph } from "../ui/glyphs";
import styles from "./Legend.module.css";

export function Legend({ meta, open, onToggle }: { meta: Meta; open: boolean; onToggle: () => void }) {
  if (!open) {
    return (
      <Button icon="legend" onClick={onToggle} aria-expanded={false} className={styles.collapsed}>
        Legend
      </Button>
    );
  }
  const linkCount = (types: string[]) => types.reduce((sum, t) => sum + (meta.graph.edge_types[t] ?? 0), 0);
  return (
    <div className={styles.legend} role="group" aria-label="Legend">
      <div className={styles.header}>
        <h3>Entities</h3>
        <Button iconOnly size="small" variant="ghost" icon="close" aria-label="Hide legend" title="Hide legend" onClick={onToggle} />
      </div>
      <ul className={styles.types}>
        {NODE_TYPES.map((type) => (
          <li key={type}>
            <TypeGlyph type={type} size={13} />
            {type}
            <span className={styles.count}>{formatCount(meta.graph.node_types[type] ?? 0)}</span>
          </li>
        ))}
      </ul>
      <h3>Links</h3>
      <ul className={styles.lines}>
        {LINK_FAMILIES.map((family, i) => (
          <li key={family.label} title={`${family.types.join(", ")}: ${formatCount(linkCount(family.types))} records`}>
            <LineSample family={i} width={22} />
            {family.short}
          </li>
        ))}
        {METHODS.map((method) => (
          <li key={method}>
            <LineSample family={null} method={method} width={22} />
            {METHOD_STYLE[method].label}
          </li>
        ))}
      </ul>
    </div>
  );
}
