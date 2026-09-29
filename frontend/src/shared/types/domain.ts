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

export type Expense = {
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
  totals: { by_currency: Total[]; by_category: CategoryTotal[] };
  warnings: { document_id: string; filename: string; message: string }[];
  notices: { document_id: string; filename: string; message: string }[];
};
