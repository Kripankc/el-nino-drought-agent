// All dates are handled as UTC calendar days. `Day` = days since 1970-01-01.
export type Day = number;

const MS = 86_400_000;

export function toDay(iso: string): Day {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return Math.round(Date.UTC(y, m - 1, d) / MS);
}

export function fromDay(day: Day): string {
  return new Date(day * MS).toISOString().slice(0, 10);
}

export function ymd(day: Day): { y: number; m: number; d: number } {
  const t = new Date(day * MS);
  return { y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: t.getUTCDate() };
}

export function dayOfYear(day: Day): number {
  const { y } = ymd(day);
  return day - Math.round(Date.UTC(y, 0, 1) / MS) + 1;
}

/** Day for the given day-of-year in year y (DOY 366 in a non-leap year -> Dec 31). */
export function dayFromDoy(y: number, doy: number): Day {
  const jan1 = Math.round(Date.UTC(y, 0, 1) / MS);
  const len = isLeap(y) ? 366 : 365;
  return jan1 + Math.min(doy, len) - 1;
}

export function isLeap(y: number): boolean {
  return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
}

export function daysInMonth(y: number, m: number): number {
  return new Date(Date.UTC(y, m, 0)).getUTCDate();
}

export function todayDay(): Day {
  const n = new Date();
  return Math.round(Date.UTC(n.getUTCFullYear(), n.getUTCMonth(), n.getUTCDate()) / MS);
}

export function toDate(day: Day): Date {
  return new Date(day * MS);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function monthName(m: number): string {
  return MONTHS[m - 1];
}

export function fmtDay(day: Day): string {
  const { y, m, d } = ymd(day);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}
