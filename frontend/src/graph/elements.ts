import type { ElementDefinition } from "cytoscape";
import type { GraphResponse, MergedEdgeData, NodeData, NodeElement } from "../api/types";
import { displayLabel } from "../lib/format";
import { familyOf, strongestMethod } from "./theme";

export interface GraphIndex {
  nodes: Map<string, NodeData>;
  edges: Map<string, MergedEdgeData>;
  /** Merged edges touching each node, in API order. */
  edgesByNode: Map<string, MergedEdgeData[]>;
  /** Underlying edge record id → the merged edge that draws it. */
  edgeOfRecord: Map<string, MergedEdgeData>;
}

export function indexGraph(graph: GraphResponse): GraphIndex {
  const nodes = new Map<string, NodeData>();
  const edges = new Map<string, MergedEdgeData>();
  const edgesByNode = new Map<string, MergedEdgeData[]>();
  const edgeOfRecord = new Map<string, MergedEdgeData>();
  for (const element of graph.elements) {
    if (element.group === "nodes") {
      nodes.set(element.data.id, element.data);
      continue;
    }
    const e = element.data;
    edges.set(e.id, e);
    for (const end of [e.source, e.target]) {
      const list = edgesByNode.get(end) ?? [];
      list.push(e);
      edgesByNode.set(end, list);
    }
    for (const record of e.edge_ids) edgeOfRecord.set(record, e);
  }
  return { nodes, edges, edgesByNode, edgeOfRecord };
}

/** API elements plus the fields the stylesheet selects on; positions come from the server's seeded layout. */
export function toCytoscape(graph: GraphResponse): ElementDefinition[] {
  return graph.elements.map((element) => {
    if (element.group === "nodes") {
      const node = element as NodeElement;
      return {
        group: "nodes",
        data: { ...node.data, display: displayLabel(node.data.type, node.data.label) },
        position: { ...node.position },
      };
    }
    const e = element.data;
    return { group: "edges", data: { ...e, family: familyOf(e.type), method: strongestMethod(e.extraction_methods) } };
  });
}
