export type KnowledgeConfig = {
  chunk_size: number;
  chunk_overlap: number;
  markdown_aware: boolean;
  embedding_provider: "gemini";
  embedding_model: "gemini-embedding-001";
  embedding_dimensions: 768;
  normalize_embeddings: true;
  supported_sources: ("text" | "pdf" | "txt" | "markdown")[];
  extraction_max_chars: number;
};
export type KnowledgeBase = {
  id: string;
  name: string;
  config: KnowledgeConfig;
};
export type KnowledgeSource = {
  id: string;
  title: string;
  kind: string;
  status: string;
  error: string | null;
};
