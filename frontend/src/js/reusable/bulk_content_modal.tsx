import React, { useEffect, useRef, useState } from "react";
import { Dialog, DialogTitle, DialogContent, DialogActions } from "@material-ui/core";
import { CatalogueFolder, CatalogueTree } from "../catalogue_tree";
import { LibraryVersion } from "../types";
import { loadTree, request } from "../manager_api";
import PlacementPicker from "../manager_placement_picker";
import { useManagerStrings } from "../manager_strings";
import { read_excel_file } from "../utils";

interface Props {
  is_open: boolean;
  show_toast_message: (message: string, success: boolean) => void;
  on_close: () => void;
  show_loader: () => void;
  remove_loader: () => void;
  initialVersion?: number;
  initialFolder?: number;
}
export default function BulkContentModal(props: Props) {
  const s = useManagerStrings();
  const [versions, setVersions] = useState<LibraryVersion[]>([]);
  const [versionId, setVersionId] = useState(props.initialVersion || 0);
  const [folders, setFolders] = useState<CatalogueFolder[]>([]);
  const [placements, setPlacements] = useState<number[]>(props.initialFolder ? [props.initialFolder] : []);
  const [path, setPath] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [placementBusy, setPlacementBusy] = useState(false);
  const [error, setError] = useState("");
  const [failures, setFailures] = useState<{file_name: string; error: string}[]>([]);
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => {
    let current = true;
    if (!props.is_open) return;
    setLoading(true);
    loadTree(versionId || undefined).then((tree: CatalogueTree) => {
      if (!current) return;
      setVersions(tree.versions);
      setVersionId(tree.catalogue_version || 0);
      setFolders(tree.folders);
      setPlacements((selected) => selected.filter((id) => tree.folders.some((folder) => folder.id === id)));
      setLoading(false);
    }).catch((failure) => {
      if (current) {setError(`${s("load_error")} ${failure instanceof Error ? failure.message : ""}`); setLoading(false);}
    });
    return () => {current = false;};
  }, [props.is_open, versionId]);
  async function createSection(parent: number, name: string) {
    const created = await request("/api/library_folders/", "POST", {
      folder_name: name, parent, version: versionId, logo_img: null, library_content: [],
    });
    const section = {...created, document_count: 0, direct_document_count: 0};
    setFolders((current) => [...current, section]);
    return section;
  }
  async function importDocuments(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    if (!file.current?.files?.[0]) {setError(s("bulk_sheet_required")); return;}
    if (path.trim() && !placements.length) {setError(s("placement_required")); return;}
    setBusy(true);
    props.show_loader();
    try {
      const sheet = await read_excel_file(file.current.files[0]);
      const result = await request("/api/content_bulk_add/", "POST", {
        sheet_data: sheet, content_path: path.trim(),
        ...(path.trim() ? {catalogue_version: versionId, folder_ids: placements} : {}),
      });
      setFailures(result.unsuccessful_uploads || []);
      props.show_toast_message(s("bulk_added", {count: result.success_count || 0}), true);
      if (!result.unsuccessful_uploads?.length) props.on_close();
    } catch (failure) {
      setError(`${s("bulk_error")} ${failure instanceof Error ? failure.message : ""}`);
    } finally {
      setBusy(false);
      props.remove_loader();
    }
  }
  const locked = busy || placementBusy || loading;
  if (!props.is_open) return null;
  return (
    <Dialog open fullWidth maxWidth="md" className="manager-dialog" onClose={() => {if (!locked) props.on_close();}} aria-labelledby="manager-bulk-title">
      <DialogTitle id="manager-bulk-title">{s("bulk_upload_title")}</DialogTitle>
      <DialogContent>
        <form id="manager-bulk-form" className="manager-form" onSubmit={importDocuments}>
          {error && <p className="manager-error" role="alert">{error}</p>}
          <label className="manager-field">{s("bulk_file_location")}
            <input autoFocus value={path} disabled={locked} onChange={(event) => setPath(event.target.value)} />
            <span className="manager-help">{s("bulk_file_location_help")}</span>
          </label>
          <label className="manager-field">{s("bulk_metadata_file")}
            <input type="file" ref={file} disabled={locked} accept=".xlsx,.xls,.csv" />
          </label>
          <fieldset className="manager-fieldset" disabled={locked}>
            <legend>{s("membership")}</legend>
            <p className="manager-help">{s("bulk_placement_help")}</p>
            <label className="manager-field">{s("version")}
              <select value={versionId || ""} disabled={locked} onChange={(event) => {setVersionId(Number(event.target.value)); setPlacements([]); setFolders([]);}}>
                {!versions.length && <option value="">{s("no_libraries")}</option>}
                {versions.map((version) => <option key={version.id} value={version.id}>{s("version_label", {name: version.library_name, version: version.version_number})}</option>)}
              </select>
            </label>
            <PlacementPicker folders={folders} value={placements} disabled={locked} onChange={setPlacements} onCreateSection={createSection} onBusy={setPlacementBusy} />
          </fieldset>
          {failures.length > 0 && <table className="manager-bulk-errors">
            <thead><tr><th>{s("bulk_file_column")}</th><th>{s("bulk_error_column")}</th></tr></thead>
            <tbody>{failures.map((failure, index) => <tr key={index}><td>{failure.file_name}</td><td>{failure.error}</td></tr>)}</tbody>
          </table>}
        </form>
      </DialogContent>
      <DialogActions>
        <button type="button" className="manager-button" disabled={locked} onClick={props.on_close}>{s("cancel")}</button>
        <button type="submit" form="manager-bulk-form" className="manager-button manager-button-primary" disabled={locked}>{busy ? s("saving") : s("bulk_add_files")}</button>
      </DialogActions>
    </Dialog>
  );
}
