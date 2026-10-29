export type User = { id: string; email: string; role: "user" | "admin" | "evaluator" };
export type Citation = { n: number; filename: string; chunk_index: number; snippet: string; meta?: { page?: number; section?: string } };
export type Msg = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: string;
  citations?: Citation[] | null;
  feedback?: string | null;
};
export type ToolEvent = { name: string; status: string; summary: string; execution_id: string | null };
export type Conversation = { id: string; title: string; updated_at: string };
export type DocumentInfo = {
  id: string; filename: string; version: number; ingestion_status: string;
  error: string | null; access_policy: string; chunk_count: number;
};
