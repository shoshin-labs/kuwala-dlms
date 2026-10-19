/** The server declares the URL mount; location/query state never chooses it. */
export function appBase(): string {
  const value = typeof document === "undefined"
    ? null
    : document.querySelector('meta[name="oasis-app-base"]')?.getAttribute("content");
  if (value == null) return "/"; // Older root previews do not supply metadata.
  if (value !== "/" && value !== "/manage/")
    throw new Error("Invalid application base path");
  return value;
}

/** Resolve a local API/resource URL once, retaining query strings and PDF pages. */
export function appUrl(value: string): string {
  if (typeof value !== "string" || value.trim() !== value ||
      /[\\\u0000-\u001f\u007f]/.test(value) || value.startsWith("//"))
    throw new Error("Invalid local application URL");
  const rawPath = value.split(/[?#]/, 1)[0];
  if (/%(?:2f|5c)/i.test(rawPath) ||
      /(?:^|\/)(?:\.|%2e){1,2}(?=\/|$)/i.test(rawPath))
    throw new Error("Invalid local application path");
  const origin = window.location.origin;
  const url = new URL(value, origin + "/");
  if (url.origin !== origin || !["http:", "https:"].includes(url.protocol) ||
      url.username || url.password)
    throw new Error("Application URLs must use the current origin");
  const base = appBase();
  if (base !== "/") {
    if (url.pathname === base.slice(0, -1)) url.pathname = base;
    else if (!url.pathname.startsWith(base))
      url.pathname = base + url.pathname.replace(/^\//, "");
  }
  return url.toString();
}

export function appPath(value: string): string {
  const url = new URL(appUrl(value));
  return url.pathname + url.search + url.hash;
}

export function staticBase(): string {
  return appPath("static/");
}

/** Stored local asset fields must not introduce off-origin requests. */
export function localResourceUrl(value?: string | null): string {
  if (!value) return "";
  try { return appPath(value); } catch { return ""; }
}

export function originalDocumentUrl(item: {
  content_file?: string | null;
  file_name?: string | null;
}): string {
  if (item.content_file) {
    const local = localResourceUrl(item.content_file);
    if (local.startsWith(appPath("media/contents/"))) return local;
  }
  return item.file_name
    ? localResourceUrl("media/contents/" + encodeURIComponent(item.file_name))
    : "";
}
