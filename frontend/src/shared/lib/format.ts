export function formatDate(value: string | null | undefined) {
  if (!value) return "–";
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(`${value}T00:00:00`));
}

export function formatMoney(value: string | null, currency: string | null) {
  if (value === null) return "–";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return value;
  try {
    return new Intl.NumberFormat("de-DE", {
      style: "currency",
      currency: currency ?? "EUR",
    }).format(amount);
  } catch {
    return `${new Intl.NumberFormat("de-DE").format(amount)} ${currency ?? ""}`.trim();
  }
}
