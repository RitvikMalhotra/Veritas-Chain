import type { ChainProblem } from "../../api/types";
import { describeBlock, formatCount, formatUtcTime, hashGroups } from "../../lib/format";
import type { History } from "../../state/hooks";
import { Button, Chip, Skeleton, Switch } from "../ui/controls";
import styles from "./AuditTrail.module.css";

export function AuditTrail({
  history,
  subjectKind,
  onIncludeEdges,
  problems,
  labelFor,
  onHoverBlock,
}: {
  history: History;
  subjectKind: "node" | "edge" | null;
  onIncludeEdges: (include: boolean) => void;
  problems: ChainProblem[];
  labelFor: (id: string) => string;
  onHoverBlock: (idx: number | null) => void;
}) {
  const failing = new Map(problems.map((p) => [p.idx, p]));
  const { blocks, total, loading, error } = history;

  return (
    <section className={styles.trail} aria-label="Audit trail">
      <header className={styles.head}>
        <h2>Audit trail</h2>
        <span className={styles.meta}>{total !== null ? `${formatCount(total)} ${total === 1 ? "block" : "blocks"}` : subjectKind ? "loading" : ""}</span>
      </header>
      {subjectKind === "node" ? (
        <div className={styles.toggle}>
          <Switch checked={history.includeEdges} onChange={onIncludeEdges}>
            Include links that touch this node
          </Switch>
        </div>
      ) : null}

      {!subjectKind ? (
        <p className={styles.empty}>
          Every write to the graph is a hash-linked block. Select an entity or a link to read the blocks that recorded it, and to mark them on the chain above.
        </p>
      ) : error ? (
        <div className={styles.error} role="alert">
          <p>Couldn't load the audit history: {error.message}</p>
          <Button size="small" onClick={history.retry}>
            Try again
          </Button>
        </div>
      ) : (
        <ol className={styles.blocks} aria-busy={loading}>
          {blocks.map((block) => {
            const problem = failing.get(block.idx);
            return (
              <li
                key={block.idx}
                className={problem ? `${styles.block} ${styles.bad}` : styles.block}
                onPointerEnter={() => onHoverBlock(block.idx)}
                onPointerLeave={() => onHoverBlock(null)}
              >
                <div className={styles.top}>
                  <span className={styles.idx}>#{formatCount(block.idx)}</span>
                  <span className={styles.op}>{block.operation}</span>
                  {problem ? (
                    <Chip tone="bad" icon="shieldBad">
                      {problem.check} check failed
                    </Chip>
                  ) : null}
                  <time dateTime={block.recorded_at}>{formatUtcTime(block.recorded_at)}</time>
                </div>
                <p className={styles.what}>{describeBlock(block, labelFor)}</p>
                {problem ? <p className={styles.what}>{problem.detail}</p> : null}
                <p className={styles.dump} title={`hash ${block.hash}\nprev ${block.prev_hash}`}>
                  <span>hash</span> {hashGroups(block.hash, 3)} <span>· prev</span> {hashGroups(block.prev_hash, 1)}
                </p>
                <p className={styles.actor}>actor {block.actor}</p>
              </li>
            );
          })}
          {loading
            ? Array.from({ length: blocks.length ? 1 : 3 }, (_, i) => (
                <li key={`skeleton-${i}`} className={styles.block} aria-hidden="true">
                  <Skeleton width="45%" />
                  <Skeleton width="85%" />
                  <Skeleton width="70%" />
                </li>
              ))
            : null}
          {!loading && total !== null && blocks.length < total ? (
            <li className={styles.more}>
              <Button size="small" onClick={history.loadMore}>
                Load {formatCount(Math.min(25, total - blocks.length))} more of {formatCount(total - blocks.length)}
              </Button>
            </li>
          ) : null}
        </ol>
      )}
    </section>
  );
}
