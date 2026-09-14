import { describe, expect, it } from "vitest";
import type { Block } from "../api/types";
import {
  describeBlock,
  displayLabel,
  formatInr,
  formatPhone,
  formatRecordTime,
  formatUtcTime,
  groupSources,
  hashGroups,
  parseDifferences,
  sourceOf,
} from "./format";

const common = { recorded_at: "2026-09-14T15:23:54.159332+00:00", actor: "pipeline", prev_hash: "0".repeat(64), hash: "d13077a1b8463cbd".repeat(4) };

describe("identifiers and amounts", () => {
  it("spaces Indian mobile numbers and leaves anything else alone", () => {
    expect(formatPhone("+919600233059")).toBe("+91 96002 33059");
    expect(formatPhone("+4420")).toBe("+4420");
    expect(displayLabel("Phone", "+917346214717")).toBe("+91 73462 14717");
    expect(displayLabel("BankAccount", "ZKVR0268028 46154561864689")).toBe("ZKVR0268028 · 46154561864689");
    expect(displayLabel("Person", "Rahul Sharma")).toBe("Rahul Sharma");
  });

  it("prints rupees in Indian digit grouping", () => {
    expect(formatInr("505000.00")).toBe("₹5,05,000.00");
    expect(formatInr(5050)).toBe("₹5,050.00");
  });

  it("groups hashes in eights and trims timestamps", () => {
    expect(hashGroups("93578083abc964b25f90fcb3a1896485", 2)).toBe("93578083 abc964b2");
    expect(formatUtcTime("2026-09-14T15:23:54.159332+00:00")).toBe("15:23:54.159 UTC");
    expect(formatRecordTime("2025-03-04T05:40:48+05:30")).toBe("2025-03-04 05:40 IST");
    expect(formatRecordTime("2025-03-04T05:40:48+00:00")).toBe("2025-03-04 05:40 UTC");
  });
});

describe("provenance", () => {
  it("names each record source and separates report text from structured records", () => {
    expect(sourceOf("TXN-000597")).toEqual({ id: "TXN-000597", source: "Bank transactions", fromText: false });
    const grouped = groupSources(["SUB-0004", "KYC-0081", "FIR-DEL-2025-0001", "VEH-0031"]);
    expect(grouped.records.map((d) => d.id)).toEqual(["SUB-0004", "KYC-0081", "VEH-0031"]);
    expect(grouped.text.map((d) => d.source)).toEqual(["Incident report text"]);
  });

  it("describes each kind of audit block from its payload", () => {
    const created: Block = { ...common, idx: 10, operation: "node_created", entity_kind: "node", entity_id: "Person:rahul_sharma", source_id: null, target_id: null, payload: { node: { id: "Person:rahul_sharma", type: "Person", source_document_ids: ["SUB-0004"] } } };
    const merged: Block = { ...common, idx: 298, operation: "node_merged", entity_kind: "node", entity_id: "Person:rahul_sharma", source_id: null, target_id: null, payload: { source_document_ids_added: ["SUB-0100"] } };
    const edge: Block = {
      ...common,
      idx: 23103,
      operation: "edge_created",
      entity_kind: "edge",
      entity_id: "edge:0d66aee4c3e2802a",
      source_id: "BankAccount:A",
      target_id: "BankAccount:B",
      payload: { edge: { id: "edge:0d66aee4c3e2802a", type: "TRANSFERRED_MONEY_TO", source_id: "BankAccount:A", target_id: "BankAccount:B", timestamp: "2025-03-04T05:40:48+05:30", extraction_method: "structured", confidence: 1, source_document_id: "TXN-000597", amount_inr: "505000.00" } },
    };
    expect(describeBlock(created)).toBe("Created Person from SUB-0004");
    expect(describeBlock(merged)).toBe("Exact-match merge added SUB-0100");
    expect(describeBlock(edge, (id) => id.slice(-1))).toBe("TRANSFERRED_MONEY_TO A → B · TXN-000597 · structured 1.00 · ₹5,05,000.00");
  });

  it("reads which node or edge a verify difference points at", () => {
    // The formats written by veritas/audit/replay.py graph_differences.
    expect(parseDifferences(["edge edge:0d66aee4c3e2802a differs", "node Person:x attributes differ", "edge edge:1 only in actual", "... 3 more"])).toEqual([
      { kind: "edge", id: "edge:0d66aee4c3e2802a", text: "edge edge:0d66aee4c3e2802a differs" },
      { kind: "node", id: "Person:x", text: "node Person:x attributes differ" },
      { kind: "edge", id: "edge:1", text: "edge edge:1 only in actual" },
    ]);
  });
});
