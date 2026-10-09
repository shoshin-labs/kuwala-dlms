import React, { useContext } from "react";
import { LocaleContext } from "./i18n";
import { documentUpdatedDate } from "./document_updated_date";

export default function DocumentUpdated({
  value,
  label,
  description,
  className = "document-updated",
}: {
  value: unknown;
  label: string;
  description: string;
  className?: string;
}) {
  const locale = useContext(LocaleContext);
  const updated = documentUpdatedDate(value, locale);
  if (!updated) return null;
  return (
    <span className={className} title={description}>
      {label}: <time dateTime={updated.dateTime}>{updated.text}</time>
    </span>
  );
}
