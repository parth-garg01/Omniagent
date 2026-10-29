export type SseEvent = { event: string; data: any };

/** Incremental SSE parser: feed text chunks, get complete events back. */
export class SseParser {
  private buf = "";

  push(chunk: string): SseEvent[] {
    this.buf += chunk;
    const out: SseEvent[] = [];
    let idx: number;
    while ((idx = this.buf.indexOf("\n\n")) !== -1) {
      const block = this.buf.slice(0, idx);
      this.buf = this.buf.slice(idx + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trim());
      }
      if (data.length) {
        try {
          out.push({ event, data: JSON.parse(data.join("\n")) });
        } catch {
          /* ignore malformed event */
        }
      }
    }
    return out;
  }
}
