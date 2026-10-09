import React, { useEffect, useRef, useState } from "react";
import { get_data } from "./urls";
import {
  CatalogueFolder,
  CatalogueTree,
  CataloguedDocument,
  DocumentPage,
  catalogueQuery,
  folderAncestors,
  withinFolder,
} from "./catalogue_tree";
import { useStrings } from "./i18n";
import "../css/catalogue.css";

interface CatalogueLocation {
  version: string;
  library: string;
  section: string;
  document: string;
  q: string;
  page: string;
}
function readLocation(): CatalogueLocation {
  const params = new URL(window.location.href).searchParams;
  return {
    version: params.get("version") || "",
    library: params.get("library") || "",
    section: params.get("section") || "",
    document: params.get("document") || "",
    q: params.get("q") || "",
    page:
      /^\d+$/.test(params.get("page") || "") && Number(params.get("page")) > 0
        ? params.get("page")!
        : "1",
  };
}
function documentTitle(document: CataloguedDocument) {
  return document.display_title || document.title || document.file_name;
}
function originalURL(document: CataloguedDocument) {
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
  const [tree, setTree] = useState<CatalogueTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [result, setResult] = useState<DocumentPage<CataloguedDocument> | null>(
    null,
  );
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [documentAttempt, setDocumentAttempt] = useState(0);
  const [search, setSearch] = useState(location.q);
  const heading = useRef<HTMLHeadingElement>(null);
  const navigated = useRef(false);
  const folders = tree?.folders || [];
  const versions = tree?.versions || [];
  const version = versions.find((item) => item.id === tree?.catalogue_version);
  const libraries = folders.filter((folder) => folder.parent === null);
  const library = libraries.find(
    (folder) => String(folder.id) === location.library,
  );
  const section = folders.find(
    (folder) =>
      String(folder.id) === location.section &&
      library &&
      folder.id !== library.id &&
      withinFolder(folder, library, folders),
  );
  const selected = section || library;
  const sections = library
    ? folders
        .filter(
          (folder) =>
            folder.id !== library.id && withinFolder(folder, library, folders),
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
  const children = selected
    ? folders.filter((folder) => folder.parent === selected.id)
    : [];
  const selectedDocument = location.document
    ? result?.results.find((item) => String(item.id) === location.document)
    : undefined;
  const countLabel = (count: number) =>
    count === 1 ? s("one_document") : s("document_count", { count });
  function navigate(update: Partial<CatalogueLocation>, replace = false) {
    // Keep the canonical list context when an input debounce or browser
    // navigation has changed the URL since this handler was rendered.
    const next = { ...readLocation(), ...update };
    const url = new URL(window.location.href);
    Object.entries(next).forEach(([key, value]) =>
      value && !(key === "page" && value === "1")
        ? url.searchParams.set(key, value)
        : url.searchParams.delete(key),
    );
    url.searchParams.set("tab", "contents");
    history[replace ? "replaceState" : "pushState"]({}, "", url.toString());
    if (!replace) navigated.current = true;
    setLocation(next);
    setSearch(next.q);
  }
  const choose = (root: CatalogueFolder, child?: CatalogueFolder) =>
    navigate({
      version: String(version!.id),
      library: String(root.id),
      section: child ? String(child.id) : "",
      document: "",
      q: "",
      page: "1",
    });
  useEffect(() => {
    const onPop = () => {
      const next = readLocation();
      navigated.current = true;
      setLocation(next);
      setSearch(next.q);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(false);
    setTree(null);
    get_data(
      catalogueQuery("/api/oasis/catalogue/", {
        catalogue_version: location.version,
      }),
    )
      .then((data) => {
        if (current) {
          setTree(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (current) {
          setError(true);
          setLoading(false);
        }
      });
    return () => {
      current = false;
    };
  }, [location.version, attempt]);
  useEffect(() => {
    let current = true;
    setResult(null);
    setDocumentsError(false);
    if (!version || !selected || (location.section && !section)) {
      setDocumentsLoading(false);
      return;
    }
    setDocumentsLoading(true);
    get_data(
      catalogueQuery("/api/oasis/catalogue/documents/", {
        catalogue_version: version.id,
        folder_id: selected.id,
        document_id: location.document || undefined,
        q: location.document ? undefined : location.q,
        page: location.document ? 1 : Number(location.page),
        size: 24,
      }),
    )
      .then((data) => {
        if (current) {
          setResult(data);
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
  }, [
    version?.id,
    selected?.id,
    location.section,
    location.document,
    location.q,
    location.page,
    documentAttempt,
  ]);
  useEffect(() => {
    if (search === location.q) return;
    const timer = window.setTimeout(
      () => navigate({ q: search, page: "1", document: "" }, true),
      300,
    );
    return () => window.clearTimeout(timer);
  }, [search, location.q]);
  useEffect(() => {
    if (!loading && !documentsLoading && navigated.current) {
      heading.current?.focus();
      navigated.current = false;
    }
  }, [location, loading, documentsLoading]);
  const documentLibraries = selectedDocument
    ? libraries.filter((root) =>
        (selectedDocument.catalogue_folder_ids || []).some((id) => {
          const folder = folders.find((item) => item.id === id);
          return folder && withinFolder(folder, root, folders);
        }),
      )
    : [];
  return (
    <section className="catalogue">
      <div className="workspace-head">
        <h1 ref={heading} tabIndex={-1}>
          {selectedDocument
            ? documentTitle(selectedDocument)
            : selected
              ? selected.folder_name
              : s("libraries")}
        </h1>
        {!library && <p className="intro-text">{s("catalogue_intro")}</p>}
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
                section: "",
                document: "",
                q: "",
                page: "1",
              })
            }
          >
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
            onClick={() => setAttempt((value) => value + 1)}
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
      ) : (
        <div className="catalogue-layout">
          <aside
            className="catalogue-navigation"
            aria-labelledby="catalogue-library-nav-title"
          >
            <h2 id="catalogue-library-nav-title">{s("libraries")}</h2>
            <nav className="catalogue-library-nav" aria-label={s("libraries")}>
              {libraries.map((root) => (
                <button
                  key={root.id}
                  className={library?.id === root.id ? "is-selected" : ""}
                  aria-current={library?.id === root.id ? "page" : undefined}
                  onClick={() => choose(root)}
                >
                  <strong>{root.folder_name}</strong>
                  <span>{countLabel(root.document_count)}</span>
                </button>
              ))}
            </nav>
            {library && sections.length > 0 && (
              <nav
                className="catalogue-section-nav"
                aria-label={s("sections_in", { name: library.folder_name })}
              >
                <h3>{s("sections")}</h3>
                <button
                  className={!section ? "is-selected" : ""}
                  onClick={() => choose(library)}
                  aria-current={!section ? "page" : undefined}
                >
                  <span>{s("all_library_documents")}</span>
                  <span>{library.document_count}</span>
                </button>
                {sections.map((child) => (
                  <button
                    key={child.id}
                    className={section?.id === child.id ? "is-selected" : ""}
                    aria-current={section?.id === child.id ? "page" : undefined}
                    style={{
                      paddingLeft:
                        12 +
                        Math.max(
                          0,
                          folderAncestors(child, folders).length - 2,
                        ) *
                          12,
                    }}
                    onClick={() => choose(library, child)}
                  >
                    <span>{child.folder_name}</span>
                    <span>{child.document_count}</span>
                  </button>
                ))}
              </nav>
            )}
          </aside>
          <div className="catalogue-main">
            {(location.library && !library) ||
            (location.section && !section) ? (
              <p role="alert">{s("missing_library")}</p>
            ) : !library ? (
              libraries.length ? (
                <div className="catalogue-overview">
                  {libraries.map((root) => (
                    <article
                      key={root.id}
                      className="catalogue-overview-library"
                    >
                      <h2>
                        <button onClick={() => choose(root)}>
                          <span>{root.folder_name}</span>
                          <span className="catalogue-overview-count">
                            {countLabel(root.document_count)}{" "}
                            <span aria-hidden="true">→</span>
                          </span>
                        </button>
                      </h2>
                      {folders.some((child) => child.parent === root.id) && (
                        <>
                          <h3>{s("sections")}</h3>
                          <ul>
                            {folders
                              .filter((child) => child.parent === root.id)
                              .map((child) => (
                                <li key={child.id}>
                                  <button onClick={() => choose(root, child)}>
                                    <span>{child.folder_name}</span>
                                    <span>
                                      {countLabel(child.document_count)}{" "}
                                      <span aria-hidden="true">→</span>
                                    </span>
                                  </button>
                                </li>
                              ))}
                          </ul>
                        </>
                      )}
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <h2>{s("no_libraries")}</h2>
                  <p>{s("no_libraries_help")}</p>
                </div>
              )
            ) : (
              <>
                {(section || location.document) && (
                  <nav
                    className="catalogue-breadcrumbs"
                    aria-label={s("breadcrumb")}
                  >
                    <button onClick={() => choose(library)}>
                      {library.folder_name}
                    </button>
                    {section &&
                      folderAncestors(section, folders)
                        .filter((item) => item.id !== library.id)
                        .map((child) => (
                          <React.Fragment key={child.id}>
                            <span aria-hidden="true">/</span>
                            <button onClick={() => choose(library, child)}>
                              {child.folder_name}
                            </button>
                          </React.Fragment>
                        ))}
                    {location.document && (
                      <button
                        className="text-button"
                        onClick={() => navigate({ document: "" })}
                      >
                        ← {s("back_documents")}
                      </button>
                    )}
                  </nav>
                )}
                {!location.document && children.length > 0 && (
                  <section className="catalogue-sections">
                    <h2>{s("sections")}</h2>
                    <div className="catalogue-section-cards">
                      {children.map((child) => (
                        <button
                          key={child.id}
                          onClick={() => choose(library, child)}
                        >
                          <strong>{child.folder_name}</strong>
                          <span>{countLabel(child.document_count)}</span>
                        </button>
                      ))}
                    </div>
                  </section>
                )}
                {!location.document && (
                  <div className="document-toolbar">
                    <h2 className="section-label">
                      {s("documents")}{" "}
                      <span className="count">
                        {result?.count ?? selected!.document_count}
                      </span>
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
                )}
                {documentsLoading ? (
                  <p role="status" className="empty-state">
                    {s("loading_documents")}
                  </p>
                ) : documentsError ? (
                  <div role="alert" className="empty-state">
                    <p>{s("documents_error")}</p>
                    <button
                      className="quiet-button"
                      onClick={() => setDocumentAttempt((value) => value + 1)}
                    >
                      {s("retry")}
                    </button>
                  </div>
                ) : location.document ? (
                  selectedDocument ? (
                    <DocumentDetail
                      key={selectedDocument.id}
                      document={selectedDocument}
                      libraries={documentLibraries}
                    />
                  ) : (
                    <p role="alert">{s("missing_document")}</p>
                  )
                ) : !result?.results.length ? (
                  <div className="empty-state">
                    <p>{location.q ? s("no_results") : s("no_documents")}</p>
                    {location.q && (
                      <button
                        className="quiet-button"
                        onClick={() => navigate({ q: "", page: "1" }, true)}
                      >
                        {s("clear_search")}
                      </button>
                    )}
                  </div>
                ) : (
                  <>
                    <ul className="document-list">
                      {result.results.map((item) => (
                        <li key={item.id}>
                          <button
                            className="document-choice"
                            onClick={() =>
                              navigate({ document: String(item.id) })
                            }
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
                                      /creator|author|source/i.test(
                                        meta.type_name,
                                      ),
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
                    <div className="catalogue-pagination">
                      <p>
                        {s("page_summary", {
                          first: (result.page - 1) * result.page_size + 1,
                          last: Math.min(
                            result.page * result.page_size,
                            result.count,
                          ),
                          count: result.count,
                        })}
                      </p>
                      <div>
                        <button
                          className="quiet-button"
                          disabled={!result.previous}
                          onClick={() =>
                            navigate({ page: String(result.page - 1) })
                          }
                        >
                          {s("previous_page")}
                        </button>
                        <button
                          className="quiet-button"
                          disabled={!result.next}
                          onClick={() =>
                            navigate({ page: String(result.page + 1) })
                          }
                        >
                          {s("next_page")}
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function DocumentDetail({
  document,
  libraries,
}: {
  document: CataloguedDocument;
  libraries: CatalogueFolder[];
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
