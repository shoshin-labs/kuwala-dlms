// Authoring timestamps are UTC ISO 8601 values. Reject invalid calendar
// dates rather than letting Date silently normalise them into another day.
export function documentUpdatedDate(value: unknown, locale: string) {
  if (
    typeof value !== "string" ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(value)
  ) return null;
  const date = new Date(value);
  if (
    !Number.isFinite(date.getTime()) ||
    date.getUTCFullYear() < 1 ||
    date.toISOString().slice(0, 19) !== value.slice(0, 19)
  ) return null;
  return {
    dateTime: value,
    text: new Intl.DateTimeFormat(locale, {
      year: "numeric", month: "long", day: "numeric", timeZone: "UTC",
    }).format(date),
  };
}
