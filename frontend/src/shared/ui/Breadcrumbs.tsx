import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";

type Breadcrumb = {
  label: string;
  to?: string;
};

export function Breadcrumbs({ items }: { items: Breadcrumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-2">
      <ol className="flex min-w-0 items-center gap-1.5 text-xs font-semibold text-zinc-400">
        {items.map((item, index) => {
          const current = index === items.length - 1;
          return (
            <li
              key={`${item.label}-${index}`}
              className="flex min-w-0 items-center gap-1.5"
            >
              {index > 0 && <ChevronRight size={13} className="shrink-0" />}
              {item.to ? (
                <Link
                  to={item.to}
                  className="truncate rounded-md hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-moss-100"
                >
                  {item.label}
                </Link>
              ) : (
                <span
                  className="truncate text-zinc-600"
                  aria-current={current ? "page" : undefined}
                >
                  {item.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
