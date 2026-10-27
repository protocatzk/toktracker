export function formatEUR(value: number | string | undefined | null): string {
  const num = typeof value === "number" ? value : parseFloat(String(value || 0)) || 0;
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
  }).format(num);
}

export function formatUSD(value: number | string | undefined | null): string {
  const num = typeof value === "number" ? value : parseFloat(String(value || 0)) || 0;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(num);
}

export function formatNumber(value: number | string | undefined | null): string {
  const num = typeof value === "number" ? value : parseFloat(String(value || 0)) || 0;
  return new Intl.NumberFormat("de-DE").format(Math.round(num));
}

export function formatDateTime(isoString: string | undefined | null): string {
  if (!isoString) return "-";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return String(isoString).replace("T", " ");
    return d.toLocaleString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return String(isoString).replace("T", " ");
  }
}
