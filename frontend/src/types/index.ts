// Chat types
export interface SourceCitation {
  document_id: string;
  filename: string;
  category: string;
  page_number: number | null;
  chunk_text: string;
  relevance_score: number;
  // Section metadata — present for semantically-chunked documents, undefined for legacy
  section_title?: string | null;
  section_path?: string | null;
  chunk_type?: string | null;
}

export interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  sources: SourceCitation[];
  created_at: string;
}

export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

export interface ConversationListItem {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ChatResponse {
  conversation_id: number;
  message_id: number;
  answer: string;
  sources: SourceCitation[];
  query_time_ms: number;
}

// Document types
export interface Document {
  id: number;
  filename: string;
  original_filename: string;
  category: string;
  description: string | null;
  chunk_count: number;
  status: 'pending' | 'indexing' | 'indexed' | 'error';
  file_size_bytes: number;
  uploaded_at: string;
  indexed_at: string | null;
}

// Analytics types
export interface AnalyticsSummary {
  total_questions: number;
  total_conversations: number;
  total_documents: number;
  total_chunks: number;
  helpful_count: number;
  not_helpful_count: number;
  avg_response_time_ms: number;
  top_queries: { query: string; count: number }[];
  feedback_by_day: { date: string; rating: string; count: number }[];
  questions_by_day: { date: string; count: number }[];
}

export const DOCUMENT_CATEGORIES = [
  'general',
  'academics',
  'placements',
  'hostel',
  'clubs',
  'policies',
  'faq',
  'internships',
] as const;

export type DocumentCategory = (typeof DOCUMENT_CATEGORIES)[number];
