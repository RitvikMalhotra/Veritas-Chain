import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { EDGE_TYPES, NODE_TYPES, type ExtractionMethod } from "../api/types";
import { buildStylesheet, familyOf, LINK_FAMILIES, METHOD_STYLE, NODE_STYLE, strongestMethod } from "./theme";

// The committed Phase 3 build report lists every node type and "EDGE_TYPE (method)" pair the graph contains.
const report = JSON.parse(readFileSync(new URL("../../../output/phase3/build_report.json", import.meta.url), "utf8")) as {
  nodes_by_type: Record<string, number>;
  edges_by_type: Record<string, number>;
};

describe("graph theme covers the graph it draws", () => {
  it("styles every node type in the build, each with its own colour and shape pair", () => {
    for (const type of Object.keys(report.nodes_by_type)) expect(NODE_TYPES).toContain(type);
    const pairs = new Set(NODE_TYPES.map((t) => `${NODE_STYLE[t].color}|${NODE_STYLE[t].shape}`));
    expect(pairs.size).toBe(NODE_TYPES.length);
    expect(new Set(NODE_TYPES.map((t) => NODE_STYLE[t].color)).size).toBe(NODE_TYPES.length);
  });

  it("puts every edge type in exactly one link family and every method in a line style", () => {
    for (const key of Object.keys(report.edges_by_type)) {
      const [, type, method] = /^(\w+) \((\w+)\)$/.exec(key)!;
      expect(EDGE_TYPES).toContain(type);
      expect(familyOf(type as (typeof EDGE_TYPES)[number])).toBeGreaterThanOrEqual(0);
      expect(METHOD_STYLE[method as ExtractionMethod]).toBeDefined();
    }
    expect(LINK_FAMILIES.flatMap((f) => f.types).sort()).toEqual([...EDGE_TYPES].sort());
  });

  it("draws a merged edge in the style of its strongest evidence", () => {
    expect(strongestMethod(["text_pattern", "structured"])).toBe("structured");
    expect(strongestMethod(["text_cooccurrence", "text_pattern"])).toBe("text_pattern");
  });

  it("keeps screen sizes constant across zoom by scaling model units", () => {
    const sheet = buildStylesheet(0.5, false) as Array<{ selector: string; style: Record<string, unknown> }>;
    const person = sheet.find((b) => b.selector === 'node[type = "Person"]')!;
    expect(person.style.width).toBe(NODE_STYLE.Person.size * 0.5);
  });
});
