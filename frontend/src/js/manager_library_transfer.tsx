import React, { useState } from "react";
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, TextField } from "@material-ui/core";
import { CatalogueFolder } from "./catalogue_tree";
import { message, request } from "./manager_api";
import { useLibraryTransferStrings } from "./library_transfer_strings";

interface TransferPlan {
  target_version?: number;
  bundle_sha256: string;
  library_name: string;
  section_count: number;
  document_count: number;
  original_bytes: number;
  warnings: string[];
}
interface Props {
  versionId?: number;
  libraries: CatalogueFolder[];
  selectedLibraryId?: number;
  onImported: (libraryId: number) => void;
}
const LIMIT = 80 * 1024 * 1024;

export default function LibraryTransferControls({ versionId, libraries, selectedLibraryId, onImported }: Props) {
  const text = useLibraryTransferStrings();
  const [mode, setMode] = useState<"import" | "export" | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [plan, setPlan] = useState<TransferPlan | null>(null);
  const [name, setName] = useState("");
  const [exportId, setExportId] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const selected = libraries.find(library => library.id === exportId);
  const duplicate = libraries.some(library => library.folder_name.trim().toLowerCase() === name.trim().toLowerCase());
  const targetChanged = Boolean(plan && plan.target_version !== versionId);
  const validName = Boolean(name.trim() && name.trim().length <= 300 && !duplicate);
  function close() { if (!busy) setMode(null); }
  function open(next: "import" | "export") {
    setMode(next); setFile(null); setPlan(null); setName(""); setError(""); setNotice("");
    setExportId(selectedLibraryId || libraries[0]?.id || 0);
  }
  function payload() {
    const body = new FormData();
    body.append("bundle", file!);
    body.append("catalogue_version", String(versionId));
    return body;
  }
  function suggestedName(original: string) {
    const names = new Set(libraries.map(library => library.folder_name.trim().toLowerCase()));
    if (!names.has(original.trim().toLowerCase())) return original;
    let candidate = "";
    let suffix = 1;
    do { candidate = text.imported_name.replace("{name}", original.slice(0, 265)).replace("{number}", String(suffix++)); } while (names.has(candidate.trim().toLowerCase()));
    return candidate;
  }
  async function inspect() {
    if (!file || !versionId || busy) return;
    if (file.size > LIMIT) { setError(text.size_error); return; }
    setBusy(true); setError("");
    try {
      const result: TransferPlan = await request("/api/oasis/libraries/import/?dry_run=1", "POST", payload());
      setPlan({ ...result, target_version: versionId }); setName(suggestedName(result.library_name));
    } catch (failure) { setError(failure?.message || text.inspect_failed); }
    finally { setBusy(false); }
  }
  async function importLibrary() {
    if (!file || !plan || !versionId || !validName || busy || plan.target_version !== versionId) return;
    setBusy(true); setError("");
    try {
      const body = payload();
      body.append("expected_sha256", plan.bundle_sha256);
      body.append("confirmed", "true");
      body.append("library_name", name.trim());
      const result = await request("/api/oasis/libraries/import/", "POST", body);
      setMode(null); setNotice(text.imported.replace("{name}", result.library.name));
      onImported(result.library.id);
    } catch (failure) { setError(failure?.message || text.import_failed); }
    finally { setBusy(false); }
  }
  async function exportLibrary() {
    if (!selected || busy) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/oasis/libraries/${selected.id}/bundle/`, { credentials: "same-origin" });
      if (!response.ok) {
        const result = await response.json().catch(() => null);
        throw new Error(message(result?.error || result) || text.export_failed);
      }
      if (!(response.headers.get("Content-Type") || "").includes("application/zip")) throw new Error(text.export_failed);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const download = document.createElement("a");
      const filename = response.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1];
      download.href = url; download.download = filename || "kuwala-library.zip";
      document.body.appendChild(download); download.click(); download.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30000);
      setMode(null); setNotice(text.exported.replace("{name}", selected.folder_name));
    } catch (failure) { setError(failure?.message || text.export_failed); }
    finally { setBusy(false); }
  }
  return <>
    <div className="manager-transfer-controls">
      <button type="button" className="manager-button" disabled={!versionId} onClick={() => open("import")}>{text.import_library}</button>
      <button type="button" className="manager-button" disabled={!versionId || !libraries.length} onClick={() => open("export")}>{text.export_library}</button>
    </div>
    {notice && <p className="manager-transfer-notice" role="status">{notice}</p>}
    {mode && <Dialog open fullWidth maxWidth="sm" className="manager-dialog" onClose={close} aria-labelledby="library-transfer-title">
      <DialogTitle id="library-transfer-title">{mode === "import" ? text.import_library : text.export_library}</DialogTitle>
      <DialogContent>
        <p>{mode === "import" ? text.import_help : text.export_help}</p>
        <p className="manager-help">{text.private_help}</p>
        {mode === "export" ? <label className="manager-field">
          <span>{text.library}</span>
          <select value={exportId} disabled={busy} onChange={event => setExportId(Number(event.target.value))}>
            {libraries.map(library => <option value={library.id} key={library.id}>{library.folder_name}</option>)}
          </select>
        </label> : <>
          <div className="advanced-file-field">
            <label htmlFor="library-transfer-file">{text.package_file}</label>
            <input id="library-transfer-file" type="file" accept=".zip,application/zip" disabled={busy} aria-describedby="library-transfer-limit" onChange={event => {setFile(event.target.files?.[0] || null); setPlan(null); setName(""); setError("");}} />
            <p id="library-transfer-limit" className="manager-help">{text.limit_help}</p>
          </div>
          {plan && <div className="manager-transfer-review">
            <h3>{text.review_heading}</h3>
            <p>{text.review_counts.replace("{documents}", (plan.document_count === 1 ? text.one_document : text.many_documents.replace("{count}", String(plan.document_count)))).replace("{sections}", (plan.section_count === 1 ? text.one_section : text.many_sections.replace("{count}", String(plan.section_count))))}</p>
            <p>{text.source_library.replace("{name}", plan.library_name)}</p>
            <TextField id="library-transfer-name" fullWidth required disabled={busy} label={text.import_as} value={name} inputProps={{maxLength:300}} error={duplicate} helperText={duplicate ? text.name_exists : text.name_help} onChange={event => {setName(event.target.value); setError("");}} />
            <p className="manager-help">{text.additive_help}</p>
            <p className="manager-help">{text.filename_help}</p>
          </div>}
        </>}
        {targetChanged && <p className="manager-error" role="alert">{text.target_changed}</p>}
        {busy && <p role="status">{mode === "export" ? text.preparing : plan ? text.importing : text.inspecting}</p>}
        {error && <p className="manager-error" role="alert">{error}</p>}
      </DialogContent>
      <DialogActions>
        <Button onClick={close} disabled={busy}>{text.cancel}</Button>
        {mode === "export" ? <Button variant="contained" color="primary" disabled={busy || !selected} onClick={exportLibrary}>{text.download}</Button> : plan && !targetChanged ?
          <Button variant="contained" color="primary" disabled={busy || !validName} onClick={importLibrary}>{text.confirm_import}</Button> :
          <Button variant="contained" color="primary" disabled={busy || !file} onClick={inspect}>{text.inspect}</Button>}
      </DialogActions>
    </Dialog>}
  </>;
}
