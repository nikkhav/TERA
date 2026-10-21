import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "../features/auth/auth-context";
import { apiClient, errorMessage } from "../shared/api/client";

export function PdfPage() {
  const { documentId } = useParams();
  const { user, loading } = useAuth();
  const [url, setUrl] = useState("");
  const file = useQuery({
    queryKey: ["original-pdf", documentId],
    enabled: Boolean(user && documentId),
    queryFn: async ({ signal }) => {
      const response = await apiClient.get<Blob>(
        `/documents/${documentId}/download`,
        { params: { inline: true }, responseType: "blob", signal },
      );
      let filename = "Originalbeleg";
      const encoded = /filename\*=UTF-8''([^;]+)/i.exec(
        response.headers["content-disposition"] ?? "",
      )?.[1];
      if (encoded) {
        try {
          filename = decodeURIComponent(encoded);
        } catch {
          /* Keep a readable fallback for malformed metadata. */
        }
      }
      return { blob: response.data, filename };
    },
    retry: false,
    gcTime: 0,
  });
  useEffect(() => {
    if (!file.data) return;
    const objectUrl = URL.createObjectURL(
      new Blob([file.data.blob], { type: "application/pdf" }),
    );
    setUrl(objectUrl);
    document.title = `${file.data.filename} · TERA`;
    return () => URL.revokeObjectURL(objectUrl);
  }, [file.data]);
  if (loading)
    return (
      <p role="status" className="p-6">
        Anmeldung wird geprüft …
      </p>
    );
  if (!user)
    return (
      <div className="p-6 text-sm">
        <p>Bitte bei TERA anmelden und diesen Tab anschließend neu laden.</p>
        <a
          className="mt-3 inline-block text-moss-700 underline"
          href="/login"
          target="_blank"
          rel="noreferrer"
        >
          Anmelden
        </a>
      </div>
    );
  return (
    <main className="flex h-dvh flex-col bg-zinc-100">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-line bg-white px-5 py-3">
        <h1 className="min-w-0 truncate text-sm font-semibold">
          {file.data?.filename ?? "Originalbeleg"}
        </h1>
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 text-xs text-moss-700 underline"
          >
            Direkt öffnen
          </a>
        )}
      </header>
      {file.isPending && (
        <p role="status" className="p-6 text-sm">
          PDF wird geladen …
        </p>
      )}
      {file.error && (
        <div role="alert" className="p-6 text-sm text-red-700">
          <p>PDF konnte nicht geladen werden. {errorMessage(file.error)}</p>
          <button
            className="mt-3 underline"
            onClick={() => void file.refetch()}
          >
            Erneut laden
          </button>
        </div>
      )}
      {url && (
        <object
          data={url}
          type="application/pdf"
          aria-label="Originalbeleg"
          className="min-h-0 w-full flex-1"
        >
          <p className="p-6 text-sm">
            Die PDF-Ansicht wird von diesem Browser nicht unterstützt.{" "}
            <a
              className="text-moss-700 underline"
              href={url}
              target="_blank"
              rel="noreferrer"
            >
              PDF direkt öffnen
            </a>
          </p>
        </object>
      )}
    </main>
  );
}
