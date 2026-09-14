import cytoscape, { type Core, type EdgeSingular, type ElementDefinition, type EventObject, type NodeSingular } from "cytoscape";
import { useCallback, useEffect, useRef, useState } from "react";
import { buildStylesheet, NODE_STYLE } from "./theme";
import type { NodeType } from "../api/types";

export type GraphSelection = { kind: "node"; id: string } | { kind: "edge"; id: string } | null;

export interface HoverTarget {
  kind: "node" | "edge";
  id: string;
  /** Pointer-anchored position inside the container, in CSS pixels. */
  x: number;
  y: number;
}

export interface Insets {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

interface Options {
  elements: ElementDefinition[] | null;
  selection: GraphSelection;
  hovered: HoverTarget | null;
  onTapNode: (id: string) => void;
  onTapEdge: (id: string) => void;
  onTapBackground: () => void;
  onHover: (target: HoverTarget | null) => void;
}

const LABEL_ZOOM = 0.9; // Person, Organization and Event names appear once the view is zoomed in this far
const CAMERA_MS = 380;
const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Canvas labels don't avoid each other, so a lit neighbourhood can print one name over another. Labels keep a fixed
 * screen size, so placement is decided in screen space: the selection keeps its label below, and any other label
 * whose spot below is taken moves above its node if that spot is free.
 */
function placeLabels(cy: Core) {
  const lit = cy.nodes(".lit");
  cy.batch(() => {
    cy.nodes(".label-above").removeClass("label-above");
    const taken: Array<{ x1: number; x2: number; y1: number; y2: number }> = [];
    const hit = (b: (typeof taken)[number]) => taken.some((t) => b.x1 < t.x2 && b.x2 > t.x1 && b.y1 < t.y2 && b.y2 > t.y1);
    const ordered = lit.sort((a, b) => Number(b.hasClass("focus")) - Number(a.hasClass("focus")) || a.renderedPosition().y - b.renderedPosition().y);
    ordered.forEach((node) => {
      const p = node.renderedPosition();
      const width = String(node.data("display")).length * 6.6 + 10;
      const offset = node.renderedHeight() / 2 + (node.hasClass("focus") ? 9 : 5);
      const below = { x1: p.x - width / 2, x2: p.x + width / 2, y1: p.y + offset, y2: p.y + offset + 18 };
      const above = { ...below, y1: p.y - offset - 18, y2: p.y - offset };
      if (hit(below) && !hit(above)) {
        node.addClass("label-above");
        taken.push(above);
      } else taken.push(below);
    });
  });
}

/** Owns one Cytoscape instance for the life of the page; React state drives its elements and classes. */
export function useCytoscape({ elements, selection, hovered, onTapNode, onTapEdge, onTapBackground, onHover }: Options) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const handlers = useRef({ onTapNode, onTapEdge, onTapBackground, onHover });
  handlers.current = { onTapNode, onTapEdge, onTapBackground, onHover };
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const motion = !reducedMotion();
    const cy = cytoscape({
      container,
      style: buildStylesheet(1, motion),
      layout: { name: "preset" },
      minZoom: 0.04,
      maxZoom: 6,
      boxSelectionEnabled: false,
      autoungrabify: true, // positions come from the server's seeded layout; dragging would redraw the evidence map
      selectionType: "single",
      pixelRatio: "auto",
    });
    cyRef.current = cy;

    let bucket = NaN;
    let frame = 0;
    const restyle = () => {
      frame = 0;
      const zoom = cy.zoom();
      const next = Math.round(Math.log2(zoom) * 3) / 3;
      if (next !== bucket) {
        bucket = next;
        cy.style().fromJson(buildStylesheet(1 / 2 ** next, motion)).update();
      }
      const labelled = zoom >= LABEL_ZOOM;
      if (cy.scratch("_labels") !== labelled) {
        cy.scratch("_labels", labelled);
        cy.batch(() => {
          const named = cy.nodes().filter((n) => NODE_STYLE[n.data("type") as NodeType].labelled);
          if (labelled) named.addClass("zoomed-labels");
          else named.removeClass("zoomed-labels");
        });
      }
    };
    cy.on("zoom", () => {
      if (!frame) frame = requestAnimationFrame(restyle);
    });
    let settle = 0;
    cy.on("viewport", () => {
      window.clearTimeout(settle);
      settle = window.setTimeout(() => placeLabels(cy), 60); // once the camera stops, distances between labels are final
    });
    cy.on("viewport", () => handlers.current.onHover(null));

    const anchor = (event: EventObject) => ({ x: event.renderedPosition.x, y: event.renderedPosition.y });
    cy.on("tap", (event) => {
      handlers.current.onHover(null); // a click answers the preview; the evidence pane takes over
      if (event.target === cy) handlers.current.onTapBackground();
      else if (event.target.isNode()) handlers.current.onTapNode(event.target.id());
      else handlers.current.onTapEdge(event.target.id());
    });
    cy.on("mouseover", "node, edge", (event) => {
      container.style.cursor = "pointer";
      handlers.current.onHover({ kind: event.target.isNode() ? "node" : "edge", id: event.target.id(), ...anchor(event) });
    });
    cy.on("mouseout", "node, edge", () => {
      container.style.cursor = "";
      handlers.current.onHover(null);
    });

    // Canvas text is drawn with whatever font is loaded at the time; redraw once the variable fonts arrive.
    document.fonts?.ready.then(() => cy.style().update());
    setReady(true);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.clearTimeout(settle);
      cy.destroy();
      cyRef.current = null;
    };
  }, []);

  // Swap elements when the view changes; the preset layout draws instantly from server positions.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !elements) return;
    cy.batch(() => {
      cy.elements().remove();
      cy.add(elements);
    });
    cy.scratch("_labels", undefined);
    cy.layout({ name: "preset", fit: true, padding: 32 }).run();
    cy.emit("zoom");
  }, [elements, ready]);

  // Selection: the element and its neighbourhood stay lit, everything else fades back to context.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.elements().removeClass("faded lit focus");
      if (!selection) return;
      const target = cy.getElementById(selection.id);
      if (target.empty()) return;
      const lit = target.isNode() ? (target as NodeSingular).closedNeighborhood() : (target as EdgeSingular).connectedNodes().union(target);
      cy.elements().not(lit).addClass("faded");
      lit.addClass("lit");
      target.addClass("focus");
    });
    placeLabels(cy);
  }, [selection, elements, ready]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements(".hovered").removeClass("hovered");
    if (hovered) cy.getElementById(hovered.id).addClass("hovered");
  }, [hovered, elements]);

  /** Fits the given ids (or the whole view) clear of overlays; of several inset layouts, the one allowing the largest zoom wins. */
  const fit = useCallback((ids: string[] | null, layouts: Insets[], animate = true) => {
    const cy = cyRef.current;
    if (!cy) return;
    let eles = cy.elements();
    if (ids) {
      const chosen = ids.reduce((acc, id) => acc.union(cy.getElementById(id)), cy.collection());
      eles = chosen.union(chosen.nodes().closedNeighborhood()).union(chosen.edges().connectedNodes()); // show what the selection connects to
    }
    if (eles.empty()) return;
    const box = eles.boundingBox({ includeLabels: false, includeOverlays: false });
    const candidates = layouts
      .map((insets) => {
        const width = cy.width() - insets.left - insets.right;
        const height = cy.height() - insets.top - insets.bottom;
        return { insets, width, height, zoom: Math.min(width / Math.max(box.w, 1), height / Math.max(box.h, 1)) };
      })
      .filter((c) => c.width > 0 && c.height > 0)
      .sort((a, b) => b.zoom - a.zoom);
    if (!candidates.length) return;
    const { insets, width, height } = candidates[0];
    const zoom = Math.min(Math.max(candidates[0].zoom, cy.minZoom()), ids ? 2.2 : cy.maxZoom());
    const pan = {
      x: insets.left + width / 2 - zoom * (box.x1 + box.w / 2),
      y: insets.top + height / 2 - zoom * (box.y1 + box.h / 2),
    };
    cy.stop(true, false);
    if (animate && !reducedMotion()) cy.animate({ zoom, pan }, { duration: CAMERA_MS, easing: "ease-in-out-cubic" });
    else cy.viewport({ zoom, pan });
  }, []);

  const zoomBy = useCallback((factor: number) => {
    const cy = cyRef.current;
    if (!cy) return;
    const level = Math.min(Math.max(cy.zoom() * factor, cy.minZoom()), cy.maxZoom());
    const pan = cy.pan();
    const zoom = cy.zoom();
    const position = { x: (cy.width() / 2 - pan.x) / zoom, y: (cy.height() / 2 - pan.y) / zoom }; // view centre, in model units
    cy.stop(true, false);
    if (reducedMotion()) cy.zoom({ level, position });
    else cy.animate({ zoom: { level, position } }, { duration: 200, easing: "ease-out-cubic" });
  }, []);

  return { containerRef, fit, zoomBy };
}
