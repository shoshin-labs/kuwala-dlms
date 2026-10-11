import React, { useEffect, useRef, useState } from "react";
import { CatalogueFolder, folderAncestors, withinFolder } from "./catalogue_tree";
import { useStrings } from "./i18n";

interface Props {
  id: string;
  folders: CatalogueFolder[];
  libraries: CatalogueFolder[];
  library?: CatalogueFolder;
  section?: CatalogueFolder;
  allDocuments?: { name: string; count: number };
  initialOpen?: boolean;
  disabled?: boolean;
  onChoose: (library?: CatalogueFolder, section?: CatalogueFolder) => void;
}

/** Folder IDs remain the navigation contract; the disclosure only changes presentation. */
export default function CatalogueNavigation({
  id, folders, libraries, library, section, allDocuments,
  initialOpen = false, disabled = false, onChoose,
}: Props) {
  const s = useStrings();
  const [open, setOpen] = useState(initialOpen);
  const [librarySearch, setLibrarySearch] = useState("");
  const [sectionSearch, setSectionSearch] = useState("");
  const [browsingLibraryId, setBrowsingLibraryId] = useState(library?.id);
  const browsingLibrary = libraries.find((item) => item.id === browsingLibraryId);
  const summary = useRef<HTMLElement>(null);
  const sectionInput = useRef<HTMLInputElement>(null);
  const scope = `${library?.id || 0}/${section?.id || 0}`;
  const previousScope = useRef(scope);
  const countLabel = (count: number) =>
    count === 1 ? s("one_document") : s("document_count", { count });
  const sectionPath = (item: CatalogueFolder) =>
    folderAncestors(item, folders).slice(1).map((parent) => parent.folder_name).join(" / ");
  const sections = browsingLibrary ? folders.filter((item) =>
    item.id !== browsingLibrary.id && withinFolder(item, browsingLibrary, folders),
  ).sort((a, b) => sectionPath(a).localeCompare(sectionPath(b))) : [];
  const matches = (name: string, query: string) =>
    name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
  const matchingLibraries = libraries.filter((item) => matches(item.folder_name, librarySearch));
  const matchingSections = sections.filter((item) => matches(sectionPath(item), sectionSearch));
  const currentCount = section?.document_count ?? library?.document_count ?? allDocuments?.count;

  function close() {
    setOpen(false);
    setLibrarySearch("");
    setSectionSearch("");
    setBrowsingLibraryId(library?.id);
  }
  function choose(root?: CatalogueFolder, child?: CatalogueFolder) {
    close();
    // A repeated selection may not trigger the parent's navigation effect.
    // Keep keyboard focus on a visible control even when the scope is unchanged.
    summary.current?.focus();
    onChoose(root, child);
  }
  function browse(root: CatalogueFolder) {
    if (!folders.some((item) => item.parent === root.id)) {
      choose(root);
      return;
    }
    setBrowsingLibraryId(root.id);
    setSectionSearch("");
  }
  useEffect(() => {
    if (previousScope.current !== scope) {
      close();
      // Returning to the catalogue overview should reveal its single library
      // list just as a first visit does. Selected scopes remain compact.
      setOpen(initialOpen);
      previousScope.current = scope;
    }
  }, [scope, initialOpen]);
  useEffect(() => {
    if (open && browsingLibrary?.id !== library?.id) sectionInput.current?.focus();
  }, [browsingLibrary?.id]);

  return (
    <details
      className="catalogue-location"
      open={open}
      onToggle={(event) => {
        if (event.currentTarget.open) {
          setBrowsingLibraryId(library?.id);
          setOpen(true);
        } else close();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.preventDefault();
          close();
          summary.current?.focus();
        }
      }}
    >
      <summary ref={summary} aria-controls={`${id}-choices`}>
        <span className="catalogue-location-current">
          <strong>{library?.folder_name || allDocuments?.name || s("choose_library")}</strong>
          <span>
            {library && <>{section ? sectionPath(section) : s("all_library_documents")} · </>}
            {currentCount !== undefined ? countLabel(currentCount) : s("libraries")}
          </span>
        </span>
        <span className="catalogue-location-action">
          {open ? s("close_location") : s("change_location")}
          <span className="catalogue-location-chevron" aria-hidden="true">⌄</span>
        </span>
      </summary>
      <div id={`${id}-choices`} className="catalogue-location-choices">
        <div className="catalogue-location-group">
          <h2>{s("libraries")} <span className="count">{libraries.length}</span></h2>
          <label className="catalogue-location-search" htmlFor={`${id}-library-search`}>
            {s("search_libraries")}
            <input id={`${id}-library-search`} type="search" value={librarySearch}
              disabled={disabled} onChange={(event) => setLibrarySearch(event.target.value)} />
          </label>
          <nav className="catalogue-location-list" aria-label={s("libraries")}>
            {allDocuments && !librarySearch.trim() && <button type="button"
              className={!library ? "is-selected" : ""} disabled={disabled}
              aria-current={!library ? "page" : undefined} onClick={() => choose()}>
              <strong>{allDocuments.name}</strong><span>{countLabel(allDocuments.count)}</span>
            </button>}
            {matchingLibraries.map((item) => <button key={item.id} type="button"
              className={browsingLibrary?.id === item.id ? "is-selected" : ""} disabled={disabled}
              aria-current={library?.id === item.id ? "page" : undefined}
              aria-pressed={browsingLibrary?.id === item.id} onClick={() => browse(item)}>
              <strong>{item.folder_name}</strong><span>{countLabel(item.document_count)}</span>
            </button>)}
            {!matchingLibraries.length && libraries.length > 0 && <p role="status">{s("no_matching_libraries")}</p>}
          </nav>
        </div>
        {browsingLibrary && sections.length > 0 && <div className="catalogue-location-group">
          <h2>{s("sections_in", { name: browsingLibrary.folder_name })} <span className="count">{sections.length}</span></h2>
          <label className="catalogue-location-search" htmlFor={`${id}-section-search`}>
            {s("search_sections")}
            <input ref={sectionInput} id={`${id}-section-search`} type="search" value={sectionSearch}
              aria-label={s("search_sections_in", { name: browsingLibrary.folder_name })}
              disabled={disabled} onChange={(event) => setSectionSearch(event.target.value)} />
          </label>
          <nav className="catalogue-location-list" aria-label={s("sections_in", { name: browsingLibrary.folder_name })}>
            {!sectionSearch.trim() && <button type="button" className={browsingLibrary.id === library?.id && !section ? "is-selected" : ""}
              disabled={disabled} aria-current={browsingLibrary.id === library?.id && !section ? "page" : undefined}
              onClick={() => choose(browsingLibrary)}>
              <strong>{s("all_library_documents")}</strong><span>{countLabel(browsingLibrary.document_count)}</span>
            </button>}
            {matchingSections.map((item) => <button key={item.id} type="button"
              className={section?.id === item.id ? "is-selected" : ""} disabled={disabled}
              aria-current={section?.id === item.id ? "page" : undefined} onClick={() => choose(browsingLibrary, item)}>
              <strong>{sectionPath(item)}</strong><span>{countLabel(item.document_count)}</span>
            </button>)}
            {!matchingSections.length && <p role="status">{s("no_matching_sections")}</p>}
          </nav>
        </div>}
      </div>
    </details>
  );
}
