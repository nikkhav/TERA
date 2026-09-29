import {
  ArrowDownToLine,
  FileText,
  LoaderCircle,
  UploadCloud,
} from "lucide-react";
import { useRef, useState } from "react";
import { cn } from "../../shared/lib/cn";
import type { Document } from "../../shared/types/domain";

export function UploadPanel({
  documents,
  uploading,
  onUpload,
  onDownload,
}: {
  documents: Document[];
  uploading: boolean;
  onUpload: (files: File[]) => void;
  onDownload: (document: Document) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const orderedDocuments = [...documents].sort((left, right) =>
    right.created_at.localeCompare(left.created_at),
  );
  return (
    <section className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <h2 className="font-bold">Belege</h2>
        <span className="rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-semibold text-zinc-600">
          {documents.length}
        </span>
      </div>
      <div className="p-4">
        <button
          type="button"
          onClick={() => input.current?.click()}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            onUpload([...event.dataTransfer.files]);
          }}
          className={cn(
            "focus-ring flex w-full flex-col items-center rounded-xl border border-dashed px-4 py-6 transition",
            dragging
              ? "border-moss-500 bg-moss-50"
              : "border-zinc-300 bg-zinc-50/60 hover:border-moss-500 hover:bg-moss-50/50",
          )}
        >
          {uploading ? (
            <LoaderCircle
              className="mb-2 animate-spin text-moss-600"
              size={23}
            />
          ) : (
            <UploadCloud className="mb-2 text-moss-600" size={23} />
          )}
          <span className="text-sm font-semibold">
            {uploading ? "Wird hochgeladen …" : "PDF hinzufügen"}
          </span>
        </button>
        <input
          ref={input}
          className="hidden"
          type="file"
          accept="application/pdf,.pdf"
          multiple
          onChange={(event) => {
            onUpload([...(event.target.files ?? [])]);
            event.target.value = "";
          }}
        />
        {documents.length > 0 && (
          <ul className="mt-3 max-h-80 divide-y divide-line overflow-y-auto pr-1">
            {orderedDocuments.map((document) => (
              <li key={document.id} className="flex items-center gap-3 py-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-red-50 text-red-600">
                  <FileText size={17} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">
                    {document.filename}
                  </p>
                  <p className="mt-0.5 text-xs text-zinc-500">
                    {document.page_count}{" "}
                    {document.page_count === 1 ? "Seite" : "Seiten"} ·{" "}
                    {(document.size_bytes / 1024).toFixed(0)} KB
                  </p>
                </div>
                <button
                  className="focus-ring rounded-lg p-2 text-zinc-400 hover:bg-zinc-100 hover:text-ink"
                  onClick={() => onDownload(document)}
                  title="PDF herunterladen"
                >
                  <ArrowDownToLine size={16} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
