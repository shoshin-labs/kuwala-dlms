import React, { useEffect, useRef, useState } from "react";
import { APP_URLS, get_data } from "./urls";
import { LibraryFolder, LibraryVersion, SerializedContent } from "./types";
import { useStrings } from "./i18n";

interface CatalogueLocation {
  version: string;
  library: string;
  document: string;
}
function readLocation(): CatalogueLocation {
  const params = new URL(window.location.href).searchParams;
  return {
    version: params.get("version") || "",
    library: params.get("library") || "",
    document: params.get("document") || "",
  };
}
function documentTitle(document: SerializedContent) {
  return document.display_title || document.title || document.file_name;
}
function descendants(
  root: LibraryFolder,
  folders: LibraryFolder[],
): LibraryFolder[] {
  const included = new Set<number>([root.id]);
  let previousSize = 0;
  while (previousSize !== included.size) {
    previousSize = included.size;
    folders.forEach((folder) => {
      if (folder.parent !== null && included.has(folder.parent))
        included.add(folder.id);
    });
  }
  return folders.filter((folder) => included.has(folder.id));
}
function documentIds(root: LibraryFolder, folders: LibraryFolder[]) {
  return new Set(
    descendants(root, folders).reduce(
      (ids: number[], folder) => ids.concat(folder.library_content),
      [],
    ),
  );
}
function originalURL(document: SerializedContent) {
  if (document.content_file) {
    const url = new URL(document.content_file, window.location.origin);
    if (url.pathname.startsWith("/media/contents/")) return url.pathname;
  }
  return document.file_name
    ? "/media/contents/" + encodeURIComponent(document.file_name)
    : "";
}

export default function LibraryCatalogue() {
  const s = useStrings();
  const [location, setLocation] = useState(readLocation);
  const [versions, setVersions] = useState<LibraryVersion[]>([]);
  const [folders, setFolders] = useState<LibraryFolder[]>([]);
  const [documents, setDocuments] = useState<SerializedContent[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(true);
  const [foldersLoading, setFoldersLoading] = useState(false);
  const [versionsError, setVersionsError] = useState(false);
  const [foldersError, setFoldersError] = useState(false);
  const loading = versionsLoading || foldersLoading;
  const error = versionsError || foldersError;
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [documentAttempt, setDocumentAttempt] = useState(0);
  const [search, setSearch] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const navigated = useRef(false);
  const version =
    versions.find((item) => String(item.id) === location.version) ||
    (!location.version ? versions[0] : undefined);
  const libraries = folders.filter((folder) => folder.parent === null);
  const library = libraries.find(
    (folder) => String(folder.id) === location.library,
  );
  const selectedDocument = documents.find(
    (item) => String(item.id) === location.document,
  );
  function navigate(update: Partial<CatalogueLocation>) {
    const next = { ...location, ...update };
    const url = new URL(window.location.href);
    Object.entries(next).forEach(([key, value]) =>
      value ? url.searchParams.set(key, value) : url.searchParams.delete(key),
    );
    url.searchParams.set("tab", "contents");
    history.pushState({}, "", url.toString());
    navigated.current = true;
    setLocation(next);
    setSearch("");
  }
  useEffect(() => {
    const onPop = () => {
      navigated.current = true;
      setLocation(readLocation());
      setSearch("");
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  useEffect(() => {
    let current = true;
    setVersionsLoading(true);
    setVersionsError(false);
    (async () => {
      const all: LibraryVersion[] = [];
      let page = 1;
      let count = 0;
      do {
        const data = await get_data(APP_URLS.LIBRARY_VERSIONS(page++, 100));
        all.push(...data.results);
        count = data.count;
      } while (all.length < count);
      if (current) {
        setVersions(all);
        setVersionsLoading(false);
      }
    })().catch(() => {
      if (current) {
        setVersionsError(true);
        setVersionsLoading(false);
      }
    });
    return () => {
      current = false;
    };
  }, [attempt]);
  useEffect(() => {
    if (!version) {
      setFolders([]);
      setFoldersLoading(false);
      setFoldersError(false);
      return;
    }
    let current = true;
    setFoldersLoading(true);
    setFoldersError(false);
    setFolders([]);
    get_data(APP_URLS.LIBRARY_VERSION_FOLDERS(version.id))
      .then((data) => {
        if (current) {
          setFolders(data);
          setFoldersLoading(false);
        }
      })
      .catch(() => {
        if (current) {
          setFoldersError(true);
          setFoldersLoading(false);
        }
      });
    return () => {
      current = false;
    };
  }, [version && version.id, attempt]);
  useEffect(() => {
    setDocuments([]);
    setDocumentsError(false);
    if (!library) {
      setDocumentsLoading(false);
      return;
    }
    let current = true;
    setDocumentsLoading(true);
    Promise.all(
      descendants(library, folders).map((folder) =>
        get_data(APP_URLS.LIBRARY_FOLDER_CONTENTS(folder.id)),
      ),
    )
      .then((results) => {
        const unique = new Map<number, SerializedContent>();
        results.forEach((result) =>
          result.files.forEach((item: SerializedContent) =>
            unique.set(item.id, item),
          ),
        );
        if (current) {
          setDocuments(
            Array.from(unique.values()).sort((a, b) =>
              documentTitle(a).localeCompare(documentTitle(b)),
            ),
          );
          setDocumentsLoading(false);
        }
      })
      .catch(() => {
        if (current) {
          setDocumentsError(true);
          setDocumentsLoading(false);
        }
      });
    return () => {
      current = false;
    };
  }, [library, folders, documentAttempt]);
  useEffect(() => {
    if (!loading && !documentsLoading && navigated.current) {
      heading.current?.focus();
      navigated.current = false;
    }
  }, [location, loading, documentsLoading]);
  const countLabel = (count: number) =>
    count === 1 ? s("one_document") : s("document_count", { count });
  const filtered = documents.filter((item) =>
    [
      item.title,
      item.display_title,
      item.description,
      item.file_name,
      ...(item.metadata_info || []).map((metadata) => metadata.name),
    ]
      .join(" ")
      .toLocaleLowerCase()
      .includes(search.toLocaleLowerCase().trim()),
  );
  return (
    <section className="catalogue">
      <div className="workspace-head">
        {location.document && library ? (
          <button
            className="text-button"
            onClick={() => navigate({ document: "" })}
          >
            ← {s("back_documents")}
          </button>
        ) : location.library ? (
          <button
            className="text-button"
            onClick={() => navigate({ library: "", document: "" })}
          >
            ← {s("back_libraries")}
          </button>
        ) : null}
        <h1 ref={heading} tabIndex={-1}>
          {selectedDocument
            ? documentTitle(selectedDocument)
            : library
              ? library.folder_name
              : s("choose_library")}
        </h1>
        {!location.library && (
          <p className="intro-text">{s("catalogue_intro")}</p>
        )}
      </div>
      {versions.length > 1 && (
        <div className="version-picker">
          <label htmlFor="catalogue-version">{s("collection")}</label>
          <select
            id="catalogue-version"
            value={version?.id || ""}
            onChange={(event) =>
              navigate({
                version: event.target.value,
                library: "",
                document: "",
              })
            }
          >
            {!version && <option value="">{s("not_available")}</option>}
            {versions.map((item) => (
              <option key={item.id} value={item.id}>
                {s("version_label", {
                  name: item.library_name,
                  version: item.version_number,
                })}
              </option>
            ))}
          </select>
        </div>
      )}
      {loading ? (
        <p role="status" className="empty-state">
          {s("loading")}
        </p>
      ) : error ? (
        <div role="alert" className="empty-state">
          <p>{s("load_error")}</p>
          <button
            className="quiet-button"
            onClick={() => setAttempt(attempt + 1)}
          >
            {s("retry")}
          </button>
        </div>
      ) : !versions.length ? (
        <div className="empty-state">
          <h2>{s("no_versions")}</h2>
          <p>{s("no_versions_help")}</p>
        </div>
      ) : !version ? (
        <p role="alert">{s("missing_library")}</p>
      ) : location.library && !library ? (
        <p role="alert">{s("missing_library")}</p>
      ) : !library ? (
        <>
          <h2 className="section-label">{s("libraries")}</h2>
          {libraries.length ? (
            <div className="library-list">
              {libraries.map((item) => (
                <button
                  className="library-choice"
                  key={item.id}
                  onClick={() =>
                    navigate({
                      version: String(version.id),
                      library: String(item.id),
                      document: "",
                    })
                  }
                  aria-label={s("browse_library", { name: item.folder_name })}
                >
                  <span className="library-choice-name">
                    {item.folder_name}
                  </span>
                  <span className="library-choice-count">
                    {countLabel(documentIds(item, folders).size)}
                  </span>
                  <span className="library-choice-arrow" aria-hidden="true">
                    →
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <h2>{s("no_libraries")}</h2>
              <p>{s("no_libraries_help")}</p>
            </div>
          )}
        </>
      ) : documentsLoading ? (
        <p role="status" className="empty-state">
          {s("loading_documents")}
        </p>
      ) : documentsError ? (
        <div role="alert" className="empty-state">
          <p>{s("documents_error")}</p>
          <button
            className="quiet-button"
            onClick={() => setDocumentAttempt(documentAttempt + 1)}
          >
            {s("retry")}
          </button>
        </div>
      ) : location.document ? (
        selectedDocument ? (
          <DocumentDetail
            document={selectedDocument}
            libraries={libraries.filter((item) =>
              documentIds(item, folders).has(selectedDocument.id),
            )}
          />
        ) : (
          <p role="alert">{s("missing_document")}</p>
        )
      ) : (
        <>
          <div className="document-toolbar">
            <h2 className="section-label">
              {s("documents")} <span className="count">{documents.length}</span>
            </h2>
            <div className="search-field">
              <label htmlFor="library-search">{s("search")}</label>
              <input
                id="library-search"
                type="search"
                value={search}
                placeholder={s("search_placeholder")}
                onChange={(event) => setSearch(event.target.value)}
                aria-describedby="search-help"
              />
              <p id="search-help">{s("search_help")}</p>
            </div>
          </div>
          {!documents.length ? (
            <p className="empty-state">{s("no_documents")}</p>
          ) : !filtered.length ? (
            <div className="empty-state">
              <p>{s("no_results")}</p>
              <button className="quiet-button" onClick={() => setSearch("")}>
                {s("clear_search")}
              </button>
            </div>
          ) : (
            <ul className="document-list">
              {filtered.map((item) => (
                <li key={item.id}>
                  <button
                    className="document-choice"
                    onClick={() => navigate({ document: String(item.id) })}
                  >
                    <span className="document-format">
                      {item.file_name?.toLowerCase().endsWith(".pdf")
                        ? s("pdf")
                        : s("file")}
                    </span>
                    <span className="document-summary">
                      <span className="document-name">
                        {documentTitle(item)}
                      </span>
                      <span className="document-description">
                        {item.description ||
                          (item.metadata_info || [])
                            .filter((meta) =>
                              /creator|author|source/i.test(meta.type_name),
                            )
                            .map((meta) => meta.name)
                            .join(" · ") ||
                          s("not_available")}
                      </span>
                    </span>
                    <span className="document-arrow" aria-hidden="true">
                      →
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

function DocumentDetail({
  document,
  libraries,
}: {
  document: SerializedContent;
  libraries: LibraryFolder[];
}) {
  const s = useStrings();
  const [page, setPage] = useState("1");
  const original = originalURL(document);
  const isPDF = document.file_name?.toLowerCase().endsWith(".pdf");
  const pageValid =
    /^\d+$/.test(page) &&
    Number(page) > 0 &&
    Number.isSafeInteger(Number(page));
  function renderValue(value: string | null | undefined) {
    if (!value) return s("not_available");
    return value.split(/(https?:\/\/[^\s<>\"]+)/gi).map((part, index) =>
      /^https?:\/\//i.test(part) ? (
        <a
          key={index}
          href={part}
          title={s("external_link")}
          target="_blank"
          rel="noopener"
        >
          {part} ↗
        </a>
      ) : (
        part
      ),
    );
  }
  const fields = [
    [s("description"), document.description],
    [s("filename"), document.file_name],
    [s("year"), document.published_year],
    [s("rights"), document.rights_statement],
    [s("copyright"), document.copyright_notes],
    [s("review_date"), document.reviewed_on],
    [s("notes"), document.additional_notes],
  ];
  return (
    <article className="document-detail">
      <div className="document-actions">
        {original ? (
          <a
            className="primary-button"
            href={original}
            target="_blank"
            rel="noopener"
          >
            {s("original")} ↗
          </a>
        ) : (
          <p>{s("original_unavailable")}</p>
        )}
        {isPDF && original && (
          <form
            className="page-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (pageValid)
                window.open(
                  `${original}#page=${Number(page)}`,
                  "_blank",
                  "noopener",
                );
            }}
          >
            <label htmlFor="pdf-page">{s("pdf_page")}</label>
            <input
              id="pdf-page"
              type="number"
              min="1"
              step="1"
              inputMode="numeric"
              value={page}
              onChange={(event) => setPage(event.target.value)}
              aria-describedby="page-help"
              required
            />
            <button
              className="quiet-button"
              type="submit"
              disabled={!pageValid}
            >
              {s("open_page")} ↗
            </button>
            <p id="page-help">{s("page_help")}</p>
          </form>
        )}
      </div>
      <p className="review-notice">{s("review_notice")}</p>
      <dl className="detail-fields">
        <div>
          <dt>{s("membership")}</dt>
          <dd>
            {libraries.map((library) => library.folder_name).join(" · ") ||
              s("not_available")}
          </dd>
        </div>
        {fields.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{renderValue(value)}</dd>
          </div>
        ))}
      </dl>
      <h2>{s("metadata")}</h2>
      {(document.metadata_info || []).length ? (
        <dl className="detail-fields">
          {document.metadata_info.map((item) => (
            <div key={item.id}>
              <dt>{item.type_name}</dt>
              <dd>{renderValue(item.name)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p>{s("no_metadata")}</p>
      )}
    </article>
  );
}
