/**
 * Utility functions for the casino management app
 */

/**
 * Normalizes a value to a valid table ID
 * @param v - The value to normalize (number, string, or unknown)
 * @returns A valid positive number or null if invalid
 */
export function normalizeTableId(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) && v > 0 ? v : null;

  if (typeof v === "string") {
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? n : null;
  }

  return null;
}

/**
 * Checks if a value is a non-empty string
 * @param v - The value to check
 * @returns True if the value is a non-empty string after trimming
 */
export function isNonEmpty(v: unknown): boolean {
  return String(v ?? "").trim().length > 0;
}

/**
 * Converts a value to an integer with a fallback
 * @param v - The value to convert
 * @param fallback - The fallback value if conversion fails
 * @returns The converted integer or fallback
 */
export function toInt(v: unknown, fallback: number): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

/**
 * Formats a number as money (with commas for thousands)
 * @param amount - The amount to format (can be null or undefined)
 * @returns Formatted money string
 */
export function formatMoney(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return "0";
  return amount.toLocaleString("ru-RU");
}

/**
 * Formats an ISO date string to a localized date/time string
 * @param iso - The ISO date string
 * @returns Formatted date/time string
 */
export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ru-RU");
}

/**
 * Formats an ISO date string to a localized time string
 * @param iso - The ISO date string
 * @returns Formatted time string
 */
export function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Formats an ISO date string to a localized date string
 * @param iso - The ISO date string
 * @returns Formatted date string
 */
export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

/**
 * Gets today's date in local ISO format (YYYY-MM-DD)
 * @returns Today's date in ISO format
 */
export function todayLocalISO(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/**
 * Gets a localized error message from an unknown error
 * @param e - The error to extract message from
 * @returns A user-friendly error message
 */
export function getErrorMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  if (e && typeof e === "object" && "message" in e) {
    const m = e.message;
    return typeof m === "string" ? m : "Ошибка";
  }
  try {
    return JSON.stringify(e);
  } catch {
    return "Ошибка";
  }
}

/**
 * Calculates the hours worked between two timestamps
 * @param startTime - Start time as ISO string
 * @param endTime - End time as ISO string (optional, defaults to now)
 * @returns Hours worked as a decimal number
 */
export function calculateHoursWorked(
  startTime: string,
  endTime?: string | null
): number {
  // Ensure timestamps are treated as UTC by appending 'Z' if not present
  const normalizeTimestamp = (ts: string): string => {
    if (!ts) return ts;
    // If timestamp doesn't end with 'Z' or have timezone info, assume UTC
    if (!ts.endsWith('Z') && !ts.includes('+') && !ts.includes('T')) {
      return ts;
    }
    if (!ts.endsWith('Z') && ts.includes('T') && !ts.includes('+') && !ts.includes('-', 10)) {
      return ts + 'Z';
    }
    return ts;
  };

  const start = new Date(normalizeTimestamp(startTime));
  const end = endTime ? new Date(normalizeTimestamp(endTime)) : new Date();

  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    return 0;
  }

  const milliseconds = end.getTime() - start.getTime();
  return Math.max(0, milliseconds / (1000 * 60 * 60));
}

/**
 * Calculates earnings based on hourly rate and time worked
 * @param hourlyRate - Hourly rate in chips (can be null)
 * @param startTime - Start time as ISO string
 * @param endTime - End time as ISO string (optional, defaults to now)
 * @returns Earnings in chips (rounded to nearest integer)
 */
export function calculateEarnings(
  hourlyRate: number | null | undefined,
  startTime: string,
  endTime?: string | null
): number {
  if (!hourlyRate || hourlyRate <= 0) {
    return 0;
  }

  const hours = calculateHoursWorked(startTime, endTime);
  return Math.round(hours * hourlyRate);
}
