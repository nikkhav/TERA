import type {
  Job,
  Summary,
  ReviewDecision,
  ReceiptFacts,
} from "../types/domain";
import { apiClient } from "./client";

export const summariesApi = {
  resolveRelationship: async (
    jobId: string,
    documentIds: string[],
    resolution: "same_expense" | "separate" | "pending",
    primaryDocumentId?: string,
  ) =>
    (
      await apiClient.put<Summary>(`/summary-jobs/${jobId}/relationships`, {
        document_ids: documentIds,
        resolution,
        primary_document_id: primaryDocumentId ?? null,
      })
    ).data,
  list: async (tripId: string) =>
    (await apiClient.get<Job[]>(`/trips/${tripId}/summaries`)).data,
  generate: async (tripId: string, force = false) =>
    (
      await apiClient.post<Job>(`/trips/${tripId}/summaries`, null, {
        params: { force },
      })
    ).data,
  job: async (jobId: string) =>
    (await apiClient.get<Job>(`/summary-jobs/${jobId}`)).data,
  result: async (jobId: string) =>
    (await apiClient.get<Summary>(`/summary-jobs/${jobId}/result`)).data,
  correct: async (
    jobId: string,
    documentId: string,
    facts: ReceiptFacts,
    comment: string,
  ) =>
    (
      await apiClient.put<Summary>(
        `/summary-jobs/${jobId}/documents/${documentId}/correction`,
        { facts, comment },
      )
    ).data,
  review: async (
    jobId: string,
    documentId: string,
    decision: ReviewDecision,
    comment: string,
  ) =>
    (
      await apiClient.put<Summary>(
        `/summary-jobs/${jobId}/documents/${documentId}/review`,
        { decision, comment },
      )
    ).data,
};
