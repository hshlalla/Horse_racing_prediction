export function parseRaceTime(dt: string | null | undefined): Date | null {
  if (!dt) return null;
  const d = new Date(dt);
  return isNaN(d.getTime()) ? null : d;
}
