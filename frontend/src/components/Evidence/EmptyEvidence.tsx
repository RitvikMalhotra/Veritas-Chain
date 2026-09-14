import { LineSample, TypeGlyph } from "../ui/glyphs";
import styles from "./Evidence.module.css";

export function EmptyEvidence() {
  return (
    <div className={styles.dossier}>
      <div className={styles.empty}>
        <h2>Nothing selected</h2>
        <p>Pick a node or a link on the graph, or a person under Key people. This pane then takes it apart:</p>
        <ul>
          <li>
            <TypeGlyph type="Person" size={14} />
            <span>
              <b>Provenance.</b> Every record the entity came from, split into structured registries and report text.
            </span>
          </li>
          <li>
            <LineSample family={1} width={22} />
            <span>
              <b>Links.</b> Each merged link with its records, extraction method and confidence.
            </span>
          </li>
          <li>
            <LineSample family={2} method="text_pattern" width={22} />
            <span>
              <b>Audit trail.</b> The hash-linked blocks that wrote it, marked on the chain above.
            </span>
          </li>
        </ul>
        <p className={styles.count}>
          <span className={styles.kbd}>Esc</span> clears a selection.
        </p>
      </div>
    </div>
  );
}
