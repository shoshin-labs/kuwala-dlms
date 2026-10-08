import React, { Suspense, useEffect, useRef, useState } from 'react';
import { Dialog, DialogActions, DialogContent, DialogTitle } from '@material-ui/core';
import { LibraryFolder, LibraryVersion, SerializedMetadata, SerializedMetadataType } from './types';
import DocumentEditor, { DocumentDraft } from './manager_document_editor';
import { ManagerData, ManagedDocument, descendantFolders, docTitle, documentEndpoint, loadFolders, loadManager, memberIds, originalUrl, request } from './manager_api';
import { useManagerStrings } from './manager_strings';
import '../css/curator.css';

const AdvancedTools = React.lazy(() => import(/* webpackChunkName: "advanced-curator" */ './manager_advanced'));
type Modal = { kind: 'library-create' | 'library-rename' | 'library-delete' | 'document-delete' | 'version-create'; library?: LibraryFolder; document?: ManagedDocument };
class AdvancedBoundary extends React.Component<{ message: string; reload: string }, { failed: boolean }> {
  state = { failed: false }; static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <div role="alert"><p>{this.props.message}</p><button className="manager-button" onClick={() => window.location.reload()}>{this.props.reload}</button></div> : this.props.children; }
}
export default function CuratorWorkspace() {
  const s = useManagerStrings();
  const [data, setData] = useState<ManagerData | null>(null);
  const [versionId, setVersionId] = useState(() => Number(new URL(window.location.href).searchParams.get('version')) || 0);
  const [libraryId, setLibraryId] = useState(-1); const [folders, setFolders] = useState<LibraryFolder[]>([]);
  const [loading, setLoading] = useState(true); const [foldersLoading, setFoldersLoading] = useState(true);
  const [loadError, setLoadError] = useState(''); const [folderError, setFolderError] = useState('');
  const [revision, setRevision] = useState(0); const [search, setSearch] = useState(''); const [notice, setNotice] = useState('');
  const [editor, setEditor] = useState<ManagedDocument | null | undefined>(undefined);
  const [modal, setModal] = useState<Modal | null>(null); const [advanced, setAdvanced] = useState(false);
  const [saving, setSaving] = useState(false); const [mutationError, setMutationError] = useState('');
  const [name, setName] = useState(''); const [number, setNumber] = useState(''); const [confirmation, setConfirmation] = useState('');
  const heading = useRef<HTMLHeadingElement>(null); const moveFocus = useRef(false);
  const version = data?.versions.find(item => item.id === versionId) || data?.versions[0];
  const libraries = folders.filter(folder => folder.parent === null);
  const library = libraries.find(item => item.id === libraryId);
  const ready = Boolean(version && !loading && !foldersLoading && !loadError && !folderError);
  useEffect(() => {
    let current = true; setLoading(true); setLoadError('');
    loadManager().then(result => { if (current) { setData(result); setLoading(false); } }).catch(failure => { if (current) { setLoadError(failure instanceof Error ? failure.message : ''); setLoading(false); } });
    return () => { current = false; };
  }, [revision]);
  useEffect(() => {
    if (!version) { setFolders([]); setFoldersLoading(false); return; }
    let current = true; setFoldersLoading(true); setFolderError('');
    loadFolders(version.id).then(result => {
      if (!current) return;
      setFolders(result); setFoldersLoading(false);
      setLibraryId(selected => selected === -1 ? result.find(item => item.parent === null)?.id || 0 : selected && !result.some(item => item.id === selected && item.parent === null) ? 0 : selected);
    }).catch(failure => { if (current) { setFolderError(failure instanceof Error ? failure.message : ''); setFoldersLoading(false); } });
    return () => { current = false; };
  }, [version?.id, revision]);
  useEffect(() => { if (ready && moveFocus.current) { heading.current?.focus(); moveFocus.current = false; } }, [libraryId, ready]);
  function chooseLibrary(id: number) { setLibraryId(id); setSearch(''); moveFocus.current = true; setNotice(''); }
  function openModal(next: Modal) { setModal(next); setName(next.library?.folder_name || ''); setNumber(''); setConfirmation(''); setMutationError(''); }
  function refresh(message = '') { setNotice(message); setRevision(value => value + 1); }
  const countLabel = (count: number) => count === 1 ? s('one_document') : s('document_count', { count });
  async function createType(fieldName: string): Promise<SerializedMetadataType> {
    const existing = data!.types.find(item => item.name === fieldName); if (existing) return existing;
    const result = await request('/api/metadata_types/', 'POST', { name: fieldName });
    setData(current => current && { ...current, types: [...current.types, result] }); return result;
  }
  async function createMetadata(type: number, valueName: string): Promise<SerializedMetadata> {
    const existing = data!.metadata.find(item => item.type === type && item.name === valueName); if (existing) return existing;
    const result = await request('/api/metadata/', 'POST', { type, name: valueName });
    setData(current => current && { ...current, metadata: [...current.metadata, result] }); return result;
  }
  async function saveDocument(draft: DocumentDraft) {
    if (!version) return;
    const payload = { title: draft.title.trim(), display_title: draft.display_title.trim() || draft.title.trim(), description: draft.description,
      copyright_notes: draft.copyright_notes, rights_statement: draft.rights_statement, additional_notes: draft.additional_notes,
      published_date: draft.published_date || null, reviewed_on: draft.reviewed_on || null, active: draft.active, duplicatable: draft.duplicatable,
      metadata: draft.metadata, catalogue_version: version.id, folder_ids: draft.folder_ids };
    let body: any = payload;
    if (draft.file) {
      body = new FormData(); body.append('content_file', draft.file);
      Object.entries(payload).forEach(([key, value]) => body.append(key, Array.isArray(value) ? JSON.stringify(value) : value === null ? '' : String(value)));
    }
    await request(documentEndpoint(editor?.id), editor ? 'PATCH' : 'POST', body);
    const wasNew = !editor; setEditor(undefined); refresh(wasNew ? s('upload_saved') : s('saved'));
  }
  async function applyModal(event: React.FormEvent) {
    event.preventDefault(); if (!modal) return; setSaving(true); setMutationError('');
    try {
      let message = s('saved');
      if (modal.kind === 'version-create') {
        const created: LibraryVersion = await request('/api/library_versions/', 'POST', { library_name: name.trim(), version_number: number.trim(), library_banner: null, created_by: null });
        setVersionId(created.id); setLibraryId(-1); setFolders([]); message = s('saved');
      } else if (modal.kind === 'library-create' && version) {
        const created: LibraryFolder = await request('/api/library_folders/', 'POST', { folder_name: name.trim(), parent: null, version: version.id, logo_img: null, library_content: [] });
        setFolders(current => [...current, created]); setLibraryId(created.id); message = s('library_saved');
      } else if (modal.kind === 'library-rename') {
        await request(`/api/library_folders/${modal.library!.id}/`, 'PATCH', { folder_name: name.trim() }); message = s('library_saved');
      } else if (modal.kind === 'library-delete') {
        await request(`/api/library_folders/${modal.library!.id}/`, 'DELETE'); setLibraryId(0); message = s('library_deleted');
      } else if (modal.kind === 'document-delete') {
        await request(documentEndpoint(modal.document!.id), 'DELETE'); message = s('document_deleted');
      }
      setModal(null); refresh(message);
    } catch (failure) { setMutationError(`${s('operation_error')} ${failure instanceof Error ? failure.message : ''}`); }
    finally { setSaving(false); }
  }
  const membership = library ? memberIds(library, folders) : null;
  const inLibrary = (data?.documents || []).filter(item => !membership || membership.has(item.id));
  const visible = inLibrary.filter(item => [item.title, item.display_title, item.description, item.file_name, ...(item.metadata_info || []).map(value => value.name)].join(' ').toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())).sort((a, b) => docTitle(a).localeCompare(docTitle(b)));
  const destructive = modal?.kind === 'document-delete' || modal?.kind === 'library-delete';
  const modalTitle = modal?.kind === 'library-create' ? s('new_library') : modal?.kind === 'library-rename' ? s('rename_library') : modal?.kind === 'library-delete' ? s('library_delete_title', { name: modal.library!.folder_name }) : modal?.kind === 'document-delete' ? s('delete_document_title') : s('create_version');
  return <section className="manager">
    <p className="manager-intro">{s('intro')}</p><p className="manager-private" role="note">{s('private')}</p>
    <div className="manager-topline">
      {data && data.versions.length > 0 && <label className="manager-version">{s('version')}<select value={version?.id || ''} disabled={loading || saving} onChange={event => { setVersionId(Number(event.target.value)); setLibraryId(-1); setFolders([]); setFoldersLoading(true); setSearch(''); setNotice(''); }}>{data.versions.map(item => <option key={item.id} value={item.id}>{s('version_label', { name: item.library_name, version: item.version_number })}</option>)}</select></label>}
      <button className="manager-text-button" disabled={loading || foldersLoading} onClick={() => refresh()}>{loading || foldersLoading ? s('loading') : s('refresh')}</button>
    </div>
    {notice && <p className="manager-notice" role="status">{notice}</p>}
    {(loadError || folderError) && <div className="manager-error" role="alert"><p>{s('load_error')} {loadError || folderError}</p><button className="manager-button" onClick={() => refresh()}>{s('retry')}</button></div>}
    {!data && loading ? <p className="manager-empty" role="status">{s('loading')}</p> : data && !data.versions.length ? <div className="manager-empty"><h2>{s('empty_catalogue')}</h2><p>{s('empty_catalogue_help')}</p><button className="manager-button manager-button-primary" onClick={() => openModal({ kind: 'version-create' })}>{s('create_version')}</button></div>
      : data && version && <div className="manager-layout">
        <aside className="manager-libraries" aria-labelledby="manager-libraries-title"><div className="manager-section-heading"><h2 id="manager-libraries-title">{s('libraries')}</h2><span>{libraries.length}</span></div>
          <button className="manager-button manager-new-library" disabled={!ready} onClick={() => openModal({ kind: 'library-create' })}>+ {s('new_library')}</button>
          <nav className="manager-library-items" aria-label={s('libraries')}>
            <button className={'manager-library-choice' + (libraryId === 0 ? ' is-selected' : '')} aria-current={libraryId === 0 ? 'page' : undefined} disabled={!ready} onClick={() => chooseLibrary(0)}><strong>{s('all_documents')}</strong><span>{countLabel(data.documents.length)}</span></button>
            {libraries.map(item => <button key={item.id} className={'manager-library-choice' + (libraryId === item.id ? ' is-selected' : '')} aria-current={libraryId === item.id ? 'page' : undefined} disabled={!ready} onClick={() => chooseLibrary(item.id)}><strong>{item.folder_name}</strong><span>{countLabel(data.documents.filter(document => memberIds(item, folders).has(document.id)).length)}</span></button>)}
          </nav>{!libraries.length && !foldersLoading && <p className="manager-help">{s('no_libraries_help')}</p>}
        </aside>
        <div className="manager-documents">
          <div className="manager-document-heading"><div><h2 ref={heading} tabIndex={-1}>{library ? library.folder_name : s('all_documents')}</h2><p className="manager-help" aria-live="polite">{countLabel(inLibrary.length)}</p></div>
            {library && <div className="manager-library-actions"><button className="manager-text-button" disabled={!ready} onClick={() => openModal({ kind: 'library-rename', library })}>{s('rename_library')}</button><button className="manager-text-button manager-danger-text" disabled={!ready} onClick={() => openModal({ kind: 'library-delete', library })}>{s('delete_library')}</button></div>}
          </div>
          <div className="manager-document-toolbar"><label className="manager-search">{s('search')}<input type="search" value={search} disabled={!ready} placeholder={s('search_placeholder')} onChange={event => setSearch(event.target.value)} /></label><button className="manager-button manager-button-primary" disabled={!ready} onClick={() => { setNotice(''); setEditor(null); }}>+ {s('upload')}</button></div>
          {foldersLoading ? <p className="manager-empty" role="status">{s('loading')}</p> : !inLibrary.length ? <div className="manager-empty"><h3>{library ? s('no_documents') : s('no_files')}</h3><p>{library ? s('no_documents_help') : s('no_files_help')}</p></div> : !visible.length ? <div className="manager-empty"><h3>{s('no_results')}</h3><button className="manager-button" onClick={() => setSearch('')}>{s('clear_search')}</button></div>
            : <ul className="manager-document-list">{visible.map(item => {
              const memberLibraries = libraries.filter(root => memberIds(root, folders).has(item.id));
              return <li key={item.id} className="manager-document-card"><div className="manager-document-body"><button className="manager-document-title" disabled={!ready} onClick={() => setEditor(item)}>{docTitle(item) || s('unnamed')}</button><p className="manager-filename">{item.file_name} · {s('stable_id', { id: item.id })}{!item.active && <> · {s('inactive')}</>}</p>{item.description && <p className="manager-document-description">{item.description}</p>}<p className="manager-document-membership">{memberLibraries.map(root => root.folder_name).join(' · ') || s('unassigned')}</p></div><div className="manager-document-actions"><button className="manager-button" disabled={!ready} onClick={() => setEditor(item)}>{s('edit')}</button>{originalUrl(item) && <a className="manager-text-button" href={originalUrl(item)} target="_blank" rel="noopener">{s('original')} ↗</a>}<button className="manager-text-button manager-danger-text" disabled={!ready} aria-label={s('delete_named', { name: docTitle(item) })} onClick={() => openModal({ kind: 'document-delete', document: item })}>{s('delete')}</button></div></li>;
            })}</ul>}
        </div>
      </div>}
    <section className="manager-advanced"><div><h2>{s('advanced')}</h2><p>{s('advanced_help')}</p></div><button className="manager-button" onClick={() => setAdvanced(value => !value)} aria-expanded={advanced}>{advanced ? s('advanced_close') : s('advanced_open')}</button>
      {advanced && <div className="manager-advanced-content"><AdvancedBoundary message={s('advanced_error')} reload={s('reload')}><Suspense fallback={<p role="status">{s('advanced_loading')}</p>}><AdvancedTools /></Suspense></AdvancedBoundary></div>}
    </section>
    {editor !== undefined && data && version && <DocumentEditor key={editor?.id || 'new'} document={editor} folders={folders} initialFolder={library?.id} metadata={data.metadata} types={data.types} onClose={() => setEditor(undefined)} onSave={saveDocument} onCreateType={createType} onCreateMetadata={createMetadata} />}
    {modal && <Dialog open fullWidth maxWidth="sm" onClose={() => { if (!saving) setModal(null); }} aria-labelledby="manager-modal-title" className="manager-dialog"><DialogTitle id="manager-modal-title">{modalTitle}</DialogTitle><DialogContent><form id="manager-action-form" className="manager-form" onSubmit={applyModal}>
      {mutationError && <p role="alert" className="manager-error">{mutationError}</p>}
      {modal.kind === 'document-delete' ? <p>{s('delete_document_help', { name: docTitle(modal.document!), file: modal.document!.file_name || s('original_missing') })}</p> : modal.kind === 'library-delete' ? <><p>{s('library_delete_help', { count: descendantFolders(modal.library!, folders).length - 1 })}</p><label className="manager-field">{s('confirm_library')}<input value={confirmation} disabled={saving} onChange={event => setConfirmation(event.target.value)} /></label></> : <><label className="manager-field">{modal.kind === 'version-create' ? s('version_name') : s('library_name')}<input autoFocus required maxLength={300} value={name} disabled={saving} onChange={event => setName(event.target.value)} /></label>{modal.kind === 'version-create' && <label className="manager-field">{s('version_number')}<input required maxLength={300} pattern={"[A-Za-z0-9][A-Za-z0-9._\\-]*"} title={s('version_help')} value={number} disabled={saving} onChange={event => setNumber(event.target.value)} /><span className="manager-help">{s('version_help')}</span></label>}</>}
    </form></DialogContent><DialogActions><button autoFocus={destructive} className="manager-button" disabled={saving} onClick={() => setModal(null)}>{s('cancel')}</button><button type="submit" form="manager-action-form" className={'manager-button ' + (destructive ? 'manager-button-danger' : 'manager-button-primary')} disabled={saving || modal.kind === 'library-delete' && confirmation !== modal.library!.folder_name || !destructive && (!name.trim() || modal.kind === 'version-create' && !number.trim())}>{saving ? s('saving') : modal.kind === 'document-delete' ? s('delete_document_confirm') : modal.kind === 'library-delete' ? s('delete_library_confirm') : modal.kind === 'library-create' ? s('create_library') : modal.kind === 'version-create' ? s('create_version') : s('save')}</button></DialogActions></Dialog>}
  </section>;
}
