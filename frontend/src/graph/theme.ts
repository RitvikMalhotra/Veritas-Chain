import type { StylesheetJson } from "cytoscape";
import type { EdgeType, ExtractionMethod, NodeType } from "../api/types";

// The one source for entity and link styling: the Cytoscape stylesheet and the legend both read from here.
// Colours were checked with a CVD palette validator on the canvas colour: every pair of node types that shares
// a link differs by ΔE ≥ 15.9 under protanopia/deuteranopia simulation and ≥ 26.5 in normal vision. Person is
// ink because people link to all six other types; no seventh hue cleared that bar.

export const CANVAS = "#10151b";
export const INK = "#e4eaef";
export const INK_2 = "#aab5c0";
export const FONT = '"Atkinson Hyperlegible Next Variable", "Segoe UI", system-ui, sans-serif';

export type NodeShape = "ellipse" | "rectangle" | "round-rectangle" | "diamond" | "hexagon" | "triangle";

export interface NodeStyle {
  color: string;
  shape: NodeShape;
  /** Diameter in screen pixels at any zoom. */
  size: number;
  /** Named at every zoom level once zoomed in; identifiers are only named when lit. */
  labelled: boolean;
}

export const NODE_STYLE: Record<NodeType, NodeStyle> = {
  Person: { color: "#dde4ea", shape: "ellipse", size: 9, labelled: true },
  Phone: { color: "#199e70", shape: "ellipse", size: 5, labelled: false },
  BankAccount: { color: "#c98500", shape: "rectangle", size: 5.5, labelled: false },
  Organization: { color: "#9085e9", shape: "round-rectangle", size: 11, labelled: true },
  Event: { color: "#3987e5", shape: "diamond", size: 12, labelled: true },
  Vehicle: { color: "#d95926", shape: "hexagon", size: 8, labelled: false },
  Location: { color: "#d55181", shape: "triangle", size: 10, labelled: false },
};

export interface LinkFamily {
  label: string;
  short: string;
  color: string;
  /** Resting line opacity; the dense call web sits lowest. */
  opacity: number;
  types: EdgeType[];
}

// Nine link colours would compete at 1,633 lines, so colour says what moved and line style says how we know.
export const LINK_FAMILIES: LinkFamily[] = [
  { label: "Calls and phone use", short: "Calls", color: "#199e70", opacity: 0.2, types: ["CALLED", "USES_PHONE"] },
  { label: "Money and accounts", short: "Money", color: "#c98500", opacity: 0.28, types: ["TRANSFERRED_MONEY_TO", "HOLDS_ACCOUNT"] },
  {
    label: "Affiliation and presence",
    short: "Affiliation",
    color: "#dde4ea",
    opacity: 0.3,
    types: ["MEMBER_OF", "OWNS_VEHICLE", "PRESENT_AT_EVENT", "MET_AT", "ASSOCIATED_WITH"],
  },
];

export const familyOf = (type: EdgeType): number => LINK_FAMILIES.findIndex((f) => f.types.includes(type));

export const METHODS: ExtractionMethod[] = ["structured", "text_pattern", "text_cooccurrence"];

export const METHOD_STYLE: Record<ExtractionMethod, { label: string; dash: number[] | null }> = {
  structured: { label: "From records", dash: null },
  text_pattern: { label: "Report rule", dash: [5, 3] },
  text_cooccurrence: { label: "Same sentence", dash: [1.5, 2.5] },
};

/** A merged edge is drawn in the style of its strongest evidence: a record outranks any text. */
export const strongestMethod = (methods: ExtractionMethod[]): ExtractionMethod =>
  METHODS.find((m) => methods.includes(m)) ?? "structured";

const edgeWidth = (count: number) => Math.min(0.7 + Math.log2(Math.max(count, 1)) * 0.35, 2.6);

/**
 * `px` converts screen pixels to model units (1 / zoom), so nodes, lines and labels keep a legible screen size
 * while the view zooms. The hook rebuilds the stylesheet only when zoom crosses a third of an octave.
 */
export function buildStylesheet(px: number, motion: boolean): StylesheetJson {
  const fade = motion ? { "transition-property": "opacity", "transition-duration": 180, "transition-timing-function": "ease-out" } : {};
  return [
    {
      selector: "node",
      style: {
        label: "",
        "font-family": FONT,
        "font-size": 11 * px,
        "font-weight": 500,
        color: INK_2,
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 4 * px,
        "text-background-color": CANVAS,
        "text-background-opacity": 0.86,
        "text-background-padding": `${2 * px}px`,
        "text-background-shape": "round-rectangle",
        "text-max-width": `${220 * px}px`,
        "text-wrap": "ellipsis",
        "overlay-opacity": 0,
        "z-index-compare": "manual",
        "z-index": 2,
        ...fade,
      },
    },
    ...Object.entries(NODE_STYLE).map(([type, s]) => ({
      selector: `node[type = "${type}"]`,
      style: { "background-color": s.color, shape: s.shape, width: s.size * px, height: s.size * px },
    })),
    { selector: "node.zoomed-labels", style: { label: "data(display)" } },
    {
      selector: "edge",
      style: {
        width: (edge: { data: (key: string) => number }) => edgeWidth(edge.data("count")) * px,
        "curve-style": "bezier",
        "control-point-step-size": 10 * px,
        "target-arrow-shape": "none",
        "arrow-scale": 0.9,
        "overlay-opacity": 0,
        "z-index-compare": "manual",
        "z-index": 1,
        ...fade,
      },
    },
    ...LINK_FAMILIES.map((f, i) => ({
      selector: `edge[family = ${i}]`,
      style: { "line-color": f.color, "target-arrow-color": f.color, "line-opacity": f.opacity },
    })),
    ...METHODS.map((m) => ({
      selector: `edge[method = "${m}"]`,
      style: METHOD_STYLE[m].dash
        ? { "line-style": "dashed", "line-dash-pattern": METHOD_STYLE[m].dash!.map((d) => d * px), "line-cap": m === "text_cooccurrence" ? "round" : "butt" }
        : { "line-style": "solid" },
    })),
    { selector: ".faded", style: { opacity: 0.14, "text-opacity": 0 } },
    { selector: "edge.lit", style: { "line-opacity": 0.95, "target-arrow-shape": "triangle", width: (e: { data: (k: string) => number }) => (edgeWidth(e.data("count")) + 0.9) * px, "z-index": 5 } },
    {
      selector: "node.lit",
      style: { label: "data(display)", color: INK, width: (n: NodeSize) => litSize(n) * px, height: (n: NodeSize) => litSize(n) * px, "z-index": 6 },
    },
    {
      selector: "node.hovered",
      style: { label: "data(display)", color: INK, "underlay-color": INK_2, "underlay-padding": 3 * px, "underlay-opacity": 0.55, "underlay-shape": "ellipse", "z-index": 8 },
    },
    {
      selector: "node.focus",
      style: {
        label: "data(display)",
        color: INK,
        "font-size": 12.5 * px,
        "font-weight": 700,
        "text-margin-y": 8 * px,
        "border-width": 2 * px,
        "border-color": CANVAS,
        "underlay-color": INK,
        "underlay-padding": 4 * px,
        "underlay-opacity": 1,
        "underlay-shape": "ellipse",
        "z-index": 9,
      },
    },
    { selector: "node.label-above", style: { "text-valign": "top", "text-margin-y": -4 * px } },
    { selector: "node.focus.label-above", style: { "text-margin-y": -8 * px } },
    { selector: "edge.hovered", style: { "line-opacity": 0.9, "z-index": 7 } },
    {
      selector: "edge.focus",
      style: { "line-opacity": 1, "target-arrow-shape": "triangle", width: (e: { data: (k: string) => number }) => (edgeWidth(e.data("count")) + 2) * px, "z-index": 9 },
    },
  ] as StylesheetJson;
}

type NodeSize = { data: (key: string) => string };
const litSize = (node: NodeSize) => NODE_STYLE[node.data("type") as NodeType].size * 1.35;
