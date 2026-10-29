import type { Citation } from "../../api/types";

export function CitationList({ citations }: { citations: Citation[] }) {
  return (
    <ul className="citations" aria-label="Sources">
      {citations.map((c) => (
        <li key={c.n} title={c.snippet}>
          <strong>[{c.n}]</strong> {c.filename}
          {c.meta?.page ? ` · p.${c.meta.page}` : ""}
          {c.meta?.section ? ` · ${c.meta.section}` : ""}
        </li>
      ))}
    </ul>
  );
}
