import {
  BriefcaseBusiness,
  CalendarDays,
  ChevronRight,
  Search,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { formatDate } from "../../shared/lib/format";
import type { Trip } from "../../shared/types/domain";
import { Button } from "../../shared/ui/Button";
import { EmptyState } from "../../shared/ui/EmptyState";

const PAGE_SIZE = 12;

export function TripList({ trips }: { trips: Trip[] }) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const filtered = [...trips]
    .sort(
      (a, b) =>
        (b.starts_on ?? b.created_at).localeCompare(
          a.starts_on ?? a.created_at,
        ) || a.name.localeCompare(b.name, "de"),
    )
    .filter((trip) =>
      trip.name
        .toLocaleLowerCase("de")
        .includes(search.trim().toLocaleLowerCase("de")),
    );
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  if (!trips.length)
    return (
      <div className="card">
        <EmptyState icon={BriefcaseBusiness} title="Noch keine Reisen" />
      </div>
    );
  return (
    <section className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-5">
        <p className="text-sm font-semibold text-zinc-500">
          {filtered.length} {filtered.length === 1 ? "Reise" : "Reisen"}
        </p>
        <label className="relative w-full sm:w-72">
          <Search size={16} className="absolute left-3 top-3 text-zinc-400" />
          <input
            type="search"
            className="field pl-9"
            placeholder="Reisen suchen"
            aria-label="Reisen suchen"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(0);
            }}
          />
        </label>
      </div>
      <div className="max-h-[65vh] divide-y divide-line overflow-y-auto">
        {filtered
          .slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE)
          .map((trip) => (
            <Link
              key={trip.id}
              to={`/employees/${trip.employee_id}/trips/${trip.id}`}
              className="focus-ring group flex items-center gap-4 px-5 py-6 transition hover:bg-moss-50 sm:gap-5 sm:px-6"
            >
              <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-moss-50 text-moss-700 group-hover:bg-moss-100">
                <BriefcaseBusiness size={22} />
              </span>
              <div className="min-w-0 flex-1">
                <h2 className="break-words text-base font-bold sm:text-lg">
                  {trip.name}
                </h2>
                <p className="mt-2 flex items-center gap-2 text-xs text-zinc-500 sm:text-sm">
                  <CalendarDays size={14} className="shrink-0" />
                  {trip.starts_on || trip.ends_on
                    ? `${formatDate(trip.starts_on)} – ${formatDate(trip.ends_on)}`
                    : "Zeitraum nicht angegeben"}
                </p>
              </div>
              <ChevronRight
                size={20}
                className="shrink-0 text-zinc-400 group-hover:text-moss-700"
              />
            </Link>
          ))}
        {!filtered.length && (
          <p className="p-10 text-center text-sm text-zinc-500">
            Keine Reisen gefunden.
          </p>
        )}
      </div>
      {pageCount > 1 && (
        <div className="flex items-center justify-between border-t border-line p-4">
          <Button
            variant="secondary"
            disabled={currentPage === 0}
            onClick={() => setPage(currentPage - 1)}
          >
            Zurück
          </Button>
          <span className="text-xs text-zinc-500">
            {currentPage + 1} / {pageCount}
          </span>
          <Button
            variant="secondary"
            disabled={currentPage + 1 >= pageCount}
            onClick={() => setPage(currentPage + 1)}
          >
            Weiter
          </Button>
        </div>
      )}
    </section>
  );
}
