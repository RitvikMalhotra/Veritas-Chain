import type { Block, ChainProblem, EdgeRecord, MergedEdgeData, NodeType, SubgraphResponse } from "../../api/types";
import { familyOf, LINK_FAMILIES, strongestMethod } from "../../graph/theme";
import { formatCount, formatInr, formatRecordTime, METHOD_LABEL, sourceOf } from "../../lib/format";
import type { FetchState, History } from "../../state/hooks";
import { Button, Chip, Field, Fields, Section, Skeleton } from "../ui/controls";
import { LineSample, TypeGlyph } from "../ui/glyphs";
import styles from "./Evidence.module.css";

const RECORD_CHIPS = 60;

export function EdgeDossier({
  edge,
  recordId,
  onRecord,
  record,
  rawAround,
  problems,
  labelFor,
  typeFor,
  onSelectNode,
}: {
  edge: MergedEdgeData;
  recordId: string;
  onRecord: (id: string) => void;
  /** History of the current record; its edge_created block holds the record's fields. */
  record: History;
  /** The source node's unmerged neighbourhood, for money links: the amounts the served graph holds. */
  rawAround: FetchState<SubgraphResponse<EdgeRecord>> | null;
  problems: ChainProblem[];
  labelFor: (id: string) => string;
  typeFor: (id: string) => NodeType | null;
  onSelectNode: (id: string) => void;
}) {
  const family = LINK_FAMILIES[familyOf(edge.type)];
  const method = strongestMethod(edge.extraction_methods);
  const position = edge.edge_ids.indexOf(recordId);
  const block = record.entityId === recordId ? record.blocks.find((b): b is Extract<Block, { operation: "edge_created" }> => b.operation === "edge_created") : undefined;
  const fields = block?.payload.edge;
  const failing = block ? problems.find((p) => p.idx === block.idx) : undefined;

  const graphRecord = rawAround?.data?.elements.find((e) => e.group === "edges" && e.data.id === recordId)?.data as EdgeRecord | undefined;
  const graphAmount = graphRecord?.amount_inr ?? null;
  const logAmount = fields?.amount_inr ?? null;
  const amountsDiffer = graphAmount !== null && logAmount !== null && Number(graphAmount) !== Number(logAmount);

  const provenance = (
    <Section title="Provenance">
      <Fields>
        <Field name="extraction">{edge.extraction_methods.map((m) => METHOD_LABEL[m]).join(" and ")}</Field>
        <Field name="confidence" derived="highest across records; an ordinal weight, not a probability">
          {edge.max_confidence.toFixed(2)}
        </Field>
        {edge.count > 1 ? (
          <>
            <Field name="first">{formatRecordTime(edge.first)}</Field>
            <Field name="last">{formatRecordTime(edge.last)}</Field>
          </>
        ) : (
          <Field name="when">{formatRecordTime(edge.first)}</Field>
        )}
      </Fields>
    </Section>
  );

  const recordSection = (
    <Section title="Record" meta={`${formatCount(position + 1)} of ${formatCount(edge.count)}`}>
      {record.error ? (
        <div className={styles.inlineError} role="alert">
          <p>Couldn't load this record's audit block: {record.error.message}</p>
          <Button size="small" onClick={record.retry}>
            Try again
          </Button>
        </div>
      ) : !fields ? (
        <div className={styles.skeletons} style={{ padding: 0 }} aria-hidden="true">
          <Skeleton width="60%" />
          <Skeleton width="75%" />
          <Skeleton width="50%" />
        </div>
      ) : (
        <Fields>
          <Field name="record">
            <span className={styles.doc}>{recordId}</span>
          </Field>
          <Field name="source record">
            <span className={styles.doc}>{fields.source_document_id}</span> {sourceOf(fields.source_document_id).source}
          </Field>
          <Field name="extraction">{fields.extraction_method}</Field>
          <Field name="confidence">{fields.confidence.toFixed(2)}</Field>
          <Field name="when">{formatRecordTime(fields.timestamp)}</Field>
          {fields.mode ? <Field name="mode">{fields.mode}</Field> : null}
          {logAmount !== null && !amountsDiffer ? (
            <Field name="amount" derived={graphAmount !== null ? "graph and audit log agree" : rawAround?.loading ? "checking the graph" : undefined}>
              {formatInr(logAmount)}
            </Field>
          ) : null}
          {amountsDiffer ? (
            <div className={styles.amounts} role="group" aria-label="Amount differs between graph and audit log">
              <div>
                <small>Graph being served</small>
                <b>{formatInr(graphAmount!)}</b>
              </div>
              <div>
                <small>Audit log now says</small>
                <b>{formatInr(logAmount!)}</b>
              </div>
            </div>
          ) : null}
        </Fields>
      )}
    </Section>
  );

  return (
    <div className={styles.dossier} style={{ ["--selection" as string]: family.color }} aria-label={`Evidence for ${edge.type} link`}>
      <div className={styles.head}>
        <h2 className={styles.title}>{edge.type}</h2>
        <div className={styles.typeLine}>
          <LineSample family={familyOf(edge.type)} method={method} width={20} />
          {family.label}
        </div>
        <div className={styles.route}>
          {[
            ["from", edge.source],
            ["to", edge.target],
          ].map(([role, id]) => {
            const type = typeFor(id);
            return (
              <button key={role} type="button" className={styles.endpoint} onClick={() => onSelectNode(id)} title={`Select ${id}`}>
                <small>{role}</small>
                {type ? <TypeGlyph type={type} /> : <span />}
                <span>{labelFor(id)}</span>
              </button>
            );
          })}
        </div>
        <div className={styles.chips}>
          <Chip>
            {formatCount(edge.count)} {edge.count === 1 ? "record" : "records"}
          </Chip>
          {edge.extraction_methods.map((m) => (
            <Chip key={m}>{m}</Chip>
          ))}
          {failing ? (
            <Chip tone="bad" icon="shieldBad">
              block fails {failing.check} check
            </Chip>
          ) : null}
        </div>
      </div>

      {/* A record whose block fails a check, or whose amount no longer matches the graph, is the finding: it goes first. */}
      {failing || amountsDiffer ? (
        <>
          {recordSection}
          {provenance}
        </>
      ) : (
        <>
          {provenance}
          {recordSection}
        </>
      )}

      {edge.count > 1 ? (
        <Section title="All records" meta={edge.count > RECORD_CHIPS ? `first ${RECORD_CHIPS} of ${formatCount(edge.count)}` : `${formatCount(edge.count)}, oldest first`}>
          <div className={styles.records}>
            {edge.edge_ids.slice(0, RECORD_CHIPS).map((id, i) => (
              <button key={id} type="button" className={styles.record} aria-current={id === recordId} onClick={() => onRecord(id)} title={id}>
                {i + 1}
              </button>
            ))}
          </div>
        </Section>
      ) : null}
    </div>
  );
}
