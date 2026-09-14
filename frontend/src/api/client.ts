import type {
  CentralityResponse,
  EdgeRecord,
  GraphResponse,
  HistoryResponse,
  Meta,
  Metric,
  NodeDetail,
  SubgraphResponse,
  Variant,
  VerifyResponse,
} from "./types";

export class ApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null) {
    super(message);
    this.status = status;
  }

  /** True when nothing answered at all, as opposed to the API rejecting the request. */
  get unreachable(): boolean {
    return this.status === null || this.status === 502 || this.status === 503 || this.status === 504;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("the API did not answer", null);
  }
  if (!response.ok) {
    const body = await response.text();
    let detail = body;
    try {
      detail = JSON.parse(body).detail ?? body;
    } catch {
      // not JSON: keep the text (the Vite proxy answers with plain text when the API is down)
    }
    throw new ApiError(`${response.status} ${typeof detail === "string" ? detail : JSON.stringify(detail)}`.trim(), response.status);
  }
  return response.json() as Promise<T>;
}

// Node and edge ids contain ":" and "+" (Phone:+919876543210), so every id is encoded.
const enc = encodeURIComponent;

export const api = {
  meta: (signal?: AbortSignal) => request<Meta>("/api/meta", { signal }),

  graph: (signal?: AbortSignal) => request<GraphResponse>("/api/graph", { signal }),

  node: (id: string, signal?: AbortSignal) => request<NodeDetail>(`/api/nodes/${enc(id)}`, { signal }),

  subgraph: (id: string, depth: number, signal?: AbortSignal) =>
    request<SubgraphResponse>(`/api/nodes/${enc(id)}/subgraph?depth=${depth}`, { signal }),

  /** Every edge record around a node, unmerged; used to read the amounts the served graph holds. */
  rawSubgraph: (id: string, signal?: AbortSignal) =>
    request<SubgraphResponse<EdgeRecord>>(`/api/nodes/${enc(id)}/subgraph?depth=1&aggregate=false`, { signal }),

  centrality: (metric: Metric, variant: Variant, limit: number, signal?: AbortSignal) =>
    request<CentralityResponse>(`/api/centrality?metric=${metric}&variant=${variant}&limit=${limit}`, { signal }),

  history: (entityId: string, options: { includeEdges: boolean; limit: number; offset: number }, signal?: AbortSignal) =>
    request<HistoryResponse>(
      `/api/audit/history/${enc(entityId)}?include_edges=${options.includeEdges}&limit=${options.limit}&offset=${options.offset}`,
      { signal },
    ),

  verify: () => request<VerifyResponse>("/api/audit/verify", { method: "POST" }),
};

export const isAbort = (error: unknown) => error instanceof DOMException && error.name === "AbortError";
