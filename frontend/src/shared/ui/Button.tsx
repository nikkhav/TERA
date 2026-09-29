import type { ButtonHTMLAttributes } from "react";
import { cn } from "../lib/cn";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
};

export function Button({
  children,
  variant = "primary",
  className,
  ...props
}: Props) {
  return (
    <button
      className={cn(
        "focus-ring inline-flex h-10 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold transition",
        variant === "primary" &&
          "bg-ink text-white hover:bg-zinc-700 disabled:bg-zinc-300",
        variant === "secondary" &&
          "border border-line bg-white text-ink hover:bg-zinc-50",
        variant === "ghost" && "text-zinc-600 hover:bg-zinc-100 hover:text-ink",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
