import { initials } from "../../shared/lib/initials";
import { LogOut, Plus, Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { Employee, User } from "../../shared/types/domain";
import { cn } from "../../shared/lib/cn";

export function EmployeeSidebar({
  employees,
  selectedId,
  mobileOpen,
  user,
  onSelect,
  onCreate,
  onClose,
  onLogout,
}: {
  employees: Employee[];
  selectedId?: string;
  mobileOpen: boolean;
  user: User;
  onSelect: (employee: Employee) => void;
  onCreate: () => void;
  onClose: () => void;
  onLogout: () => void;
}) {
  const [search, setSearch] = useState("");
  const visibleEmployees = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("de");
    return [...employees]
      .sort((left, right) =>
        left.name.localeCompare(right.name, "de", {
          sensitivity: "base",
          numeric: true,
        }),
      )
      .filter((employee) =>
        employee.name.toLocaleLowerCase("de").includes(query),
      );
  }, [employees, search]);

  return (
    <>
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[280px] flex-col border-r border-line bg-white transition-transform lg:sticky lg:top-0 lg:h-screen lg:w-auto lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-16 items-center justify-between px-5">
          <Link
            to="/"
            className="focus-ring flex items-center gap-3 rounded-xl"
          >
            <span className="grid size-9 place-items-center rounded-xl bg-ink text-sm font-extrabold text-white">
              T
            </span>
            <span className="text-sm font-extrabold tracking-[0.16em]">
              TERA
            </span>
          </Link>
          <button
            className="rounded-lg p-2 text-zinc-500 lg:hidden"
            onClick={onClose}
            aria-label="Navigation schließen"
          >
            <X size={18} />
          </button>
        </div>
        <div className="flex items-center justify-between px-5 pb-3 pt-2">
          <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-zinc-400">
            Mitarbeitende
          </p>
          <button
            onClick={onCreate}
            className="focus-ring rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-ink"
            aria-label="Mitarbeitende hinzufügen"
          >
            <Plus size={16} />
          </button>
        </div>
        <div className="px-3 pb-3">
          <label className="relative block">
            <Search
              size={15}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400"
            />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Suchen"
              aria-label="Mitarbeitende suchen"
              className="focus-ring h-9 w-full rounded-xl border border-line bg-zinc-50 pl-9 pr-3 text-sm outline-none placeholder:text-zinc-400"
            />
          </label>
        </div>
        <nav className="flex-1 overflow-y-auto px-3">
          {visibleEmployees.map((employee) => (
            <button
              key={employee.id}
              onClick={() => onSelect(employee)}
              className={cn(
                "focus-ring mb-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold transition",
                employee.id === selectedId
                  ? "bg-moss-50 text-moss-700"
                  : "text-zinc-600 hover:bg-zinc-50 hover:text-ink",
              )}
            >
              <span
                className={cn(
                  "grid size-8 shrink-0 place-items-center rounded-full text-xs font-bold",
                  employee.id === selectedId ? "bg-moss-100" : "bg-zinc-100",
                )}
              >
                {initials(employee.name)}
              </span>
              <span className="truncate">{employee.name}</span>
            </button>
          ))}
          {!visibleEmployees.length && (
            <p className="px-3 py-4 text-xs text-zinc-400">
              {employees.length ? "Keine Treffer" : "Keine Einträge"}
            </p>
          )}
        </nav>
        <div className="m-3">
          <button
            onClick={onLogout}
            className="focus-ring flex w-full items-center gap-3 rounded-xl p-3 text-left hover:bg-zinc-50"
          >
            <span className="grid size-8 place-items-center rounded-full bg-zinc-100 text-xs font-bold">
              {initials(user.display_name)}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-bold">
                {user.display_name}
              </span>
              <span className="block truncate text-[10px] text-zinc-400">
                {user.email}
              </span>
            </span>
            <LogOut size={15} className="text-zinc-400" />
          </button>
        </div>
      </aside>
      {mobileOpen && (
        <button
          className="fixed inset-0 z-30 bg-zinc-950/20 lg:hidden"
          onClick={onClose}
          aria-label="Navigation schließen"
        />
      )}
    </>
  );
}
