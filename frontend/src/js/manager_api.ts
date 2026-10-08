import { LibraryFolder, LibraryVersion, SerializedContent, SerializedMetadata, SerializedMetadataType } from './types';
import english from './locales/manager.en.json';

export interface ManagedDocument extends SerializedContent { published_date?: string | null; }
export interface ManagerData { versions: LibraryVersion[]; documents: ManagedDocument[]; metadata: SerializedMetadata[]; types: SerializedMetadataType[]; }
const DOCUMENTS = '/api/oasis/documents/';
let token: Promise<string> | undefined;
function message(value: any): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(message).filter(Boolean).join(' ');
  if (value && typeof value === 'object') return Object.keys(value).map(key => `${key}: ${message(value[key])}`).join(' · ');
  return '';
}
export async function request(url: string, method = 'GET', body?: any): Promise<any> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (method !== 'GET') {
    if (!token) token = request('/api/get_csrf/').catch(error => { token = undefined; throw error; });
    headers['X-CSRFToken'] = await token;
  }
  if (body && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const response = await fetch(url, { method, credentials: 'same-origin', headers, body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined });
  const text = await response.text();
  let result: any;
  try { result = text ? JSON.parse(text) : null; } catch { throw new Error(`HTTP ${response.status}`); }
  if (!response.ok || result?.success === false) throw new Error(message(result?.error || result) || `HTTP ${response.status}`);
  return result && Object.prototype.hasOwnProperty.call(result, 'success') ? result.data : result;
}
export async function allPages<T>(path: string): Promise<T[]> {
  const records: T[] = []; let page = 1;
  while (true) {
    const url = new URL(path, window.location.origin);
    url.searchParams.set('page', String(page++)); url.searchParams.set('size', '100');
    const data = await request(url.toString());
    if (Array.isArray(data)) return data;
    if (!Array.isArray(data?.results) || !Number.isFinite(data.count)) throw new Error(english.strings.invalid_response);
    records.push(...data.results);
    if (records.length >= data.count) return records;
    if (!data.results.length) throw new Error(english.strings.incomplete_response);
  }
}
export async function loadManager(): Promise<ManagerData> {
  const [versions, documents, metadata, types] = await Promise.all([
    allPages<LibraryVersion>('/api/library_versions/'), allPages<ManagedDocument>(DOCUMENTS),
    allPages<SerializedMetadata>('/api/metadata/'), allPages<SerializedMetadataType>('/api/metadata_types/')
  ]);
  return { versions, documents, metadata, types };
}
export function loadFolders(version: number): Promise<LibraryFolder[]> { return request(`/api/library_versions/${version}/folders/`); }
export function docTitle(document: ManagedDocument) { return document.display_title || document.title || document.file_name; }
export function originalUrl(document: ManagedDocument) { return document.file_name ? '/media/contents/' + encodeURIComponent(document.file_name) : ''; }
export function folderPath(folder: LibraryFolder, folders: LibraryFolder[]): string {
  const seen = new Set<number>(); const parts: string[] = []; let current: LibraryFolder | undefined = folder;
  while (current && !seen.has(current.id)) { seen.add(current.id); parts.unshift(current.folder_name); current = folders.find(item => item.id === current!.parent); }
  return parts.join(' / ');
}
export function descendantFolders(root: LibraryFolder, folders: LibraryFolder[]) {
  const ids = new Set([root.id]); let last = 0;
  while (last !== ids.size) { last = ids.size; folders.forEach(folder => { if (folder.parent !== null && ids.has(folder.parent)) ids.add(folder.id); }); }
  return folders.filter(folder => ids.has(folder.id));
}
export function memberIds(root: LibraryFolder, folders: LibraryFolder[]) { return new Set(descendantFolders(root, folders).flatMap(folder => folder.library_content)); }
export const documentEndpoint = (id?: number) => id ? `${DOCUMENTS}${id}/` : DOCUMENTS;
