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
  return (
    <section className="rounded-2xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-950">
      <h3 className="mb-3 flex items-center gap-2 font-semibold">
        <Info size={17} />
        Beleghinweise
      </h3>
      <ul className="max-h-64 space-y-3 overflow-y-auto">
        {notices.map((notice, index) => (
          <li key={`${notice.document_id}-${index}`}>
            <p>{notice.message}</p>
            {onReview ? (
              <button
                className="mt-1 text-xs underline underline-offset-2"
                onClick={() => onReview(notice.document_id)}
              >
                {notice.filename}
              </button>
            ) : (
              <p className="mt-1 text-xs">{notice.filename}</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
