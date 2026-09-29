import { initials } from "../../shared/lib/initials";
import { Plus, Search, Users } from "lucide-react";
import { useMemo, useState } from "react";
import type { Employee } from "../../shared/types/domain";
import { Button } from "../../shared/ui/Button";
import { EmptyState } from "../../shared/ui/EmptyState";

export function EmployeeOverview({
  employees,
  onSelect,
  onCreate,
}: {
  employees: Employee[];
  onSelect: (employee: Employee) => void;
  onCreate: () => void;
}) {
  const [search, setSearch] = useState("");
  const visibleEmployees = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("de");
    return [...employees]
      .sort((left, right) =>
        left.name.localeCompare(right.name, "de", { sensitivity: "base" }),
      )
      .filter((employee) =>
        employee.name.toLocaleLowerCase("de").includes(query),
      );
  }, [employees, search]);

  return (
    <section>
      <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
            Mitarbeitende
          </h1>
          <p className="mt-1 text-sm text-zinc-500">{employees.length}</p>
        </div>
        <Button onClick={onCreate}>
          <Plus size={16} />
          Hinzufügen
        </Button>
      </div>
      {employees.length > 8 && (
        <label className="relative mb-5 block max-w-md">
          <Search
            size={16}
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-400"
          />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Suchen"
            aria-label="Mitarbeitende suchen"
            className="field pl-10"
          />
        </label>
      )}
      {visibleEmployees.length ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {visibleEmployees.map((employee) => (
            <button
              key={employee.id}
              onClick={() => onSelect(employee)}
              className="focus-ring flex items-center gap-3 rounded-2xl border border-line bg-white p-4 text-left shadow-soft transition hover:border-zinc-300"
            >
              <span className="grid size-10 shrink-0 place-items-center rounded-full bg-moss-50 text-xs font-bold text-moss-700">
                {initials(employee.name)}
              </span>
              <span className="min-w-0 truncate text-sm font-bold">
                {employee.name}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <div className="card">
          <EmptyState
            icon={Users}
            title={employees.length ? "Keine Treffer" : "Keine Mitarbeitenden"}
            action={
              employees.length ? undefined : (
                <Button onClick={onCreate}>
                  <Plus size={16} />
                  Hinzufügen
                </Button>
              )
            }
          />
        </div>
      )}
    </section>
  );
}
