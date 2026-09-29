import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function EmptyState({
  icon: Icon,
  title,
  text,
  action,
  iconClassName,
}: {
  icon: LucideIcon;
  title: string;
  text?: string;
  action?: ReactNode;
  iconClassName?: string;
}) {
  return (
    <div className="flex min-h-72 flex-col items-center justify-center px-6 text-center">
      <span className="mb-4 grid size-12 place-items-center rounded-2xl bg-moss-50 text-moss-700">
        <Icon size={23} className={iconClassName} />
      </span>
      <h2 className="text-lg font-bold">{title}</h2>
      {text && <p className="mt-2 max-w-sm text-sm text-zinc-500">{text}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
