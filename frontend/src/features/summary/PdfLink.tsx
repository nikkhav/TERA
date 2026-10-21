import { ExternalLink } from "lucide-react";

export function PdfLink({
  documentId,
  filename,
}: {
  documentId: string;
  filename: string;
}) {
  return (
    <a
      href={`/documents/${encodeURIComponent(documentId)}/view`}
      target="_blank"
      rel="noopener noreferrer"
      className="focus-ring inline-flex items-center gap-1.5 text-sm text-moss-700 underline underline-offset-2"
      title={filename}
      aria-label={`PDF ansehen: ${filename} (neuer Tab)`}
    >
      PDF ansehen <ExternalLink size={14} aria-hidden="true" />
    </a>
  );
}
