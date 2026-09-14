import type { Block, ExtractionMethod, NodeType } from "../api/types";

const counts = new Intl.NumberFormat("en-IN");
const rupees = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const formatCount = (n: number) => counts.format(n);

/** Rupee amounts in Indian digit grouping, as the source records would print them: ₹5,05,000.00. */
export const formatInr = (amount: string | number) => `₹${rupees.format(Number(amount))}`;

/** +919600233059 → +91 96002 33059 (the canonical id keeps the unspaced form). */
export function formatPhone(number: string): string {
  return /^\+91\d{10}$/.test(number) ? `+91 ${number.slice(3, 8)} ${number.slice(8)}` : number;
}

/** The API's label, spaced for reading: phones grouped, account IFSC and number separated. */
export function displayLabel(type: NodeType | string, label: string): string {
  if (type === "Phone") return formatPhone(label);
  if (type === "BankAccount") return label.replace(" ", " · ");
  return label;
}

/** A node id's type prefix, for ids seen only inside audit payloads. */
export const typeOfId = (id: string) => id.slice(0, id.indexOf(":"));

/** Groups of eight hex digits, the way the audit trail prints hashes. */
export function hashGroups(hash: string, groups = 8): string {
  return (hash.match(/.{1,8}/g) ?? []).slice(0, groups).join(" ");
}

/** 2026-09-14T15:23:54.159332+00:00 → 15:23:54.159 UTC (audit blocks are recorded in UTC). */
export function formatUtcTime(iso: string): string {
  const match = /T(\d{2}:\d{2}:\d{2})(\.\d{1,3})?/.exec(iso);
  return match ? `${match[1]}${match[2] ?? ""} UTC` : iso;
}

/** Record timestamps carry their own offset; +05:30 is written as IST. */
export function formatRecordTime(iso: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?([+-]\d{2}:\d{2}|Z)?$/.exec(iso);
  if (!match) return iso;
  const [, date, time, offset] = match;
  const zone = offset === "+05:30" ? "IST" : offset === "Z" || offset === "+00:00" ? "UTC" : offset ?? "";
  return `${date} ${time} ${zone}`.trim();
}

export const METHOD_LABEL: Record<ExtractionMethod, string> = {
  structured: "structured record",
  text_pattern: "report text, pattern rule",
  text_cooccurrence: "report text, same sentence",
};

// Record-id prefixes, as documented in data/README.md. FIR documents are free text read by the extractor.
const SOURCES: Record<string, string> = {
  SUB: "Subscriber registry",
  CDR: "Call detail records",
  KYC: "Bank account KYC",
  TXN: "Bank transactions",
  VEH: "Vehicle registry",
  ROC: "Company registry",
  INC: "Incident register",
  FIR: "Incident report text",
};

export interface SourceDocument {
  id: string;
  source: string;
  fromText: boolean;
}

export function sourceOf(documentId: string): SourceDocument {
  const prefix = documentId.split("-")[0];
  return { id: documentId, source: SOURCES[prefix] ?? "Unknown source", fromText: prefix === "FIR" };
}

export function groupSources(documentIds: string[]): { records: SourceDocument[]; text: SourceDocument[] } {
  const all = documentIds.map(sourceOf);
  return { records: all.filter((d) => !d.fromText), text: all.filter((d) => d.fromText) };
}

/** One line per audit block, in the words of what the pipeline did. `labelFor` names the other end of an edge. */
export function describeBlock(block: Block, labelFor: (id: string) => string = (id) => id): string {
  switch (block.operation) {
    case "node_created":
      return `Created ${block.payload.node.type} from ${block.payload.node.source_document_ids.join(", ")}`;
    case "node_merged":
      return `Exact-match merge added ${block.payload.source_document_ids_added.join(", ")}`;
    case "edge_created": {
      const e = block.payload.edge;
      const amount = e.amount_inr ? ` · ${formatInr(e.amount_inr)}` : "";
      return `${e.type} ${labelFor(e.source_id ?? "")} → ${labelFor(e.target_id ?? "")} · ${e.source_document_id} · ${e.extraction_method} ${e.confidence.toFixed(2)}${amount}`;
    }
  }
}

export interface Difference {
  kind: "node" | "edge";
  id: string;
  text: string;
}

/** Parses verify's replay differences ("edge edge:0d66… differs", "node Person:x attributes differ"). */
export function parseDifferences(differences: string[]): Difference[] {
  return differences.flatMap((text) => {
    const match = /^(node|edge) (\S+) /.exec(text);
    return match ? [{ kind: match[1] as "node" | "edge", id: match[2], text }] : [];
  });
}
