import type { Meta } from "../../api/types";
import { formatCount, formatUtcTime } from "../../lib/format";
import { lastResult, type VerifyState } from "../../state/hooks";
import styles from "./StatusBar.module.css";

export function StatusBar({
  meta,
  verify,
  drawnLinks,
  viewText,
  rankingText,
}: {
  meta: Meta | null;
  verify: VerifyState;
  drawnLinks: number | null;
  viewText: string;
  rankingText: string;
}) {
  const result = lastResult(verify);
  const ok = result && result.chain.ok && result.served_graph_matches_log;
  const tone = verify.status === "running" ? "running" : !result ? "idle" : !ok ? "bad" : result.chain.anchor_checked ? "ok" : "warn";
  const chainText =
    verify.status === "running"
      ? "Verifying the chain"
      : !result
        ? "Chain not verified"
        : !ok
          ? "Tampering detected"
          : result.chain.anchor_checked
            ? "Chain verified"
            : "Verified without an anchor";

  return (
    <footer className={styles.bar}>
      <span>
        <i className={styles.led} data-tone={tone} aria-hidden="true" />
        {chainText}
        {result && verify.status !== "running" ? <b>{formatUtcTime(result.checked_at).slice(0, 8)} UTC</b> : null}
      </span>
      {meta ? (
        <>
          <span>
            Nodes <b>{formatCount(meta.graph.nodes)}</b>
          </span>
          <span>
            Edge records <b>{formatCount(meta.graph.edges)}</b>
          </span>
        </>
      ) : null}
      {drawnLinks !== null ? (
        <span>
          Drawn links <b>{formatCount(drawnLinks)}</b>
        </span>
      ) : null}
      <span className={styles.shrink}>{viewText}</span>
      <span>
        Rankings <b>{rankingText}</b>
      </span>
      <span className={styles.end}>All data is synthetic</span>
    </footer>
  );
}
