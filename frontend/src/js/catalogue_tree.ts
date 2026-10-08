import { LibraryVersion, SerializedContent } from "./types";

export interface CatalogueFolder {
  id: number;
  folder_name: string;
  parent: number | null;
  version: number;
  document_count: number;
  direct_document_count: number;
}
export interface CatalogueTree {
  versions: LibraryVersion[];
  catalogue_version: number | null;
  folders: CatalogueFolder[];
  document_count: number;
  all_document_count?: number;
}
export interface CataloguedDocument extends SerializedContent {
  catalogue_folder_ids?: number[];
}
export interface DocumentPage<T> {
  results: T[];
  count: number;
  next: string | null;
  previous: string | null;
  page: number;
  page_size: number;
}
export function folderAncestors(
  folder: CatalogueFolder,
  folders: CatalogueFolder[],
) {
  const result: CatalogueFolder[] = [];
  const seen = new Set<number>();
  let current: CatalogueFolder | undefined = folder;
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    result.unshift(current);
    current = folders.find((item) => item.id === current!.parent);
  }
  return result;
}
export function withinFolder(
  folder: CatalogueFolder,
  root: CatalogueFolder,
  folders: CatalogueFolder[],
) {
  return folderAncestors(folder, folders).some((item) => item.id === root.id);
}
export function catalogueQuery(
  path: string,
  values: Record<string, string | number | undefined>,
) {
  const url = new URL(path, window.location.origin);
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "")
      url.searchParams.set(key, String(value));
  });
  return url.toString();
}
