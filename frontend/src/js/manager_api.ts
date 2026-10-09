import {
  LibraryVersion,
  SerializedMetadata,
  SerializedMetadataType,
} from "./types";
import {
  CataloguedDocument,
  CatalogueFolder,
  CatalogueTree,
  DocumentPage,
  catalogueQuery,
  folderAncestors,
} from "./catalogue_tree";
import english from "./locales/manager.en.json";

export interface ManagedDocument extends CataloguedDocument {
  published_date?: string | null;
}
export interface ManagerData {
  versions: LibraryVersion[];
  metadata: SerializedMetadata[];
  types: SerializedMetadataType[];
}
const DOCUMENTS = "/api/oasis/documents/";
let token: Promise<string> | undefined;
export function message(value: any): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(message).filter(Boolean).join(" ");
  if (value && typeof value === "object")
    return Object.keys(value)
      .map((key) => `${key}: ${message(value[key])}`)
      .join(" · ");
  return "";
}
export async function request(
  url: string,
  method = "GET",
  body?: any,
): Promise<any> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    if (!token)
      token = request("/api/get_csrf/").catch((error) => {
        token = undefined;
        throw error;
      });
    headers["X-CSRFToken"] = await token;
  }
  if (body && !(body instanceof FormData))
    headers["Content-Type"] = "application/json";
  const response = await fetch(url, {
    method,
    credentials: "same-origin",
    headers,
    body:
      body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  });
  // A rejected write can follow a rotated or expired CSRF cookie. Let the
  // curator's next retry fetch a fresh token without repeating the mutation.
  if (response.status === 403 && method !== "GET") token = undefined;
  const text = await response.text();
  let result: any;
  try {
    result = text ? JSON.parse(text) : null;
  } catch {
    throw new Error(`HTTP ${response.status}`);
  }
  if (!response.ok || result?.success === false)
    throw new Error(
      message(result?.error || result) || `HTTP ${response.status}`,
    );
  return result && Object.prototype.hasOwnProperty.call(result, "success")
    ? result.data
    : result;
}
export async function allPages<T>(path: string): Promise<T[]> {
  const records: T[] = [];
  let page = 1;
  while (true) {
    const url = new URL(path, window.location.origin);
    url.searchParams.set("page", String(page++));
    url.searchParams.set("size", "100");
    const data = await request(url.toString());
    if (Array.isArray(data)) return data;
    if (!Array.isArray(data?.results) || !Number.isFinite(data.count))
      throw new Error(english.strings.invalid_response);
    records.push(...data.results);
    if (records.length >= data.count) return records;
    if (!data.results.length)
      throw new Error(english.strings.incomplete_response);
  }
}
export async function loadManager(): Promise<ManagerData> {
  const tree: CatalogueTree = await loadTree();
  return { versions: tree.versions, metadata: [], types: [] };
}
export function loadTree(version?: number): Promise<CatalogueTree> {
  return request(
    catalogueQuery("/api/oasis/catalogue/", {
      mode: "curator",
      catalogue_version: version,
    }),
  );
}
export function loadDocumentPage(
  version: number,
  folder: number,
  page: number,
  query: string,
): Promise<DocumentPage<ManagedDocument>> {
  return request(
    catalogueQuery(DOCUMENTS, {
      catalogue_version: version,
      folder_id: folder || undefined,
      global: folder ? undefined : 1,
      q: query,
      page,
      size: 24,
    }),
  );
}
export async function loadEditorReferences() {
  const [metadata, types] = await Promise.all([
    allPages<SerializedMetadata>("/api/metadata/"),
    allPages<SerializedMetadataType>("/api/metadata_types/"),
  ]);
  return { metadata, types };
}
export function docTitle(document: ManagedDocument) {
  return document.display_title || document.title || document.file_name;
}
export function originalUrl(document: ManagedDocument) {
  return document.file_name
    ? "/media/contents/" + encodeURIComponent(document.file_name)
    : "";
}
export function folderPath(
  folder: CatalogueFolder,
  folders: CatalogueFolder[],
): string {
  return folderAncestors(folder, folders)
    .map((item) => item.folder_name)
    .join(" / ");
}
export function descendantFolders(
  root: CatalogueFolder,
  folders: CatalogueFolder[],
) {
  return folders.filter((folder) =>
    folderAncestors(folder, folders).some((item) => item.id === root.id),
  );
}
export const documentEndpoint = (id?: number) =>
  id ? `${DOCUMENTS}${id}/` : DOCUMENTS;
