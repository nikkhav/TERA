import { BriefcaseBusiness, Check, Plus } from "lucide-react";
import { formatDate } from "../../shared/lib/format";
import { cn } from "../../shared/lib/cn";
import type { Trip } from "../../shared/types/domain";

export function TripSelector({
  trips,
  selectedId,
  onSelect,
  onCreate,
}: {
  trips: Trip[];
  selectedId?: string;
  onSelect: (trip: Trip) => void;
  onCreate: () => void;
}) {
  if (trips.length > 8) {
    return (
      <div className="mb-7 max-w-xl">
        <select
          className="field"
          value={selectedId ?? ""}
          aria-label="Reise auswählen"
          onChange={(event) => {
            const trip = trips.find((item) => item.id === event.target.value);
            if (trip) onSelect(trip);
          }}
        >
          <option value="">Reise auswählen</option>
          {trips.map((trip) => (
            <option key={trip.id} value={trip.id}>
              {trip.name}
              {trip.starts_on ? ` · ${formatDate(trip.starts_on)}` : ""}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div className="mb-7 flex gap-3 overflow-x-auto pb-2">
      {trips.map((trip) => (
        <button
          key={trip.id}
          onClick={() => onSelect(trip)}
          className={cn(
            "focus-ring min-w-52 rounded-2xl border p-4 text-left transition",
            trip.id === selectedId
              ? "border-moss-500 bg-moss-50"
              : "border-line bg-white hover:border-zinc-300",
          )}
        >
          <div className="flex items-center justify-between">
            <span
              className={cn(
                "grid size-8 place-items-center rounded-xl",
                trip.id === selectedId
                  ? "bg-moss-100 text-moss-700"
                  : "bg-zinc-100 text-zinc-500",
              )}
            >
              <BriefcaseBusiness size={16} />
            </span>
            {trip.id === selectedId && (
              <Check size={15} className="text-moss-600" />
            )}
          </div>
          <p className="mt-3 truncate text-sm font-bold">{trip.name}</p>
          <p className="mt-1 text-xs text-zinc-500">
            {trip.starts_on ? formatDate(trip.starts_on) : "Kein Datum"}
          </p>
        </button>
      ))}
      {!trips.length && (
        <button
          onClick={onCreate}
          className="focus-ring min-w-64 rounded-2xl border border-dashed border-zinc-300 bg-white p-5 text-left hover:border-moss-500"
        >
          <Plus size={18} className="text-moss-600" />
          <p className="mt-3 text-sm font-bold">Erste Reise anlegen</p>
        </button>
      )}
    </div>
  );
}
