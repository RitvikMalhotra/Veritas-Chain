import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api/client";
import type { Metric, Variant } from "./api/types";
import { AuditTrail } from "./components/Audit/AuditTrail";
import { IntegrityBand, type StripSubject } from "./components/Audit/IntegrityBand";
import { EdgeDossier } from "./components/Evidence/EdgeDossier";
import { EmptyEvidence } from "./components/Evidence/EmptyEvidence";
import { NodeDossier } from "./components/Evidence/NodeDossier";
import { GraphStage, type FitRequest, type ViewMode } from "./components/GraphStage/GraphStage";
import { Welcome } from "./components/Onboarding/Welcome";
import { METRICS, Rankings, VARIANTS } from "./components/Rankings/Rankings";
import { StatusBar } from "./components/StatusBar/StatusBar";
import { TopBar } from "./components/TopBar/TopBar";
import { indexGraph, toCytoscape } from "./graph/elements";
import type { GraphSelection } from "./graph/useCytoscape";
import { displayLabel, formatCount, type Difference } from "./lib/format";
import { lastResult, useBoot, useFetch, useHistory, useVerify } from "./state/hooks";
import styles from "./App.module.css";

// Curated starting point: one node that holds records from reports in two cities (docs/methodology.md, Phase 3).
// The card hides itself if a rebuilt graph no longer has this node.
const SHARED_NAME_ID = "Person:rahul_sharma";
const WELCOME_WIDTH = 456; // the docked panel plus its margin; see Welcome.module.css

interface View {
  mode: ViewMode;
  center: string | null;
  depth: number;
}

export default function App() {
  const boot = useBoot();
  const verify = useVerify();

  const [metric, setMetric] = useState<Metric>("betweenness");
  const [variant, setVariant] = useState<Variant>("structured_only");
  const ranking = useFetch(`${metric}|${variant}`, (signal) => api.centrality(metric, variant, 1000, signal));
  const ranks = useMemo(() => new Map((ranking.data?.ranking ?? []).map((row) => [row.node, row])), [ranking.data]);

  const [view, setView] = useState<View>({ mode: "full", center: null, depth: 2 });
  const subgraphKey = view.mode === "neighbourhood" && view.center ? `${view.center}|${view.depth}` : null;
  const subgraph = useFetch(subgraphKey, (signal) => api.subgraph(view.center!, view.depth, signal));
  const showingSubgraph = subgraphKey !== null && subgraph.dataKey === subgraphKey && Boolean(subgraph.data);
  const viewGraph = showingSubgraph ? subgraph.data! : boot.graph;
  const elements = useMemo(() => (viewGraph ? toCytoscape(viewGraph) : null), [viewGraph]);
  const viewIndex = useMemo(() => (!viewGraph ? null : viewGraph === boot.graph ? boot.index : indexGraph(viewGraph)), [viewGraph, boot.graph, boot.index]);
  const fullIndex = boot.index;

  const [selection, setSelection] = useState<GraphSelection>(null);
  const [recordId, setRecordId] = useState<string | null>(null);
  const [includeEdges, setIncludeEdges] = useState(false);
  const [fitRequest, setFitRequest] = useState<FitRequest>({ ids: null, nonce: 0, animate: false });
  const [welcomeOpen, setWelcomeOpen] = useState(true);
  const [hoverBlock, setHoverBlock] = useState<number | null>(null);
  const selectionRef = useRef<GraphSelection>(null);
  selectionRef.current = selection;

  const requestFit = useCallback((ids: string[] | null, animate = true) => setFitRequest((f) => ({ ids, nonce: f.nonce + 1, animate })), []);

  const labelFor = useCallback(
    (id: string) => {
      const node = fullIndex?.nodes.get(id);
      return node ? displayLabel(node.type, node.label) : id;
    },
    [fullIndex],
  );
  const typeFor = useCallback((id: string) => fullIndex?.nodes.get(id)?.type ?? null, [fullIndex]);

  // First draw: fit the whole graph clear of the legend, without a camera move.
  useEffect(() => {
    if (boot.graph) requestFit(null, false);
  }, [boot.graph, requestFit]);

  // A neighbourhood arrived: fit it.
  useEffect(() => {
    if (showingSubgraph) requestFit(null, false);
  }, [showingSubgraph, subgraph.data, requestFit]);

  const selectNode = useCallback(
    (id: string, { fit = false } = {}) => {
      if (!fullIndex?.nodes.has(id)) return;
      if (view.mode === "neighbourhood" && !viewIndex?.nodes.has(id)) setView((v) => ({ ...v, mode: "full" }));
      setSelection({ kind: "node", id });
      setRecordId(null);
      if (fit) requestFit([id]);
    },
    [fullIndex, viewIndex, view.mode, requestFit],
  );

  const selectEdge = useCallback(
    (id: string, { fit = false, record }: { fit?: boolean; record?: string } = {}) => {
      const edge = viewIndex?.edges.get(id) ?? fullIndex?.edges.get(id);
      if (!edge) return;
      if (!viewIndex?.edges.has(id)) setView((v) => ({ ...v, mode: "full" }));
      setSelection({ kind: "edge", id });
      setRecordId(record ?? edge.edge_ids[0]);
      if (fit) requestFit([id]);
    },
    [fullIndex, viewIndex, requestFit],
  );

  // Closing the welcome panel frees the left of the canvas: re-centre on what is selected, or on everything.
  const closeWelcome = useCallback(() => {
    setWelcomeOpen(false);
    requestFit(selectionRef.current ? [selectionRef.current.id] : null);
  }, [requestFit]);

  const clearSelection = useCallback(() => {
    setSelection(null);
    setRecordId(null);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (welcomeOpen) closeWelcome();
      else clearSelection();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [welcomeOpen, closeWelcome, clearSelection]);

  const selectedNode = selection?.kind === "node" ? (fullIndex?.nodes.get(selection.id) ?? null) : null;
  const selectedEdge = selection?.kind === "edge" ? (viewIndex?.edges.get(selection.id) ?? fullIndex?.edges.get(selection.id) ?? null) : null;

  const nodeDetail = useFetch(selectedNode ? selectedNode.id : null, (signal) => api.node(selectedNode!.id, signal));
  const history = useHistory(selectedNode ? selectedNode.id : selectedEdge ? recordId : null, selectedNode ? includeEdges : false);
  const rawAround = useFetch(selectedEdge?.type === "TRANSFERRED_MONEY_TO" ? `raw|${selectedEdge.source}` : null, (signal) =>
    api.rawSubgraph(selectedEdge!.source, signal),
  );

  const verifyResult = lastResult(verify.state);
  const problems = useMemo(() => verifyResult?.chain.problems ?? [], [verifyResult]);

  const ticks = useMemo(() => history.blocks.map((b) => b.idx), [history.blocks]);
  const subject: StripSubject | null =
    selection && ticks.length
      ? { name: selectedNode ? labelFor(selectedNode.id) : `This ${selectedEdge?.type ?? "link"} record`, total: history.total, ticks }
      : null;

  const inspect = useCallback(
    (difference: Difference) => {
      setWelcomeOpen(false);
      if (difference.kind === "node") return selectNode(difference.id, { fit: true });
      const merged = fullIndex?.edgeOfRecord.get(difference.id);
      if (merged) selectEdge(merged.id, { fit: true, record: difference.id });
    },
    [fullIndex, selectNode, selectEdge],
  );

  const onMode = (mode: ViewMode) => {
    if (mode === "full") {
      setView((v) => ({ ...v, mode }));
      requestFit(selection ? [selection.id] : null, false);
      return;
    }
    const center = selectedNode?.id ?? selectedEdge?.source ?? null;
    if (center) setView((v) => ({ ...v, mode, center }));
  };

  const counts = viewGraph?.counts;
  let viewText = "";
  if (subgraph.error && subgraphKey) viewText = `couldn't load the neighbourhood: ${subgraph.error.message}`;
  else if (counts && showingSubgraph) {
    viewText = `neighbourhood(${view.center}, depth=${view.depth}) · ${formatCount(counts.nodes)} nodes · ${formatCount(counts.edge_elements)} links`;
  } else if (counts) {
    viewText = selection ? `full graph · selected ${selection.id}` : `full graph · ${formatCount(counts.nodes)} nodes · ${formatCount(counts.edge_elements)} merged links`;
  } else viewText = "loading the graph";

  const metricLabel = METRICS.find((m) => m.value === metric)!.label;
  const variantLabel = VARIANTS.find((v) => v.value === variant)!.label;

  return (
    <div className={styles.app}>
      <TopBar meta={boot.meta} welcomeOpen={welcomeOpen} onToggleWelcome={() => (welcomeOpen ? closeWelcome() : setWelcomeOpen(true))} />

      <IntegrityBand verify={verify.state} onVerify={verify.run} anchorAvailable={boot.meta?.anchor_available ?? null} subject={subject} highlight={hoverBlock} onInspect={inspect} />

      <main className={styles.body}>
        <Rankings
          metric={metric}
          variant={variant}
          onMetric={setMetric}
          onVariant={setVariant}
          ranking={ranking}
          selectedId={selectedNode?.id ?? null}
          onSelect={(id) => {
            setWelcomeOpen(false);
            selectNode(id, { fit: true });
          }}
        />

        <GraphStage
          meta={boot.meta}
          elements={elements}
          index={viewIndex}
          selection={selection}
          mode={showingSubgraph ? "neighbourhood" : view.mode}
          depth={view.depth}
          viewText={viewText}
          viewLoading={subgraph.loading}
          onMode={onMode}
          onDepth={(depth) => setView((v) => ({ ...v, depth }))}
          onTapNode={(id) => selectNode(id)}
          onTapEdge={(id) => selectEdge(id)}
          onClear={clearSelection}
          fitRequest={fitRequest}
          bootSteps={boot.steps}
          bootError={boot.error}
          onRetryBoot={boot.retry}
          rankOf={(id) => ranks.get(id)?.rank ?? null}
          occludedLeft={welcomeOpen ? WELCOME_WIDTH : 0}
          overlay={
            welcomeOpen && boot.meta && elements ? (
              <Welcome
                meta={boot.meta}
                topBroker={boot.topBroker?.ranking[0] ?? null}
                peopleRanked={boot.topBroker?.people_ranked ?? null}
                sharedName={fullIndex?.nodes.has(SHARED_NAME_ID) ? labelFor(SHARED_NAME_ID) : null}
                onFollowBroker={() => {
                  setWelcomeOpen(false);
                  if (boot.topBroker?.ranking[0]) selectNode(boot.topBroker.ranking[0].node, { fit: true });
                }}
                onSharedName={() => {
                  setWelcomeOpen(false);
                  selectNode(SHARED_NAME_ID, { fit: true });
                }}
                onVerify={() => {
                  closeWelcome();
                  verify.run();
                }}
                onClose={closeWelcome}
              />
            ) : null
          }
        />

        <aside className={styles.evidence} aria-label="Evidence and audit trail">
          {selectedNode ? (
            <NodeDossier
              key={selectedNode.id}
              node={selectedNode}
              detail={nodeDetail}
              links={viewIndex?.edgesByNode.get(selectedNode.id) ?? []}
              rank={ranks.get(selectedNode.id) ?? null}
              rankLabel={metricLabel.toLowerCase()}
              labelFor={labelFor}
              onSelectEdge={(id) => selectEdge(id)}
            />
          ) : selectedEdge && recordId ? (
            <EdgeDossier
              key={selectedEdge.id}
              edge={selectedEdge}
              recordId={recordId}
              onRecord={setRecordId}
              record={history}
              rawAround={selectedEdge.type === "TRANSFERRED_MONEY_TO" ? rawAround : null}
              problems={problems}
              labelFor={labelFor}
              typeFor={typeFor}
              onSelectNode={(id) => selectNode(id, { fit: true })}
            />
          ) : (
            <EmptyEvidence />
          )}
          <AuditTrail
            history={history}
            subjectKind={selectedNode ? "node" : selectedEdge ? "edge" : null}
            onIncludeEdges={setIncludeEdges}
            problems={problems}
            labelFor={labelFor}
            onHoverBlock={setHoverBlock}
          />
        </aside>
      </main>

      <p className={styles.narrow} role="note">
        This explorer is laid out for screens at least 960 px wide. Scroll sideways, or widen the window.
      </p>

      <StatusBar
        meta={boot.meta}
        verify={verify.state}
        drawnLinks={counts?.edge_elements ?? null}
        viewText={showingSubgraph ? `Neighbourhood of ${labelFor(view.center!)}, depth ${view.depth}` : "Full graph, parallel edges merged"}
        rankingText={`${metricLabel.toLowerCase()} · ${variantLabel.toLowerCase()}`}
      />
    </div>
  );
}
