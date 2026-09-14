import { useState } from "react";
import type { MergedEdgeData, NodeData, NodeDetail, RankingRow } from "../../api/types";
import { familyOf, NODE_STYLE, strongestMethod } from "../../graph/theme";
import { displayLabel, formatCount, formatRecordTime, groupSources } from "../../lib/format";
import type { FetchState } from "../../state/hooks";
import { Button, Chip, Field, FieldGroup, Fields, Section, Skeleton } from "../ui/controls";
import { LineSample, TypeGlyph } from "../ui/glyphs";
import styles from "./Evidence.module.css";

const LINK_PREVIEW = 30;

export function NodeDossier({
  node,
  detail,
  links,
  rank,
  rankLabel,
  labelFor,
  onSelectEdge,
}: {
  node: NodeData;
  detail: FetchState<NodeDetail>;
  links: MergedEdgeData[];
  rank: RankingRow | null;
  rankLabel: string;
  labelFor: (id: string) => string;
  onSelectEdge: (id: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const d = detail.dataKey === node.id ? detail.data : undefined;
  const style = NODE_STYLE[node.type];
  const sources = d ? groupSources(d.source_document_ids) : null;
  const attributes = d ? Object.entries(d.attributes).filter(([key]) => key !== "type") : [];
  const sorted = [...links].sort((a, b) => a.type.localeCompare(b.type) || b.count - a.count);
  const shown = showAll ? sorted : sorted.slice(0, LINK_PREVIEW);
  const out = d ? Object.values(d.outgoing_edges).reduce((a, b) => a + b, 0) : null;
  const into = d ? Object.values(d.incoming_edges).reduce((a, b) => a + b, 0) : null;

  return (
    <div className={styles.dossier} style={{ ["--selection" as string]: style.color }} aria-label={`Evidence for ${node.label}`}>
      <div className={styles.head}>
        <h2 className={styles.title}>{displayLabel(node.type, node.label)}</h2>
        <div className={styles.typeLine}>
          <TypeGlyph type={node.type} />
          {node.type}
          <span className={styles.id}>{node.id}</span>
        </div>
        <div className={styles.chips}>
          <Chip>
            {formatCount(node.source_document_count)} source {node.source_document_count === 1 ? "record" : "records"}
          </Chip>
          {d ? <Chip>{formatCount(d.neighbours)} linked entities</Chip> : null}
          {rank ? (
            <Chip title={`Rank ${rank.rank} by ${rankLabel}, score ${rank.score}`}>
              rank {rank.rank} · {rankLabel}
            </Chip>
          ) : null}
        </div>
      </div>

      {detail.error && !d ? (
        <div className={styles.inlineError} role="alert">
          <p>Couldn't load this node's details: {detail.error.message}</p>
          <Button size="small" onClick={detail.reload}>
            Try again
          </Button>
        </div>
      ) : !d ? (
        <div className={styles.skeletons} aria-hidden="true">
          <Skeleton width="40%" />
          <Skeleton width="80%" />
          <Skeleton width="72%" />
          <Skeleton width="60%" />
        </div>
      ) : (
        <>
          {attributes.length > 1 ? (
            <Section title="Stored attributes" meta={`${attributes.length} fields`}>
              <Fields>
                {attributes.map(([key, value]) => (
                  <Field key={key} name={key}>
                    {typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value) ? formatRecordTime(value) : String(value)}
                  </Field>
                ))}
              </Fields>
            </Section>
          ) : null}

          <Section title="Provenance" meta={`${formatCount(d.source_document_ids.length)} records`}>
            <Fields>
              {sources!.records.length ? <FieldGroup>From structured records</FieldGroup> : null}
              {sources!.records.map((s) => (
                <Field key={s.id} name={<span className={styles.doc}>{s.id}</span>}>
                  {s.source}
                </Field>
              ))}
              {sources!.text.length ? <FieldGroup>From report text, extracted</FieldGroup> : null}
              {sources!.text.map((s) => (
                <Field key={s.id} name={<span className={styles.doc}>{s.id}</span>}>
                  {s.source}
                </Field>
              ))}
            </Fields>
          </Section>

          <Section title="Links" meta={`${formatCount(links.length)} drawn · ${formatCount(out ?? 0)} records out · ${formatCount(into ?? 0)} in`}>
            {links.length === 0 ? (
              <p className={styles.count}>No links in this view.</p>
            ) : (
              <div className={styles.links}>
                {shown.map((edge) => {
                  const other = edge.source === node.id ? edge.target : edge.source;
                  const direction = edge.source === node.id ? "→" : "←";
                  return (
                    <button key={edge.id} type="button" className={styles.linkRow} onClick={() => onSelectEdge(edge.id)} title={`${edge.type} ${direction} ${other}`}>
                      <LineSample family={familyOf(edge.type)} method={strongestMethod(edge.extraction_methods)} />
                      <span className={styles.who}>
                        <small>
                          {edge.type} {direction}
                        </small>
                        {labelFor(other)}
                      </span>
                      <span className={styles.count}>{formatCount(edge.count)}×</span>
                    </button>
                  );
                })}
                {sorted.length > LINK_PREVIEW ? (
                  <Button size="small" variant="ghost" className={styles.showAll} onClick={() => setShowAll((s) => !s)}>
                    {showAll ? "Show fewer" : `Show all ${formatCount(sorted.length)} links`}
                  </Button>
                ) : null}
              </div>
            )}
          </Section>
        </>
      )}
    </div>
  );
}
