import { useEffect, useRef } from "react";
import type { CentralityResponse, Metric, Variant } from "../../api/types";
import type { FetchState } from "../../state/hooks";
import { Button, SegmentedControl, Select, Skeleton, type Choice } from "../ui/controls";
import styles from "./Rankings.module.css";

export const METRICS: Choice<Metric>[] = [
  { value: "betweenness", label: "Betweenness", description: "Brokers: people on the shortest paths between others" },
  { value: "pagerank", label: "PageRank", description: "Influence: linked to by people who are themselves well linked" },
  { value: "degree", label: "Degree", description: "Distinct contacts" },
];

export const VARIANTS: Choice<Variant>[] = [
  { value: "structured_only", label: "Structured records only", description: "Calls, transfers and registries; no report text" },
  { value: "no_cooccurrence", label: "Without same-sentence links", description: "Adds pattern-matched report text, leaves out names that only share a sentence" },
  { value: "all_evidence", label: "All evidence", description: "Every link, including names that only share a sentence" },
];

export function Rankings({
  metric,
  variant,
  onMetric,
  onVariant,
  ranking,
  selectedId,
  onSelect,
}: {
  metric: Metric;
  variant: Variant;
  onMetric: (m: Metric) => void;
  onVariant: (v: Variant) => void;
  ranking: FetchState<CentralityResponse>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const data = ranking.data;
  const max = data?.ranking[0]?.score || 1;
  const listRef = useRef<HTMLOListElement>(null);
  const metricLabel = METRICS.find((m) => m.value === metric)!.label;

  useEffect(() => {
    if (!selectedId) return;
    listRef.current?.querySelector<HTMLElement>(`[data-node="${CSS.escape(selectedId)}"]`)?.scrollIntoView({ block: "nearest" });
  }, [selectedId, data]);

  return (
    <section className={styles.pane} aria-label="Key people">
      <header className={styles.head}>
        <h2>Key people</h2>
        <span className={styles.meta}>{data ? `${data.people_ranked} ranked` : ""}</span>
      </header>
      <div className={styles.controls}>
        <SegmentedControl label="Ranking metric" choices={METRICS} value={metric} onChange={onMetric} />
        <Select label="Evidence" choices={VARIANTS} value={variant} onChange={onVariant} />
      </div>
      <div className={styles.columns} aria-hidden="true">
        <span>#</span>
        <span>Person</span>
        <span>{metricLabel}</span>
      </div>
      <div className={styles.scroll}>
        {ranking.error && !data ? (
          <div className={styles.error} role="alert">
            <p>Couldn't load rankings: {ranking.error.message}</p>
            <Button size="small" onClick={ranking.reload}>
              Try again
            </Button>
          </div>
        ) : !data ? (
          <div className={styles.skeletons} aria-hidden="true">
            {Array.from({ length: 12 }, (_, i) => (
              <Skeleton key={i} width={`${88 - ((i * 7) % 30)}%`} />
            ))}
          </div>
        ) : (
          <ol ref={listRef} className={styles.list} data-stale={ranking.loading} aria-busy={ranking.loading}>
            {data.ranking.map((row) => (
              <li key={row.node}>
                <button type="button" className={styles.row} data-node={row.node} aria-current={row.node === selectedId} onClick={() => onSelect(row.node)} title={row.node}>
                  <span className={styles.rank}>{row.rank}</span>
                  <span className={styles.name}>{row.label}</span>
                  <span className={styles.score}>
                    {row.score.toFixed(4)}
                    <i className={styles.bar} aria-hidden="true">
                      <i style={{ width: `${Math.max((row.score / max) * 100, 0).toFixed(1)}%` }} />
                    </i>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>
      {data ? <p className={styles.note}>{data.note}</p> : null}
    </section>
  );
}
