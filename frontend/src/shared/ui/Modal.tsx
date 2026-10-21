import { X } from "lucide-react";
import { type ReactNode, useEffect } from "react";

export function Modal({
  title,
  children,
  onClose,
  wide = false,
  expanded = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
  expanded?: boolean;
}) {
  useEffect(() => {
    const close = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-zinc-950/30 p-4 backdrop-blur-sm"
      onMouseDown={onClose}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`card max-h-[90vh] w-full overflow-y-auto p-6 ${expanded ? "max-w-7xl" : wide ? "max-w-3xl" : "max-w-md"}`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 className="min-w-0 break-words text-lg font-bold">{title}</h2>
          <button
            className="focus-ring rounded-lg p-2 text-zinc-500 hover:bg-zinc-100"
            onClick={onClose}
            aria-label="Schließen"
          >
            <X size={18} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
