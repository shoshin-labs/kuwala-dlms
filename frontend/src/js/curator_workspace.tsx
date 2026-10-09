import React, { Suspense, useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
} from "@material-ui/core";
import {
  LibraryVersion,
  SerializedMetadata,
  SerializedMetadataType,
} from "./types";
import {
  CatalogueFolder,
  DocumentPage,
  folderAncestors,
  withinFolder,
} from "./catalogue_tree";
import DocumentEditor, { DocumentDraft } from "./manager_document_editor";
import ManagerSearch from "./manager_search";
import DocumentUpdated from "./document_updated";
import {
  ManagerData,
  ManagedDocument,
  descendantFolders,
  docTitle,
  documentEndpoint,
  loadDocumentPage,
  loadEditorReferences,
  loadTree,
  loadManager,
  originalUrl,
  request,
} from "./manager_api";
import { useManagerStrings } from "./manager_strings";
import {
  DocumentIndexStatus,
  IndexingProvider,
  IndexingSummary,
  ReindexAction,
} from "./manager_indexing";
import "../css/curator.css";
import "../css/catalogue.css";

const AdvancedTools = React.lazy(
  () => import(/* webpackChunkName: "advanced-curator" */ "./manager_advanced"),
);
const BulkContentModal = React.lazy(
  () => import(/* webpackChunkName: "bulk-import" */ "./reusable/bulk_content_modal"),
);
type Modal = {
  kind:
    | "library-create"
    | "section-create"
    | "library-rename"
    | "library-delete"
    | "document-delete"
    | "version-create";
  library?: CatalogueFolder;
  document?: ManagedDocument;
};
class AdvancedBoundary extends React.Component<
  { message: string; reload: string; title?: string; cancel?: string; onClose?: () => void },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed && this.props.onClose) {
      return (
        <Dialog open fullWidth maxWidth="sm" className="manager-dialog"
          aria-labelledby="manager-import-error-title" onClose={this.props.onClose}>
          <DialogTitle id="manager-import-error-title">{this.props.title}</DialogTitle>
          <DialogContent><p role="alert">{this.props.message}</p></DialogContent>
          <DialogActions>
            <button autoFocus className="manager-button" onClick={this.props.onClose}>{this.props.cancel}</button>
            <button className="manager-button manager-button-primary" onClick={() => window.location.reload()}>{this.props.reload}</button>
          </DialogActions>
        </Dialog>
      );
    }
    return this.state.failed ? (
      <div role="alert">
        <p>{this.props.message}</p>
        <button
          className="manager-button"
          onClick={() => window.location.reload()}
        >
          {this.props.reload}
        </button>
      </div>
    ) : (
      this.props.children
    );
  }
}
export default function CuratorWorkspace() {
  const s = useManagerStrings();
  const [data, setData] = useState<ManagerData | null>(null);
  const [versionId, setVersionId] = useState(
    () =>
      Number(new URL(window.location.href).searchParams.get("version")) || 0,
  );
  const [libraryId, setLibraryId] = useState(-1);
  const [folders, setFolders] = useState<CatalogueFolder[]>([]);
  const [allDocumentCount, setAllDocumentCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [foldersLoading, setFoldersLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [folderError, setFolderError] = useState("");
  const [revision, setRevision] = useState(0);
  const [search, setSearch] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [documents, setDocuments] =
    useState<DocumentPage<ManagedDocument> | null>(null);
  const [loadedDocumentScope, setLoadedDocumentScope] = useState("");
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState("");
  const [documentAttempt, setDocumentAttempt] = useState(0);
  const [referencesReady, setReferencesReady] = useState(false);
  const [referencesLoading, setReferencesLoading] = useState(false);
  const [referencesError, setReferencesError] = useState("");
  const editorAttempt = useRef(0);
  const [editor, setEditor] = useState<ManagedDocument | null | undefined>(
    undefined,
  );
  const [modal, setModal] = useState<Modal | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [bulkImport, setBulkImport] = useState(false);
  const [saving, setSaving] = useState(false);
  const [mutationError, setMutationError] = useState("");
  const [name, setName] = useState("");
  const [number, setNumber] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [sectionLibraryId, setSectionLibraryId] = useState(0);
  const [sectionParentId, setSectionParentId] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const moveFocus = useRef(false);
  const version =
    data?.versions.find((item) => item.id === versionId) || data?.versions[0];
  const libraries = folders.filter((folder) => folder.parent === null);
  const selectedFolder = folders.find((item) => item.id === libraryId);
  const library = selectedFolder && folderAncestors(selectedFolder, folders)[0];
  const sections = library
    ? folders
        .filter(
          (item) =>
            item.id !== library.id && withinFolder(item, library, folders),
        )
        .sort((a, b) =>
          folderAncestors(a, folders)
            .map((item) => item.folder_name)
            .join(" / ")
            .localeCompare(
              folderAncestors(b, folders)
                .map((item) => item.folder_name)
                .join(" / "),
            ),
        )
    : [];
  const children = selectedFolder
    ? folders.filter((item) => item.parent === selectedFolder.id)
    : [];
  const ready = Boolean(
    version && !loading && !foldersLoading && !loadError && !folderError,
  );
  const documentScope = JSON.stringify([
    version?.id, libraryId, page, query, revision, documentAttempt,
  ]);
  useEffect(() => {
    let current = true;
    setLoading(true);
    setLoadError("");
    loadManager()
      .then((result) => {
        if (current) {
          setData((previous) => ({
            ...result,
            metadata: previous?.metadata || [],
            types: previous?.types || [],
          }));
          setLoading(false);
        }
      })
      .catch((failure) => {
        if (current) {
          setLoadError(failure instanceof Error ? failure.message : "");
          setLoading(false);
        }
      });
    return () => {
      current = false;
    };
  }, [revision]);
  useEffect(() => {
    if (!version) {
      setFolders([]);
      setFoldersLoading(false);
      return;
    }
    let current = true;
    setFoldersLoading(true);
    setFolderError("");
    loadTree(version.id)
      .then((result) => {
        if (!current) return;
        setFolders(result.folders);
        setAllDocumentCount(result.all_document_count || 0);
        setFoldersLoading(false);
        setLibraryId((selected) =>
          selected === -1
            ? result.folders.find((item) => item.parent === null)?.id || 0
            : selected && !result.folders.some((item) => item.id === selected)
              ? 0
              : selected,
        );
      })
      .catch((failure) => {
        if (current) {
          setFolderError(failure instanceof Error ? failure.message : "");
          setFoldersLoading(false);
        }
      });
    return () => {
      current = false;
    };
  }, [version?.id, revision]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(search);
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    let current = true;
    setDocuments(null);
    setDocumentsError("");
    if (!version || libraryId < 0 || foldersLoading || folderError) {
      setDocumentsLoading(false);
      return;
    }
    setDocumentsLoading(true);
    loadDocumentPage(version.id, libraryId, page, query)
      .then((result) => {
        if (current) {
          setDocuments(result);
          setLoadedDocumentScope(documentScope);
          setDocumentsLoading(false);
        }
      })
      .catch((failure) => {
        if (current) {
          setDocumentsError(failure instanceof Error ? failure.message : "");
          setDocumentsLoading(false);
        }
      });
    return () => {
      current = false;
    };
  }, [
    version?.id,
    libraryId,
    page,
    query,
    foldersLoading,
    folderError,
    revision,
    documentAttempt,
    documentScope,
  ]);
  useEffect(() => {
    if (ready && !documentsLoading && moveFocus.current) {
      heading.current?.focus();
      moveFocus.current = false;
    }
  }, [libraryId, page, ready, documentsLoading]);
  function chooseLibrary(id: number) {
    setLibraryId(id);
    setSearch("");
    setQuery("");
    setPage(1);
    moveFocus.current = true;
    setNotice("");
  }
  function openModal(next: Modal) {
    setModal(next);
    setName(
      next.kind === "library-rename" ? next.library?.folder_name || "" : "",
    );
    setNumber("");
    setConfirmation("");
    setMutationError("");
    if (next.kind === "section-create" && next.library) {
      setSectionLibraryId(folderAncestors(next.library, folders)[0].id);
      setSectionParentId(next.library.id);
    }
  }
  function refresh(message = "") {
    setNotice(message);
    setPage(1);
    setReferencesReady(false);
    setRevision((value) => value + 1);
  }
  async function prepareEditor() {
    const attempt = ++editorAttempt.current;
    setReferencesLoading(true);
    setReferencesError("");
    try {
      const references = await loadEditorReferences();
      if (attempt === editorAttempt.current) {
        setData((current) => current && { ...current, ...references });
        setReferencesReady(true);
        setReferencesLoading(false);
      }
    } catch (failure) {
      if (attempt === editorAttempt.current) {
        setReferencesError(failure instanceof Error ? failure.message : "");
        setReferencesLoading(false);
      }
    }
  }
  function openEditor(item: ManagedDocument | null) {
    setEditor(item);
    setNotice("");
    if (!referencesReady) prepareEditor();
  }
  function closeEditor() {
    editorAttempt.current++;
    setEditor(undefined);
    setReferencesLoading(false);
    setReferencesError("");
  }
  const countLabel = (count: number) =>
    count === 1 ? s("one_document") : s("document_count", { count });
  async function createType(
    fieldName: string,
  ): Promise<SerializedMetadataType> {
    const existing = data!.types.find((item) => item.name === fieldName);
    if (existing) return existing;
    const result = await request("/api/metadata_types/", "POST", {
      name: fieldName,
    });
    setData(
      (current) => current && { ...current, types: [...current.types, result] },
    );
    return result;
  }
  async function createMetadata(
    type: number,
    valueName: string,
  ): Promise<SerializedMetadata> {
    const existing = data!.metadata.find(
      (item) => item.type === type && item.name === valueName,
    );
    if (existing) return existing;
    const result = await request("/api/metadata/", "POST", {
      type,
      name: valueName,
    });
    setData(
      (current) =>
        current && { ...current, metadata: [...current.metadata, result] },
    );
    return result;
  }
  async function createSection(parent: number, name: string): Promise<CatalogueFolder> {
    if (!version || !folders.some((folder) => folder.id === parent && folder.version === version.id))
      throw new Error(s("choose_library"));
    const created = await request("/api/library_folders/", "POST", {
      folder_name: name.trim(), parent, version: version.id, logo_img: null, library_content: [],
    });
    const section = { ...created, document_count: 0, direct_document_count: 0 };
    setFolders((current) => [...current, section]);
    return section;
  }
  async function saveDocument(draft: DocumentDraft) {
    if (!version) return;
    const payload = {
      title: draft.title.trim(),
      display_title: draft.display_title.trim() || draft.title.trim(),
      description: draft.description,
      copyright_notes: draft.copyright_notes,
      rights_statement: draft.rights_statement,
      additional_notes: draft.additional_notes,
      published_date: draft.published_date || null,
      reviewed_on: draft.reviewed_on || null,
      active: draft.active,
      duplicatable: draft.duplicatable,
      metadata: draft.metadata,
      catalogue_version: version.id,
      folder_ids: draft.folder_ids,
    };
    let body: any = payload;
    if (draft.file) {
      body = new FormData();
      body.append("content_file", draft.file);
      Object.entries(payload).forEach(([key, value]) =>
        body.append(
          key,
          Array.isArray(value)
            ? JSON.stringify(value)
            : value === null
              ? ""
              : String(value),
        ),
      );
    }
    await request(
      documentEndpoint(editor?.id),
      editor ? "PATCH" : "POST",
      body,
    );
    const wasNew = !editor;
    setEditor(undefined);
    refresh(wasNew ? s("upload_saved") : s("saved"));
  }
  async function applyModal(event: React.FormEvent) {
    event.preventDefault();
    if (!modal) return;
    setSaving(true);
    setMutationError("");
    try {
      let message = s("saved");
      if (modal.kind === "version-create") {
        const created: LibraryVersion = await request(
          "/api/library_versions/",
          "POST",
          {
            library_name: name.trim(),
            version_number: number.trim(),
            library_banner: null,
            created_by: null,
          },
        );
        setVersionId(created.id);
        setLibraryId(-1);
        setFolders([]);
        message = s("saved");
      } else if (
        (modal.kind === "library-create" || modal.kind === "section-create") &&
        version
      ) {
        const created = await request("/api/library_folders/", "POST", {
          folder_name: name.trim(),
          parent: modal.kind === "section-create" ? sectionParentId : null,
          version: version.id,
          logo_img: null,
          library_content: [],
        });
        setFolders((current) => [
          ...current,
          { ...created, document_count: 0, direct_document_count: 0 },
        ]);
        setLibraryId(created.id);
        message = s(
          modal.kind === "section-create" ? "section_saved" : "library_saved",
        );
      } else if (modal.kind === "library-rename") {
        await request(`/api/library_folders/${modal.library!.id}/`, "PATCH", {
          folder_name: name.trim(),
        });
        message = s(
          modal.library!.parent === null ? "library_saved" : "section_saved",
        );
      } else if (modal.kind === "library-delete") {
        await request(`/api/library_folders/${modal.library!.id}/`, "DELETE");
        setLibraryId(modal.library!.parent || 0);
        message = s(
          modal.library!.parent === null
            ? "library_deleted"
            : "section_deleted",
        );
      } else if (modal.kind === "document-delete") {
        await request(documentEndpoint(modal.document!.id), "DELETE");
        message = s("document_deleted");
      }
      setModal(null);
      refresh(message);
    } catch (failure) {
      setMutationError(
        `${s("operation_error")} ${failure instanceof Error ? failure.message : ""}`,
      );
    } finally {
      setSaving(false);
    }
  }
  const visible = documents?.results || [];
  const destructive =
    modal?.kind === "document-delete" || modal?.kind === "library-delete";
  const modalTitle =
    modal?.kind === "library-create"
      ? s("new_library")
      : modal?.kind === "section-create"
        ? s("new_section")
        : modal?.kind === "library-rename"
          ? s(
              modal.library!.parent === null
                ? "rename_library"
                : "rename_section",
            )
          : modal?.kind === "library-delete"
            ? s(
                modal.library!.parent === null
                  ? "library_delete_title"
                  : "section_delete_title",
                { name: modal.library!.folder_name },
              )
            : modal?.kind === "document-delete"
              ? s("delete_document_title")
              : s("create_version");
  return (
    <section className="manager">
      <p className="manager-intro">{s("intro")}</p>
      <p className="manager-private" role="note">
        {s("private")}
      </p>
      <div className="manager-topline">
        {data && data.versions.length > 0 && (
          <label className="manager-version">
            {s("version")}
            <select
              value={version?.id || ""}
              disabled={loading || saving}
              onChange={(event) => {
                setVersionId(Number(event.target.value));
                setLibraryId(-1);
                setFolders([]);
                setFoldersLoading(true);
                setSearch("");
                setQuery("");
                setPage(1);
                setNotice("");
              }}
            >
              {data.versions.map((item) => (
                <option key={item.id} value={item.id}>
                  {s("version_label", {
                    name: item.library_name,
                    version: item.version_number,
                  })}
                </option>
              ))}
            </select>
          </label>
        )}
        <button
          className="manager-text-button"
          disabled={loading || foldersLoading}
          onClick={() => refresh()}
        >
          {loading || foldersLoading ? s("loading") : s("refresh")}
        </button>
      </div>
      {notice && (
        <p className="manager-notice" role="status">
          {notice}
        </p>
      )}
      {(loadError || folderError) && (
        <div className="manager-error" role="alert">
          <p>
            {s("load_error")} {loadError || folderError}
          </p>
          <button className="manager-button" onClick={() => refresh()}>
            {s("retry")}
          </button>
        </div>
      )}
      {!data && loading ? (
        <p className="manager-empty" role="status">
          {s("loading")}
        </p>
      ) : data && !data.versions.length ? (
        <div className="manager-empty">
          <h2>{s("empty_catalogue")}</h2>
          <p>{s("empty_catalogue_help")}</p>
          <button
            className="manager-button manager-button-primary"
            onClick={() => openModal({ kind: "version-create" })}
          >
            {s("create_version")}
          </button>
        </div>
      ) : (
        data &&
        version && (
          <IndexingProvider
            key={version.id}
            versionId={version.id}
            revision={revision}
            enabled={ready && documents !== null && !documentsLoading && loadedDocumentScope === documentScope}
            documentIds={visible.map((item) => item.id)}
            folderId={selectedFolder?.id}
          >
            <IndexingSummary />
            <div className="manager-layout">
              <aside
                className="manager-libraries"
                aria-labelledby="manager-libraries-title"
              >
                <div className="manager-section-heading">
                  <h2 id="manager-libraries-title">{s("libraries")}</h2>
                  <span>{libraries.length}</span>
                </div>
                <button
                  className="manager-button manager-new-library"
                  disabled={!ready}
                  onClick={() => openModal({ kind: "library-create" })}
                >
                  + {s("new_library")}
                </button>
                <nav
                  className="manager-library-items"
                  aria-label={s("libraries")}
                >
                  <button
                    className={
                      "manager-library-choice" +
                      (libraryId === 0 ? " is-selected" : "")
                    }
                    aria-current={libraryId === 0 ? "page" : undefined}
                    disabled={!ready}
                    onClick={() => chooseLibrary(0)}
                  >
                    <strong>{s("all_documents")}</strong>
                    <span>{countLabel(allDocumentCount)}</span>
                  </button>
                  {libraries.map((item) => (
                    <button
                      key={item.id}
                      className={
                        "manager-library-choice" +
                        (library?.id === item.id ? " is-selected" : "")
                      }
                      aria-current={
                        library?.id === item.id ? "page" : undefined
                      }
                      disabled={!ready}
                      onClick={() => chooseLibrary(item.id)}
                    >
                      <strong>{item.folder_name}</strong>
                      <span>{countLabel(item.document_count)}</span>
                    </button>
                  ))}
                </nav>
                {!libraries.length && !foldersLoading && (
                  <p className="manager-help">{s("no_libraries_help")}</p>
                )}
                {library && sections.length > 0 && (
                  <nav
                    className="manager-section-items"
                    aria-label={s("sections_in", { name: library.folder_name })}
                  >
                    <h3>{s("sections")}</h3>
                    <button
                      className={
                        selectedFolder?.id === library.id ? "is-selected" : ""
                      }
                      disabled={!ready}
                      onClick={() => chooseLibrary(library.id)}
                    >
                      <span>{s("all_library_documents")}</span>
                      <span>{library.document_count}</span>
                    </button>
                    {sections.map((item) => (
                      <button
                        key={item.id}
                        className={
                          selectedFolder?.id === item.id ? "is-selected" : ""
                        }
                        disabled={!ready}
                        style={{
                          paddingLeft:
                            12 +
                            Math.max(
                              0,
                              folderAncestors(item, folders).length - 2,
                            ) *
                              12,
                        }}
                        aria-current={
                          selectedFolder?.id === item.id ? "page" : undefined
                        }
                        onClick={() => chooseLibrary(item.id)}
                      >
                        <span>{item.folder_name}</span>
                        <span>{item.document_count}</span>
                      </button>
                    ))}
                  </nav>
                )}
              </aside>
              <div className="manager-documents">
                {selectedFolder && selectedFolder.parent !== null && (
                  <nav
                    className="catalogue-breadcrumbs"
                    aria-label={s("breadcrumb")}
                  >
                    {folderAncestors(selectedFolder, folders).map(
                      (item, index) => (
                        <React.Fragment key={item.id}>
                          {index > 0 && <span aria-hidden="true">/</span>}
                          <button
                            disabled={!ready}
                            onClick={() => chooseLibrary(item.id)}
                          >
                            {item.folder_name}
                          </button>
                        </React.Fragment>
                      ),
                    )}
                  </nav>
                )}
                <div className="manager-document-heading">
                  <div>
                    <h2 ref={heading} tabIndex={-1}>
                      {selectedFolder
                        ? selectedFolder.folder_name
                        : s("all_documents")}
                    </h2>
                    <p className="manager-help" aria-live="polite">
                      {countLabel(
                        documents?.count ??
                          selectedFolder?.document_count ??
                          allDocumentCount,
                      )}
                    </p>
                  </div>
                  {selectedFolder && (
                    <div className="manager-library-actions">
                      <button
                        className="manager-text-button"
                        disabled={!ready}
                        onClick={() =>
                          openModal({
                            kind: "section-create",
                            library: selectedFolder,
                          })
                        }
                      >
                        + {s("new_section")}
                      </button>
                      <ReindexAction
                        disabled={!ready}
                        target={{
                          name: selectedFolder.folder_name,
                          folderId: selectedFolder.id,
                          isSection: selectedFolder.parent !== null,
                        }}
                      />
                      <button
                        className="manager-text-button"
                        disabled={!ready}
                        onClick={() =>
                          openModal({
                            kind: "library-rename",
                            library: selectedFolder,
                          })
                        }
                      >
                        {s(
                          selectedFolder.parent === null
                            ? "rename_library"
                            : "rename_section",
                        )}
                      </button>
                      <button
                        className="manager-text-button manager-danger-text"
                        disabled={!ready}
                        onClick={() =>
                          openModal({
                            kind: "library-delete",
                            library: selectedFolder,
                          })
                        }
                      >
                        {s(
                          selectedFolder.parent === null
                            ? "delete_library"
                            : "delete_section",
                        )}
                      </button>
                    </div>
                  )}
                </div>
                {children.length > 0 && (
                  <section className="catalogue-sections">
                    <h3>{s("sections")}</h3>
                    <div className="catalogue-section-cards">
                      {children.map((child) => (
                        <button
                          key={child.id}
                          disabled={!ready}
                          onClick={() => chooseLibrary(child.id)}
                        >
                          <strong>{child.folder_name}</strong>
                          <span>{countLabel(child.document_count)}</span>
                        </button>
                      ))}
                    </div>
                  </section>
                )}
                <ManagerSearch
                  versionId={version.id}
                  folderId={selectedFolder?.id}
                  revision={revision}
                  metadataQuery={search}
                  onMetadataChange={setSearch}
                  onMetadataSubmit={() => {
                    setQuery(search);
                    setPage(1);
                  }}
                  disabled={!ready}
                >
                  <button
                    className="manager-button manager-button-primary"
                    disabled={!ready}
                    onClick={() => openEditor(null)}
                  >
                    + {s("upload")}
                  </button>
                  <button className="manager-button" disabled={!ready} onClick={() => setBulkImport(true)}>{s("bulk_add_files")}</button>
                </ManagerSearch>
                {foldersLoading || documentsLoading ? (
                  <p className="manager-empty" role="status">
                    {s("loading_documents")}
                  </p>
                ) : documentsError ? (
                  <div className="manager-error" role="alert">
                    <p>
                      {s("documents_error")} {documentsError}
                    </p>
                    <button
                      className="manager-button"
                      onClick={() => setDocumentAttempt((value) => value + 1)}
                    >
                      {s("retry")}
                    </button>
                  </div>
                ) : !visible.length ? (
                  query ? (
                    <div className="manager-empty">
                      <h3>{s("no_results")}</h3>
                      <button
                        className="manager-button"
                        onClick={() => {
                          setSearch("");
                          setQuery("");
                          setPage(1);
                        }}
                      >
                        {s("clear_search")}
                      </button>
                    </div>
                  ) : (
                    <div className="manager-empty">
                      <h3>
                        {selectedFolder
                          ? s(
                              selectedFolder.parent === null
                                ? "no_documents"
                                : "no_documents_section",
                            )
                          : s("no_files")}
                      </h3>
                      <p>
                        {selectedFolder
                          ? s("no_documents_help")
                          : s("no_files_help")}
                      </p>
                    </div>
                  )
                ) : (
                  <>
                    <ul className="manager-document-list">
                      {visible.map((item) => {
                        const memberFolders = (item.catalogue_folder_ids || [])
                          .map((id) =>
                            folders.find((folder) => folder.id === id),
                          )
                          .filter(Boolean) as CatalogueFolder[];
                        return (
                          <li key={item.id} className="manager-document-card">
                            <div className="manager-document-body">
                              <button
                                className="manager-document-title"
                                disabled={!ready}
                                onClick={() => openEditor(item)}
                              >
                                {docTitle(item) || s("unnamed")}
                              </button>
                              <p className="manager-filename">
                                {item.file_name} ·{" "}
                                {s("stable_id", { id: item.id })}
                                {!item.active && <> · {s("inactive")}</>}
                              </p>
                              <DocumentUpdated
                                value={item.modified_on}
                                label={s("last_updated")}
                                description={s("last_updated_help")}
                                className="document-updated manager-document-updated"
                              />
                              {item.description && (
                                <p className="manager-document-description">
                                  {item.description}
                                </p>
                              )}
                              <p className="manager-document-membership">
                                {memberFolders
                                  .map((folder) =>
                                    folderAncestors(folder, folders)
                                      .map((item) => item.folder_name)
                                      .join(" / "),
                                  )
                                  .join(" · ") || s("unassigned")}
                              </p>
                              <DocumentIndexStatus documentId={item.id} />
                            </div>
                            <div className="manager-document-actions">
                              <button
                                className="manager-button"
                                disabled={!ready}
                                onClick={() => openEditor(item)}
                              >
                                {s("edit")}
                              </button>
                              {originalUrl(item) && (
                                <a
                                  className="manager-text-button"
                                  href={originalUrl(item)}
                                  target="_blank"
                                  rel="noopener"
                                >
                                  {s("original")} ↗
                                </a>
                              )}
                              <ReindexAction
                                disabled={!ready}
                                target={{
                                  documentId: item.id,
                                  name: docTitle(item) || s("unnamed"),
                                }}
                              />
                              <button
                                className="manager-text-button manager-danger-text"
                                disabled={!ready}
                                aria-label={s("delete_named", {
                                  name: docTitle(item),
                                })}
                                onClick={() =>
                                  openModal({
                                    kind: "document-delete",
                                    document: item,
                                  })
                                }
                              >
                                {s("delete")}
                              </button>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                    {documents && (
                      <div className="manager-pagination">
                        <p>
                          {s("page_summary", {
                            first:
                              (documents.page - 1) * documents.page_size + 1,
                            last: Math.min(
                              documents.page * documents.page_size,
                              documents.count,
                            ),
                            count: documents.count,
                          })}
                        </p>
                        <div>
                          <button
                            className="manager-button"
                            disabled={!documents.previous || documentsLoading}
                            onClick={() => {
                              setPage(documents.page - 1);
                              moveFocus.current = true;
                            }}
                          >
                            {s("previous_page")}
                          </button>
                          <button
                            className="manager-button"
                            disabled={!documents.next || documentsLoading}
                            onClick={() => {
                              setPage(documents.page + 1);
                              moveFocus.current = true;
                            }}
                          >
                            {s("next_page")}
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          </IndexingProvider>
        )
      )}
      <section className="manager-advanced">
        <div>
          <h2>{s("advanced")}</h2>
          <p>{s("advanced_help")}</p>
        </div>
        <button
          className="manager-button"
          onClick={() => setAdvanced((value) => !value)}
          aria-expanded={advanced}
        >
          {advanced ? s("advanced_close") : s("advanced_open")}
        </button>
        {advanced && (
          <div className="manager-advanced-content">
            <AdvancedBoundary
              message={s("advanced_error")}
              reload={s("reload")}
            >
              <Suspense fallback={<p role="status">{s("advanced_loading")}</p>}>
                <AdvancedTools />
              </Suspense>
            </AdvancedBoundary>
          </div>
        )}
      </section>
      {bulkImport && (
        <AdvancedBoundary message={s("bulk_load_error")} reload={s("reload")}
          title={s("bulk_upload_title")} cancel={s("cancel")} onClose={() => setBulkImport(false)}>
          <Suspense fallback={
            <Dialog open fullWidth maxWidth="sm" className="manager-dialog"
              aria-labelledby="manager-import-loading-title" onClose={() => setBulkImport(false)}>
              <DialogTitle id="manager-import-loading-title">{s("bulk_upload_title")}</DialogTitle>
              <DialogContent><p role="status">{s("bulk_loading")}</p></DialogContent>
              <DialogActions><button autoFocus className="manager-button" onClick={() => setBulkImport(false)}>{s("cancel")}</button></DialogActions>
            </Dialog>
          }>
            <BulkContentModal
              is_open initialVersion={version?.id} initialFolder={selectedFolder?.id}
              on_close={() => {setBulkImport(false); refresh();}}
              show_toast_message={(message, success) => {if (success) setNotice(message);}}
              show_loader={() => {}} remove_loader={() => {}}
            />
          </Suspense>
        </AdvancedBoundary>
      )}
      {editor !== undefined && data && version && referencesReady && (
        <DocumentEditor
          key={editor?.id || "new"}
          document={editor}
          folders={folders}
          initialFolder={selectedFolder?.id}
          metadata={data.metadata}
          types={data.types}
          onClose={closeEditor}
          onSave={saveDocument}
          onCreateType={createType}
          onCreateMetadata={createMetadata}
          onCreateSection={createSection}
        />
      )}
      {editor !== undefined && !referencesReady && (
        <Dialog
          open
          fullWidth
          maxWidth="sm"
          className="manager-dialog"
          onClose={closeEditor}
          aria-labelledby="manager-editor-loading-title"
        >
          <DialogTitle id="manager-editor-loading-title">
            {s("loading_editor")}
          </DialogTitle>
          <DialogContent>
            {referencesError ? (
              <div className="manager-error" role="alert">
                <p>
                  {s("editor_error")} {referencesError}
                </p>
                <button
                  className="manager-button"
                  disabled={referencesLoading}
                  onClick={prepareEditor}
                >
                  {s("retry")}
                </button>
              </div>
            ) : (
              <p role="status">{s("loading_editor_help")}</p>
            )}
          </DialogContent>
          <DialogActions>
            <button autoFocus className="manager-button" onClick={closeEditor}>
              {s("cancel")}
            </button>
          </DialogActions>
        </Dialog>
      )}
      {modal && (
        <Dialog
          open
          fullWidth
          maxWidth="sm"
          onClose={() => {
            if (!saving) setModal(null);
          }}
          aria-labelledby="manager-modal-title"
          className="manager-dialog"
        >
          <DialogTitle id="manager-modal-title">{modalTitle}</DialogTitle>
          <DialogContent>
            <form
              id="manager-action-form"
              className="manager-form"
              onSubmit={applyModal}
            >
              {mutationError && (
                <p role="alert" className="manager-error">
                  {mutationError}
                </p>
              )}
              {modal.kind === "section-create" && (
                <div className="manager-form-grid">
                  <label className="manager-field">{s("placement_library")}
                    <select value={sectionLibraryId} disabled={saving} required
                      onChange={(event) => {const id = Number(event.target.value); setSectionLibraryId(id); setSectionParentId(id);}}>
                      {libraries.map((root) => <option key={root.id} value={root.id}>{root.folder_name}</option>)}
                    </select>
                  </label>
                  <label className="manager-field">{s("section_parent")}
                    <select value={sectionParentId} disabled={saving} required onChange={(event) => setSectionParentId(Number(event.target.value))}>
                      {folders.filter((folder) => {
                        const root = folders.find((item) => item.id === sectionLibraryId);
                        return root && withinFolder(folder, root, folders);
                      }).map((folder) => <option key={folder.id} value={folder.id}>
                        {folderAncestors(folder, folders).map((item) => item.folder_name).join(" / ")}
                      </option>)}
                    </select>
                  </label>
                </div>
              )}
              {modal.kind === "document-delete" ? (
                <p>
                  {s("delete_document_help", {
                    name: docTitle(modal.document!),
                    file: modal.document!.file_name || s("original_missing"),
                  })}
                </p>
              ) : modal.kind === "library-delete" ? (
                <>
                  <p>
                    {s(
                      modal.library!.parent === null
                        ? "library_delete_help"
                        : "section_delete_help",
                      {
                        count:
                          descendantFolders(modal.library!, folders).length - 1,
                      },
                    )}
                  </p>
                  <label className="manager-field">
                    {s(
                      modal.library!.parent === null
                        ? "confirm_library"
                        : "confirm_section",
                    )}
                    <input
                      value={confirmation}
                      disabled={saving}
                      onChange={(event) => setConfirmation(event.target.value)}
                    />
                  </label>
                </>
              ) : (
                <>
                  <label className="manager-field">
                    {modal.kind === "version-create"
                      ? s("version_name")
                      : s(
                          modal.kind === "section-create" ||
                            (modal.library?.parent !== null &&
                              modal.library !== undefined)
                            ? "section_name"
                            : "library_name",
                        )}
                    <input
                      autoFocus
                      required
                      maxLength={modal.kind === "version-create" ? 300 : 200}
                      value={name}
                      disabled={saving}
                      onChange={(event) => setName(event.target.value)}
                    />
                  </label>
                  {modal.kind === "version-create" && (
                    <label className="manager-field">
                      {s("version_number")}
                      <input
                        required
                        maxLength={300}
                        pattern={"[A-Za-z0-9][A-Za-z0-9._\\-]*"}
                        title={s("version_help")}
                        value={number}
                        disabled={saving}
                        onChange={(event) => setNumber(event.target.value)}
                      />
                      <span className="manager-help">{s("version_help")}</span>
                    </label>
                  )}
                </>
              )}
            </form>
          </DialogContent>
          <DialogActions>
            <button
              autoFocus={destructive}
              className="manager-button"
              disabled={saving}
              onClick={() => setModal(null)}
            >
              {s("cancel")}
            </button>
            <button
              type="submit"
              form="manager-action-form"
              className={
                "manager-button " +
                (destructive
                  ? "manager-button-danger"
                  : "manager-button-primary")
              }
              disabled={
                saving ||
                (modal.kind === "library-delete" &&
                  confirmation !== modal.library!.folder_name) ||
                (!destructive &&
                  (!name.trim() ||
                    (modal.kind === "version-create" && !number.trim())))
              }
            >
              {saving
                ? s("saving")
                : modal.kind === "document-delete"
                  ? s("delete_document_confirm")
                  : modal.kind === "library-delete"
                    ? s(
                        modal.library!.parent === null
                          ? "delete_library_confirm"
                          : "delete_section_confirm",
                      )
                    : modal.kind === "section-create"
                      ? s("create_section")
                      : modal.kind === "library-create"
                        ? s("create_library")
                        : modal.kind === "version-create"
                          ? s("create_version")
                          : s("save")}
            </button>
          </DialogActions>
        </Dialog>
      )}
    </section>
  );
}
