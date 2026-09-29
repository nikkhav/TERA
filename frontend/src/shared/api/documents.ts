import type { Document } from "../types/domain";
import { apiClient } from "./client";
import { listAll } from "./pagination";

export const documentsApi = {
  list: (tripId: string) => listAll<Document>(`/trips/${tripId}/documents`),
  upload: async (tripId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return (await apiClient.post<Document>(`/trips/${tripId}/documents`, form))
      .data;
  },
  download: async (document: Pick<Document, "id" | "filename">) => {
    const response = await apiClient.get<Blob>(
      `/documents/${document.id}/download`,
      {
        responseType: "blob",
      },
    );
    return { blob: response.data, filename: document.filename };
  },
};
