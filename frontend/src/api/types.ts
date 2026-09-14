// Response shapes of the read-only API in veritas/api/app.py. Nothing here is computed by the page.

export const NODE_TYPES = ["Person", "Phone", "BankAccount", "Organization", "Event", "Vehicle", "Location"] as const;
export type NodeType = (typeof NODE_TYPES)[number];

export const EDGE_TYPES = [
  "CALLED",
  "USES_PHONE",
  "TRANSFERRED_MONEY_TO",
  "HOLDS_ACCOUNT",
  "MEMBER_OF",
  "OWNS_VEHICLE",
  "PRESENT_AT_EVENT",
  "MET_AT",
  "ASSOCIATED_WITH",
] as const;
export type EdgeType = (typeof EDGE_TYPES)[number];

export type ExtractionMethod = "structured" | "text_pattern" | "text_cooccurrence";
export type Metric = "betweenness" | "pagerank" | "degree";
export type Variant = "structured_only" | "no_cooccurrence" | "all_evidence";

export interface Meta {
  notice: string;
  loaded_at: string;
  graph: {
    nodes: number;
    edges: number;
    node_types: Record<string, number>;
    edge_types: Record<string, number>;
  };
  metrics: Metric[];
  variants: Variant[];
  anchor_available: boolean;
}

export interface NodeData {
  id: string;
  type: NodeType;
  label: string;
  source_document_count: number;
  [attribute: string]: unknown;
}

/** One drawn edge: every edge of one type between the same two nodes, oldest first. */
export interface MergedEdgeData {
  id: string;
  source: string;
  target: string;
  type: EdgeType;
  count: number;
  edge_ids: string[];
  first: string;
  last: string;
  extraction_methods: ExtractionMethod[];
  max_confidence: number;
}

/** A single edge record, as returned with aggregate=false and inside audit blocks. */
export interface EdgeRecord {
  id: string;
  source_id?: string;
  target_id?: string;
  source?: string;
  target?: string;
  type: EdgeType;
  timestamp: string;
  extraction_method: ExtractionMethod;
  confidence: number;
  source_document_id: string;
  amount_inr?: string | null;
  mode?: string | null;
  [attribute: string]: unknown;
}

export interface NodeElement {
  group: "nodes";
  data: NodeData;
  position: { x: number; y: number };
}

export interface EdgeElement<D> {
  group: "edges";
  data: D;
}

export interface GraphResponse<D = MergedEdgeData> {
  counts: { nodes: number; edges: number; edge_elements: number };
  elements: Array<NodeElement | EdgeElement<D>>;
}

export interface SubgraphResponse<D = MergedEdgeData> extends GraphResponse<D> {
  center: string;
  depth: number;
}

export interface NodeDetail {
  id: string;
  type: NodeType;
  label: string;
  attributes: Record<string, unknown>;
  source_document_ids: string[];
  outgoing_edges: Record<string, number>;
  incoming_edges: Record<string, number>;
  neighbours: number;
}

export interface RankingRow {
  rank: number;
  node: string;
  score: number;
  label: string;
}

export interface CentralityResponse {
  metric: Metric;
  variant: Variant;
  people_ranked: number;
  note: string;
  ranking: RankingRow[];
}

export type Block = BlockCommon &
  (
    | { operation: "node_created"; payload: { node: { id: string; type: NodeType; source_document_ids: string[] } } }
    | { operation: "node_merged"; payload: { source_document_ids_added: string[] } }
    | { operation: "edge_created"; payload: { edge: EdgeRecord } }
  );

interface BlockCommon {
  idx: number;
  recorded_at: string;
  entity_kind: "node" | "edge";
  entity_id: string;
  source_id: string | null;
  target_id: string | null;
  actor: string;
  prev_hash: string;
  hash: string;
}

export interface HistoryResponse {
  entity_id: string;
  include_edges: boolean;
  total: number;
  offset: number;
  limit: number;
  blocks: Block[];
}

export interface ChainProblem {
  idx: number;
  check: string;
  detail: string;
}

export interface VerifyResponse {
  checked_at: string;
  chain: {
    ok: boolean;
    blocks_checked: number;
    anchor_checked: boolean;
    head: { idx: number; hash: string } | null;
    problem_count: number;
    problems: ChainProblem[];
  };
  served_graph_matches_log: boolean;
  differences: string[];
  replay_error: string | null;
}
