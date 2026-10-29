import { describe, expect, it } from "vitest";
import { SseParser } from "./sse";

describe("SseParser", () => {
  it("parses events split across chunks", () => {
    const p = new SseParser();
    expect(p.push('event: delta\ndata: {"text":"Hel')).toEqual([]);
    const out = p.push('lo"}\n\nevent: done\ndata: {"id":"1"}\n\n');
    expect(out).toEqual([
      { event: "delta", data: { text: "Hello" } },
      { event: "done", data: { id: "1" } },
    ]);
  });

  it("ignores malformed json", () => {
    expect(new SseParser().push("event: x\ndata: {nope\n\n")).toEqual([]);
  });
});
