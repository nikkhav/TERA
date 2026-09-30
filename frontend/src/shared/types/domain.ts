export type User = {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  user: User;
};
export type Employee = { id: string; name: string; created_at: string };

export type Trip = {
  id: string;
  employee_id: string;
  name: string;
  starts_on: string | null;
  ends_on: string | null;
  created_at: string;
};

export type Document = {
  id: string;
  trip_id: string;
  filename: string;
  size_bytes: number;
  page_count: number;
  created_at: string;
};

export type Job = {
  id: string;
  trip_id: string;
  status: "queued" | "running" | "completed" | "needs_review" | "failed";
  document_ids: string[];
  completed_chunks: number;
  total_chunks: number;
  error: string | null;
  created_at: string;
  finished_at: string | null;
};

export type Total = {
  currency: string | null;
  confirmed: string;
  in_review: string;
  excluded: string;
  unknown_amounts: number;
};

export type ExpenseCategory =
  "Hotel" | "Flugreisen" | "Verpflegung" | "Sonstige Ausgaben";

export type ExchangeRate = {
  currency: string | null;
  rate: string | null;
  requested_on: string | null;
  as_of: string | null;
  source: string;
  source_url: string;
  error: string | null;
};
export type ReceiptItem = {
  description: string;
  category: ExpenseCategory | null;
  net: string | null;
  tax: string | null;
  gross: string | null;
  is_breakfast: boolean;
  evidence: { page: number; quote: string; field: string | null }[];
};
export type ReceiptFacts = {
  merchant: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  service_start: string | null;
  service_end: string | null;
  currency: string | null;
  category: ExpenseCategory | null;
  total: string | null;
  net_total: string | null;
  tax_total: string | null;
  breakfast_total: string | null;
  breakfast_net: string | null;
  breakfast_tax: string | null;
  items: ReceiptItem[];
  overnight_count: number | null;
  room_count: number | null;
  transport_mode: string | null;
  distance_km: string | null;
  origin: string | null;
  destination: string | null;
  flight_number: string | null;
};
export type Expense = {
  amount_eur: string | null;
  exchange_rate: ExchangeRate | null;
  document_id: string;
  filename: string;
  date: string | null;
  service_start: string | null;
  service_end: string | null;
  merchant: string | null;
  currency: string | null;
  status: string;
  pages: number[];
  category: ExpenseCategory;
  description: string;
  amount: string | null;
};

export type CategoryTotal = Total & { category: ExpenseCategory };

export type ReviewDecision = "approved" | "rejected" | "pending";
export type ReviewEvent = {
  decision: ReviewDecision;
  comment: string;
  user_id: string;
  user_name: string;
  reviewed_at: string;
};
export type DocumentResult = {
  facts: ReceiptFacts;
  original_texts: {
    merchant?: string;
    items?: string[];
    warnings?: string[];
    notices?: string[];
  };
  exchange_rate: ExchangeRate | null;
  correction_history: {
    user_name: string;
    corrected_at: string;
    comment: string;
    before: ReceiptFacts;
    after: ReceiptFacts;
  }[];
  document_id: string;
  filename: string;
  status: string;
  extraction_failed: boolean;
  warnings: string[];
  notices: string[];
  sources: { page: number; quote: string; field: string | null }[];
  review_history: ReviewEvent[];
};

export type Summary = {
  schema_version: number;
  job_id: string;
  trip_id: string;
  status: Job["status"];
  is_stale: boolean;
  coverage: {
    supplied: number;
    processed: number;
    failed: number;
    needs_review: number;
  };
  documents: DocumentResult[];
  expenses: Expense[];
  totals: {
    by_currency: Total[];
    by_category: CategoryTotal[];
    eur: Total[];
    by_category_eur: CategoryTotal[];
  };
  warnings: { document_id: string; filename: string; message: string }[];
  notices: { document_id: string; filename: string; message: string }[];
};
