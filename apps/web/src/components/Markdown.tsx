import ReactMarkdown from "react-markdown";

// react-markdown does not render raw HTML by default; links are restricted to safe protocols.
export function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown
      urlTransform={(url) => (/^(https?:|mailto:)/i.test(url) ? url : "")}
      components={{ a: (p) => <a {...p} target="_blank" rel="noreferrer noopener" /> }}
    >
      {text}
    </ReactMarkdown>
  );
}
