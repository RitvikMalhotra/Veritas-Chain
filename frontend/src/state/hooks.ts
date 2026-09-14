import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, isAbort } from "../api/client";
import type { Block, CentralityResponse, GraphResponse, Meta, VerifyResponse } from "../api/types";
import { indexGraph, type GraphIndex } from "../graph/elements";

export interface FetchState<T> {
  data: T | undefined;
  /** The key the current data belongs to; lets views keep showing old data while a new key loads. */
  dataKey: string | null;
  loading: boolean;
  error: Error | null;
  reload: () => void;
}

/** Loads whenever `key` changes, cancelling the previous request; a null key means "nothing to load". */
export function useFetch<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>): FetchState<T> {
  const loader = useRef(load);
  loader.current = load;
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<Omit<FetchState<T>, "reload">>({ data: undefined, dataKey: null, loading: key !== null, error: null });

  useEffect(() => {
    if (key === null) {
      setState({ data: undefined, dataKey: null, loading: false, error: null });
      return;
    }
    const controller = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    loader.current(controller.signal).then(
      (data) => setState({ data, dataKey: key, loading: false, error: null }),
      (error) => {
        if (!isAbort(error)) setState((s) => ({ ...s, loading: false, error: error as Error }));
      },
    );
    return () => controller.abort();
  }, [key, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, reload };
}

export type StepState = "waiting" | "loading" | "done" | "failed";
export interface BootStep {
  request: string;
  state: StepState;
  detail: string;
}

export interface Boot {
  meta: Meta | null;
  graph: GraphResponse | null;
  index: GraphIndex | null;
  topBroker: CentralityResponse | null;
  steps: BootStep[];
  error: ApiError | Error | null;
  retry: () => void;
}

/** The first three requests, reported step by step so the graph pane can show what it is waiting for. */
export function useBoot(): Boot {
  const [attempt, setAttempt] = useState(0);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [index, setIndex] = useState<GraphIndex | null>(null);
  const [topBroker, setTopBroker] = useState<CentralityResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [steps, setSteps] = useState<BootStep[]>(initialSteps);

  useEffect(() => {
    const controller = new AbortController();
    const mark = (i: number, state: StepState, detail: string) =>
      setSteps((all) => all.map((step, k) => (k === i ? { ...step, state, detail } : step)));
    const fail = (i: number) => (e: unknown) => {
      if (isAbort(e)) return;
      mark(i, "failed", e instanceof Error ? e.message : String(e));
      setError(e instanceof Error ? e : new Error(String(e)));
    };
    setSteps(initialSteps().map((s, i) => (i < 3 ? { ...s, state: "loading", detail: "waiting for a response" } : s)));
    setError(null);

    api.meta(controller.signal).then((m) => {
      setMeta(m);
      mark(0, "done", `${m.graph.nodes.toLocaleString("en-IN")} nodes, ${m.graph.edges.toLocaleString("en-IN")} edge records`);
    }, fail(0));
    api.centrality("betweenness", "structured_only", 1, controller.signal).then((c) => {
      setTopBroker(c);
      mark(1, "done", `${c.people_ranked} people ranked`);
    }, fail(1));
    api.graph(controller.signal).then((g) => {
      setIndex(indexGraph(g));
      setGraph(g);
      mark(2, "done", `${g.counts.edge_elements.toLocaleString("en-IN")} merged links`);
      mark(3, "done", "drawn");
    }, fail(2));
    return () => controller.abort();
  }, [attempt]);

  return { meta, graph, index, topBroker, steps, error, retry: () => setAttempt((a) => a + 1) };
}

const initialSteps = (): BootStep[] => [
  { request: "GET /api/meta", state: "waiting", detail: "" },
  { request: "GET /api/centrality", state: "waiting", detail: "" },
  { request: "GET /api/graph", state: "waiting", detail: "" },
  { request: "draw", state: "waiting", detail: "waiting for the graph" },
];

export interface History {
  entityId: string | null;
  includeEdges: boolean;
  blocks: Block[];
  total: number | null;
  loading: boolean;
  error: Error | null;
  loadMore: () => void;
  retry: () => void;
}

const PAGE = 25;

/** Audit blocks for one node or edge record, oldest first, a page at a time. */
export function useHistory(entityId: string | null, includeEdges: boolean): History {
  const [state, setState] = useState<{ key: string | null; blocks: Block[]; total: number | null; loading: boolean; error: Error | null }>({
    key: null,
    blocks: [],
    total: null,
    loading: false,
    error: null,
  });
  const [nonce, setNonce] = useState(0);
  const key = entityId ? `${entityId}|${includeEdges}` : null;
  const controllerRef = useRef<AbortController | null>(null);

  const fetchPage = useCallback(
    (offset: number, replace: boolean) => {
      if (!entityId) return;
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState((s) => ({ ...s, key, loading: true, error: null, ...(replace ? { blocks: [], total: null } : {}) }));
      api.history(entityId, { includeEdges, limit: PAGE, offset }, controller.signal).then(
        (page) => setState((s) => ({ key, blocks: replace ? page.blocks : [...s.blocks, ...page.blocks], total: page.total, loading: false, error: null })),
        (error) => {
          if (!isAbort(error)) setState((s) => ({ ...s, loading: false, error: error as Error }));
        },
      );
    },
    [entityId, includeEdges, key],
  );

  useEffect(() => {
    if (!entityId) {
      controllerRef.current?.abort();
      setState({ key: null, blocks: [], total: null, loading: false, error: null });
      return;
    }
    fetchPage(0, true);
    return () => controllerRef.current?.abort();
  }, [entityId, includeEdges, nonce, fetchPage]);

  const current = state.key === key;
  return {
    entityId,
    includeEdges,
    blocks: current ? state.blocks : [],
    total: current ? state.total : null,
    loading: state.loading || !current,
    error: current ? state.error : null,
    loadMore: () => fetchPage(current ? state.blocks.length : 0, false),
    retry: () => setNonce((n) => n + 1),
  };
}

export type VerifyState =
  | { status: "idle" }
  | { status: "running"; previous: VerifyResponse | null }
  | { status: "done"; result: VerifyResponse }
  | { status: "failed"; message: string; previous: VerifyResponse | null };

export function useVerify() {
  const [state, setState] = useState<VerifyState>({ status: "idle" });
  const last = useRef<VerifyResponse | null>(null);

  const run = useCallback(() => {
    setState({ status: "running", previous: last.current });
    api.verify().then(
      (result) => {
        last.current = result;
        setState({ status: "done", result });
      },
      (error: Error) => setState({ status: "failed", message: error.message, previous: last.current }),
    );
  }, []);

  return { state, run };
}

/** The last completed verification, even while a new one runs or after one fails. */
export function lastResult(state: VerifyState): VerifyResponse | null {
  if (state.status === "done") return state.result;
  if (state.status === "idle") return null;
  return state.previous;
}
