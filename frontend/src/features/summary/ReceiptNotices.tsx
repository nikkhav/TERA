import { Info } from "lucide-react";

type Notice = { document_id: string; filename: string; message: string };

export function ReceiptNotices({
  notices,
  onReview,
}: {
  notices: Notice[];
  onReview?: (documentId: string) => void;
}) {
  if (!notices.length) return null;
  const groups = new Map<string, Map<string, Notice>>();
  for (const notice of notices) {
    const documents = groups.get(notice.message) ?? new Map<string, Notice>();
    documents.set(notice.document_id, notice);
    groups.set(notice.message, documents);
  }
  return (
    <section className="rounded-2xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-950">
      <h3 className="mb-3 flex items-center gap-2 font-semibold">
        <Info size={17} />
        Beleghinweise
      </h3>
      <ul className="max-h-64 space-y-3 overflow-y-auto">
        {Array.from(groups, ([message, documents]) => (
          <li key={message}>
            <p className="font-medium">{message}</p>
            <ul className="mt-1 list-disc space-y-1 pl-4 text-xs">
              {Array.from(documents.values(), (notice) => (
                <li key={notice.document_id} className="break-words">
                  {onReview ? (
                    <button
                      className="text-left underline underline-offset-2"
                      onClick={() => onReview(notice.document_id)}
                    >
                      {notice.filename}
                    </button>
                  ) : (
                    notice.filename
                  )}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  );
}
