import { useEffect, useRef } from "react";
import type { Meta, RankingRow } from "../../api/types";
import { METHODS, METHOD_STYLE } from "../../graph/theme";
import { NODE_TYPES } from "../../api/types";
import { formatCount } from "../../lib/format";
import { Button } from "../ui/controls";
import { Icon } from "../ui/Icon";
import { LineSample, TypeGlyph } from "../ui/glyphs";
import styles from "./Welcome.module.css";

const METHOD_READING = {
  structured: "Solid: from structured records",
  text_pattern: "Dashed: a rule matched report text",
  text_cooccurrence: "Dotted: named in the same sentence",
} as const;

export function Welcome({
  meta,
  topBroker,
  peopleRanked,
  sharedName,
  onFollowBroker,
  onSharedName,
  onVerify,
  onClose,
}: {
  meta: Meta;
  topBroker: RankingRow | null;
  peopleRanked: number | null;
  /** Label of the curated shared-name node, or null when this graph doesn't contain it. */
  sharedName: string | null;
  onFollowBroker: () => void;
  onSharedName: () => void;
  onVerify: () => void;
  onClose: () => void;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => headingRef.current?.focus({ preventScroll: true }), []);

  return (
    <aside id="welcome" className={styles.panel} aria-labelledby="welcome-title">
      <div className={styles.titleRow}>
        <h2 id="welcome-title" ref={headingRef} tabIndex={-1}>
          A criminal-network graph you can audit
        </h2>
        <Button iconOnly variant="ghost" icon="close" aria-label="Close" title="Close" onClick={onClose} />
      </div>
      <p>
        {formatCount(meta.graph.nodes)} entities and {formatCount(meta.graph.edges)} links from call records, bank transfers and incident reports. Every link names its source
        record, and every change to the graph sits in a SHA-256 hash chain you can re-check here.
      </p>

      <div className={styles.synthetic}>
        <Icon name="flask" />
        <p>
          <b>Everything here is synthetic.</b> Generated for a portfolio project; no real people, numbers, accounts or cases.
        </p>
      </div>

      <div className={styles.reading}>
        <h3>Reading the graph</h3>
        <p className={styles.row}>
          <span className={styles.glyphs}>
            {NODE_TYPES.map((type) => (
              <TypeGlyph key={type} type={type} size={12} />
            ))}
          </span>
          Shape and colour: entity type
        </p>
        {METHODS.map((method) => (
          <p key={method} className={styles.row}>
            <LineSample family={null} method={method} width={26} />
            {METHOD_READING[method]}
            <span className="visually-hidden"> ({METHOD_STYLE[method].label})</span>
          </p>
        ))}
        <p className={styles.caveat}>Closeness on screen is not evidence; only a line is. Zoom in to see names.</p>
      </div>

      <div className={styles.starts}>
        <h3>Start with</h3>
        {topBroker ? (
          <button type="button" className={styles.start} onClick={onFollowBroker}>
            <strong>Follow the top broker</strong>
            <span>
              {topBroker.label}, rank 1 of {peopleRanked ?? "all"} by betweenness
            </span>
            <Icon name="arrow" />
          </button>
        ) : null}
        {sharedName ? (
          <button type="button" className={styles.start} onClick={onSharedName}>
            <strong>Inspect a shared name</strong>
            <span>{sharedName}: one node, reports from Delhi and Mumbai</span>
            <Icon name="arrow" />
          </button>
        ) : null}
        <button type="button" className={styles.start} onClick={onVerify}>
          <strong>Verify the audit chain</strong>
          <span>Re-hash every block and replay the log against this graph</span>
          <Icon name="arrow" />
        </button>
      </div>

      <footer className={styles.footer}>
        <Button variant="ghost" onClick={onClose}>
          Explore on my own
        </Button>
        <span>Reopen it from About</span>
      </footer>
    </aside>
  );
}
