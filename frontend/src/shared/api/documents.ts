import type { Document } from "../types/domain";
import { apiClient, errorMessage } from "./client";
import { listAll } from "./pagination";

export type UploadResult = {
  uploaded: Document[];
  failed: { filename: string; reason: string }[];
};

export const documentsApi = {
  uploadMany: async (tripId: string, files: File[]): Promise<UploadResult> => {
    const result: UploadResult = { uploaded: [], failed: [] };
    for (const file of files) {
      if (
        file.type !== "application/pdf" &&
        !file.name.toLowerCase().endsWith(".pdf")
      ) {
        result.failed.push({
          filename: file.name,
          reason: "Bitte ein PDF-Dokument auswählen.",
        });
        continue;
      }
      try {
        result.uploaded.push(await documentsApi.upload(tripId, file));
      } catch (error) {
        result.failed.push({
          filename: file.name,
          reason: errorMessage(error),
        });
      }
    }
    return result;
  },
  list: (tripId: string) => listAll<Document>(`/trips/${tripId}/documents`),
  upload: async (tripId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return (await apiClient.post<Document>(`/trips/${tripId}/documents`, form))
      .data;
  },
  remove: async (documentId: string) => {
    await apiClient.delete(`/documents/${documentId}`);
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
