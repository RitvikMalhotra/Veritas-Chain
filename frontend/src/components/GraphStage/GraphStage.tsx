import type { ElementDefinition } from "cytoscape";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import type { Meta } from "../../api/types";
import type { GraphIndex } from "../../graph/elements";
import { useCytoscape, type GraphSelection, type HoverTarget, type Insets } from "../../graph/useCytoscape";
import type { BootStep } from "../../state/hooks";
import { Button, SegmentedControl } from "../ui/controls";
import { BootLog } from "./BootLog";
import styles from "./GraphStage.module.css";
import { HoverCard } from "./HoverCard";
import { Legend } from "./Legend";

export type ViewMode = "full" | "neighbourhood";

export interface FitRequest {
  ids: string[] | null;
  nonce: number;
  animate: boolean;
}

const HOVER_DELAY = 250;
const HOVER_WARM = 500; // after a card closes, the next one opens without the delay

export function GraphStage({
  meta,
  elements,
  index,
  selection,
  mode,
  depth,
  viewText,
  viewLoading,
  onMode,
  onDepth,
  onTapNode,
  onTapEdge,
  onClear,
  fitRequest,
  bootSteps,
  bootError,
  onRetryBoot,
  rankOf,
  overlay,
  occludedLeft = 0,
}: {
  meta: Meta | null;
  elements: ElementDefinition[] | null;
  index: GraphIndex | null;
  selection: GraphSelection;
  mode: ViewMode;
  depth: number;
  viewText: string;
  viewLoading: boolean;
  onMode: (mode: ViewMode) => void;
  onDepth: (depth: number) => void;
  onTapNode: (id: string) => void;
  onTapEdge: (id: string) => void;
  onClear: () => void;
  fitRequest: FitRequest;
  bootSteps: BootStep[];
  bootError: Error | null;
  onRetryBoot: () => void;
  rankOf: (id: string) => number | null;
  overlay?: ReactNode;
  /** Width covered by a docked panel at the left of the canvas (the welcome panel). */
  occludedLeft?: number;
}) {
  const [hovered, setHovered] = useState<HoverTarget | null>(null);
  const [legendOpen, setLegendOpen] = useState(true);
  const legendRef = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const timer = useRef<number | undefined>(undefined);
  const lastClosed = useRef(0);
  const shown = useRef(false);

  const onHover = useCallback((target: HoverTarget | null) => {
    window.clearTimeout(timer.current);
    if (!target) {
      if (shown.current) lastClosed.current = performance.now();
      shown.current = false;
      setHovered(null);
      return;
    }
    const open = () => {
      shown.current = true;
      setHovered(target);
    };
    if (performance.now() - lastClosed.current < HOVER_WARM) open();
    else timer.current = window.setTimeout(open, HOVER_DELAY);
  }, []);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const { containerRef, fit, zoomBy } = useCytoscape({ elements, selection, hovered, onTapNode, onTapEdge, onTapBackground: onClear, onHover });

  // The legend sits in the bottom-left corner: keep the graph either above it or beside it, whichever is larger.
  const insets = useCallback((): Insets[] => {
    const legend = legendRef.current;
    const base = { top: 40, right: 56, bottom: 40, left: Math.max(56, occludedLeft + 24) };
    if (!legend || !legendOpen) return [base];
    return [
      { ...base, bottom: legend.offsetHeight + 28 },
      { ...base, left: Math.max(base.left, legend.offsetWidth + 28) },
    ];
  }, [legendOpen, occludedLeft]);

  // Declared after useCytoscape, so it runs after the hook has swapped elements: a fit requested with a view change fits the new view.
  useEffect(() => {
    if (elements && fitRequest.nonce > 0) fit(fitRequest.ids, insets(), fitRequest.animate);
  }, [fitRequest]); // on request only: a redraw alone must not move the camera

  const ready = Boolean(elements);
  const selectionFitIds = selection ? [selection.id] : null;

  return (
    <section className={styles.stage} aria-label="Graph">
      <div className={styles.viewbar}>
        <SegmentedControl
          label="View"
          className={styles.mode}
          value={mode}
          onChange={onMode}
          choices={[
            { value: "full", label: "Full graph" },
            { value: "neighbourhood", label: "Neighbourhood", disabled: !selection, description: selection ? undefined : "Select a node first" },
          ]}
        />
        <span className={styles.depth}>
          <span id="depth-label">Depth</span>
          <SegmentedControl
            label="Neighbourhood depth"
            className={styles.depthControl}
            value={depth}
            onChange={onDepth}
            disabled={mode !== "neighbourhood"}
            choices={[1, 2, 3].map((d) => ({ value: d, label: String(d) }))}
          />
        </span>
        <p className={styles.expr} aria-live="polite" title={viewText}>
          {viewLoading ? <b>loading · </b> : null}
          {viewText}
        </p>
        <Button iconOnly icon="fit" title="Fit the selection" aria-label="Fit the selection" disabled={!selection || !ready} onClick={() => fit(selectionFitIds, insets())} />
        <Button iconOnly icon="reset" title="Reset view" aria-label="Reset view" disabled={!ready} onClick={() => fit(null, insets())} />
      </div>

      <div ref={wrapRef} className={styles.canvasWrap}>
        <div ref={containerRef} className={styles.canvas} data-ready={ready} aria-label={meta ? `Graph of ${meta.graph.nodes} nodes; use Key people or the evidence pane to navigate by keyboard` : "Graph"} role="img" />

        {!ready ? <BootLog steps={bootSteps} error={bootError} onRetry={onRetryBoot} /> : null}

        {ready && meta ? (
          <>
            <div ref={legendRef} className={styles.legendDock}>
              <Legend meta={meta} open={legendOpen} onToggle={() => setLegendOpen((o) => !o)} />
            </div>
            <div className={styles.zoom}>
              <Button iconOnly icon="plus" title="Zoom in" aria-label="Zoom in" onClick={() => zoomBy(1.4)} />
              <Button iconOnly icon="minus" title="Zoom out" aria-label="Zoom out" onClick={() => zoomBy(1 / 1.4)} />
            </div>
          </>
        ) : null}

        {hovered && index ? (
          <HoverCard target={hovered} index={index} rankOf={rankOf} bounds={{ width: wrapRef.current?.clientWidth ?? 0, height: wrapRef.current?.clientHeight ?? 0 }} />
        ) : null}
        {overlay}
      </div>
    </section>
  );
}
