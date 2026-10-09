import React, { useRef, useState } from "react";
import { CatalogueFolder, folderAncestors, withinFolder } from "./catalogue_tree";
import { folderPath } from "./manager_api";
import { useManagerStrings } from "./manager_strings";

interface Props {
  folders: CatalogueFolder[];
  value: number[];
  disabled?: boolean;
  onChange: (value: number[]) => void;
  onCreateSection: (parent: number, name: string) => Promise<CatalogueFolder>;
  onBusy?: (busy: boolean) => void;
}

/** Keep the existing exact folder IDs: a section is a child folder, not a tag. */
export default function PlacementPicker(props: Props) {
  const s = useManagerStrings();
  const libraries = props.folders.filter((folder) => folder.parent === null);
  const [adding, setAdding] = useState(false);
  const [additionalLibrary, setAdditionalLibrary] = useState(0);
  const [sectionFor, setSectionFor] = useState<number | null>(null);
  const [parentId, setParentId] = useState(0);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pickerId = useRef(`placement-${Math.random().toString(36).slice(2)}`);
  const locked = props.disabled || busy;
  const ordered = (folders: CatalogueFolder[]) => folders.slice().sort((a, b) =>
    folderPath(a, props.folders).localeCompare(folderPath(b, props.folders)));
  function replace(oldId: number, newId: number) {
    props.onChange(Array.from(new Set(props.value.map((id) => id === oldId ? newId : id))));
  }
  async function createSection() {
    if (sectionFor === null || !parentId || !name.trim()) return;
    setBusy(true);
    props.onBusy?.(true);
    setError("");
    try {
      const section = await props.onCreateSection(parentId, name.trim());
      replace(sectionFor, section.id);
      setSectionFor(null);
      setName("");
    } catch (failure) {
      setError(`${s("operation_error")} ${failure instanceof Error ? failure.message : ""}`);
    } finally {
      setBusy(false);
      props.onBusy?.(false);
    }
  }
  return (
    <div className="manager-placement-picker">
      {error && <p className="manager-error" role="alert">{error}</p>}
      {props.value.map((id) => {
        const folder = props.folders.find((item) => item.id === id);
        const library = folder && folderAncestors(folder, props.folders)[0];
        const sections = library ? ordered(props.folders.filter((item) =>
          item.id !== library.id && withinFolder(item, library, props.folders))) : [];
        return (
          <div key={id} className="manager-placement">
            <div className="manager-placement-controls">
              <label className="manager-field">
                {s("placement_library")}
                <select value={library?.id || ""} disabled={locked} required
                  onChange={(event) => { replace(id, Number(event.target.value)); setSectionFor(null); }}>
                  <option value="" disabled>{s("choose_library")}</option>
                  {ordered(libraries).map((root) => <option key={root.id} value={root.id}>{root.folder_name}</option>)}
                </select>
              </label>
              <label className="manager-field">
                {s("placement_section")}
                <select value={folder?.id || ""} disabled={locked || !library}
                  onChange={(event) => { replace(id, Number(event.target.value)); setSectionFor(null); }}>
                  {!library && <option value="">{s("choose_library")}</option>}
                  {library && <option value={library.id}>{s("library_documents_no_section")}</option>}
                  {sections.map((section) => <option key={section.id} value={section.id}>
                    {folderAncestors(section, props.folders).slice(1).map((item) => item.folder_name).join(" / ")}
                  </option>)}
                </select>
              </label>
              <button type="button" className="manager-text-button" disabled={locked}
                aria-label={s("remove_placement_named", {name: folder ? folderPath(folder, props.folders) : id})}
                onClick={() => {props.onChange(props.value.filter((value) => value !== id)); setSectionFor(null);}}>
                {s("remove_placement")}
              </button>
            </div>
            {library && <button type="button" className="manager-text-button" disabled={locked}
              onClick={() => { setSectionFor(id); setParentId(id); setName(""); setError(""); }}>
              + {s("new_section")}
            </button>}
            {sectionFor === id && library && (
              <div className="manager-inline-form">
                <p className="manager-help">{s("new_section_assignment_help")}</p>
                <div className="manager-form-grid">
                  <label className="manager-field">{s("section_parent")}
                    <select value={parentId} disabled={locked} onChange={(event) => setParentId(Number(event.target.value))}>
                      <option value={library.id}>{library.folder_name}</option>
                      {sections.map((section) => <option key={section.id} value={section.id}>{folderPath(section, props.folders)}</option>)}
                    </select>
                  </label>
                  <label className="manager-field">{s("section_name")}
                    <input autoFocus maxLength={200} value={name} disabled={locked}
                      onChange={(event) => setName(event.target.value)} />
                  </label>
                </div>
                <div className="manager-inline-actions">
                  <button type="button" className="manager-button" disabled={locked || !name.trim()} onClick={createSection}>
                    {busy ? s("saving") : s("create_section")}
                  </button>
                  <button type="button" className="manager-text-button" disabled={locked} onClick={() => setSectionFor(null)}>{s("cancel")}</button>
                </div>
              </div>
            )}
          </div>
        );
      })}
      {(adding || !props.value.length) && libraries.length > 0 ? (
        <div className="manager-field">
          <label htmlFor={pickerId.current}>{props.value.length ? s("additional_placement") : s("placement_library")}</label>
          <select id={pickerId.current} value={additionalLibrary || ""} disabled={locked}
            onChange={(event) => {
              const id = Number(event.target.value);
              if (props.value.includes(id)) {setAdditionalLibrary(id); return;}
              props.onChange([...props.value, id]); setAdding(false); setAdditionalLibrary(0);
            }}>
            <option value="" disabled>{s("choose_library")}</option>
            {ordered(libraries).map((library) => <option key={library.id} value={library.id}>{library.folder_name}</option>)}
          </select>
          {additionalLibrary > 0 && <>
            <span className="manager-help">{s("library_already_selected")}</span>
            <label htmlFor={pickerId.current + "-section"}>{s("placement_section")}</label>
            <select id={pickerId.current + "-section"} value="" disabled={locked}
              onChange={(event) => {props.onChange(Array.from(new Set([...props.value, Number(event.target.value)]))); setAdding(false); setAdditionalLibrary(0);}}>
              <option value="" disabled>{s("choose_section")}</option>
              {ordered(props.folders.filter((section) => {
                const root = libraries.find((library) => library.id === additionalLibrary);
                return root && section.id !== root.id && withinFolder(section, root, props.folders) && !props.value.includes(section.id);
              })).map((section) => <option key={section.id} value={section.id}>{folderPath(section, props.folders)}</option>)}
            </select>
            <button type="button" className="manager-text-button" disabled={locked} onClick={() => {setAdding(false); setAdditionalLibrary(0);}}>{s("cancel")}</button>
          </>}
        </div>
      ) : libraries.length > 0 && (
        <button type="button" className="manager-text-button" disabled={locked} onClick={() => setAdding(true)}>+ {s("additional_placement")}</button>
      )}
      {!libraries.length && <p className="manager-help">{s("no_membership_help")}</p>}
    </div>
  );
}
