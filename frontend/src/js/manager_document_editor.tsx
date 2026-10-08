import React, { useRef, useState } from "react";
import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from "@material-ui/core";
import Autocomplete from "@material-ui/lab/Autocomplete";
import { SerializedMetadata, SerializedMetadataType } from "./types";
import { CatalogueFolder } from "./catalogue_tree";
import { ManagedDocument, folderPath, originalUrl } from "./manager_api";
import { useManagerStrings } from "./manager_strings";

export interface DocumentDraft {
  title: string;
  display_title: string;
  description: string;
  rights_statement: string;
  copyright_notes: string;
  additional_notes: string;
  published_date: string;
  reviewed_on: string;
  active: boolean;
  duplicatable: boolean;
  metadata: number[];
  folder_ids: number[];
  file: File | null;
}
interface Props {
  document: ManagedDocument | null;
  folders: CatalogueFolder[];
  initialFolder?: number;
  metadata: SerializedMetadata[];
  types: SerializedMetadataType[];
  onClose: () => void;
  onSave: (draft: DocumentDraft) => Promise<void>;
  onCreateType: (name: string) => Promise<SerializedMetadataType>;
  onCreateMetadata: (type: number, name: string) => Promise<SerializedMetadata>;
}
export default function DocumentEditor(props: Props) {
  const s = useManagerStrings();
  const item = props.document;
  const input = useRef<HTMLInputElement>(null);
  const chooseFile = useRef<HTMLButtonElement>(null);
  const [draft, setDraft] = useState<DocumentDraft>({
    title: item?.title || "",
    display_title: item?.display_title || "",
    description: item?.description || "",
    rights_statement: item?.rights_statement || "",
    copyright_notes: item?.copyright_notes || "",
    additional_notes: item?.additional_notes || "",
    published_date: item?.published_date || "",
    reviewed_on: item?.reviewed_on || "",
    active: item?.active ?? true,
    duplicatable: item?.duplicatable ?? false,
    metadata: item?.metadata || [],
    folder_ids: item
      ? item.catalogue_folder_ids || []
      : props.initialFolder
        ? [props.initialFolder]
        : [],
    file: null,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [newType, setNewType] = useState("");
  const [showNewType, setShowNewType] = useState(false);
  const [valueType, setValueType] = useState<number | null>(null);
  const [newValue, setNewValue] = useState("");
  const [metadataBusy, setMetadataBusy] = useState(false);
  const [metadataError, setMetadataError] = useState("");
  const locked = busy || metadataBusy;
  function field<K extends keyof DocumentDraft>(
    key: K,
    value: DocumentDraft[K],
  ) {
    setDraft((current) => ({ ...current, [key]: value }));
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    if (!item && !draft.file) {
      setError(s("file_required"));
      chooseFile.current?.focus();
      return;
    }
    setBusy(true);
    try {
      await props.onSave(draft);
    } catch (failure) {
      setError(
        `${s("operation_error")} ${failure instanceof Error ? failure.message : ""}`,
      );
      setBusy(false);
    }
  }
  async function addType() {
    setMetadataBusy(true);
    setMetadataError("");
    try {
      const type = await props.onCreateType(newType.trim());
      setValueType(type.id);
      setNewType("");
      setShowNewType(false);
    } catch (failure) {
      setMetadataError(
        `${s("metadata_error")} ${failure instanceof Error ? failure.message : ""}`,
      );
    } finally {
      setMetadataBusy(false);
    }
  }
  async function addValue() {
    if (valueType === null) return;
    setMetadataBusy(true);
    setMetadataError("");
    try {
      const value = await props.onCreateMetadata(valueType, newValue.trim());
      setDraft((current) => ({
        ...current,
        metadata: Array.from(new Set([...current.metadata, value.id])),
      }));
      setValueType(null);
      setNewValue("");
    } catch (failure) {
      setMetadataError(
        `${s("metadata_error")} ${failure instanceof Error ? failure.message : ""}`,
      );
    } finally {
      setMetadataBusy(false);
    }
  }
  return (
    <Dialog
      open
      onClose={() => {
        if (!locked) props.onClose();
      }}
      fullWidth
      maxWidth="md"
      aria-labelledby="manager-editor-title"
      className="manager-dialog"
    >
      <DialogTitle id="manager-editor-title">
        {item ? s("edit_title") : s("upload_title")}
      </DialogTitle>
      <DialogContent>
        <form
          id="manager-document-form"
          className="manager-form"
          onSubmit={save}
        >
          {item && <p className="manager-help">{s("edit_scope")}</p>}
          {error && (
            <p className="manager-error" role="alert">
              {error}
            </p>
          )}
          <fieldset disabled={locked} className="manager-fieldset">
            <legend>{s("file")}</legend>
            <div className="manager-file-box">
              <div>
                <strong>
                  {draft.file?.name || item?.file_name || s("no_file")}
                </strong>
                {item && originalUrl(item) && (
                  <a href={originalUrl(item)} target="_blank" rel="noopener">
                    {s("original")} ↗
                  </a>
                )}
                <p>{item ? s("replacement_help") : s("file_help")}</p>
              </div>
              <button
                ref={chooseFile}
                type="button"
                className="manager-button"
                onClick={() => input.current?.click()}
              >
                {item ? s("replace_file") : s("choose_file")}
              </button>
              <input
                ref={input}
                type="file"
                tabIndex={-1}
                className="manager-file-input"
                aria-label={s("file")}
                onChange={(event) => {
                  const file = event.target.files?.[0] || null;
                  setDraft((current) => ({
                    ...current,
                    file,
                    title:
                      current.title || file?.name.replace(/\.[^.]+$/, "") || "",
                  }));
                }}
              />
            </div>
            <div className="manager-form-grid">
              <label className="manager-field">
                {s("title")}
                <input
                  autoFocus
                  required
                  maxLength={300}
                  value={draft.title}
                  onChange={(event) => field("title", event.target.value)}
                />
              </label>
              <label className="manager-field">
                {s("display_title")}
                <input
                  maxLength={300}
                  value={draft.display_title}
                  placeholder={draft.title}
                  onChange={(event) =>
                    field("display_title", event.target.value)
                  }
                />
              </label>
            </div>
            <label className="manager-field">
              {s("description")}
              <textarea
                rows={3}
                value={draft.description}
                onChange={(event) => field("description", event.target.value)}
              />
            </label>
            <div className="manager-form-grid">
              <label className="manager-field">
                {s("rights")}
                <textarea
                  rows={3}
                  value={draft.rights_statement}
                  onChange={(event) =>
                    field("rights_statement", event.target.value)
                  }
                />
                <span className="manager-help">{s("rights_help")}</span>
              </label>
              <label className="manager-field">
                {s("copyright")}
                <textarea
                  rows={3}
                  value={draft.copyright_notes}
                  onChange={(event) =>
                    field("copyright_notes", event.target.value)
                  }
                />
              </label>
            </div>
            <label className="manager-field">
              {s("notes")}
              <textarea
                rows={2}
                value={draft.additional_notes}
                onChange={(event) =>
                  field("additional_notes", event.target.value)
                }
              />
            </label>
          </fieldset>
          <fieldset
            disabled={locked}
            className="manager-fieldset manager-form-section"
          >
            <legend>{s("membership")}</legend>
            <p className="manager-help">{s("membership_help")}</p>
            {props.folders.length ? (
              <div className="manager-membership-list">
                {props.folders
                  .slice()
                  .sort((a, b) =>
                    folderPath(a, props.folders).localeCompare(
                      folderPath(b, props.folders),
                    ),
                  )
                  .map((folder) => (
                    <label key={folder.id} className="manager-checkbox">
                      <input
                        type="checkbox"
                        checked={draft.folder_ids.includes(folder.id)}
                        onChange={(event) =>
                          field(
                            "folder_ids",
                            event.target.checked
                              ? [...draft.folder_ids, folder.id]
                              : draft.folder_ids.filter(
                                  (id) => id !== folder.id,
                                ),
                          )
                        }
                      />
                      <span>{folderPath(folder, props.folders)}</span>
                    </label>
                  ))}
              </div>
            ) : (
              <p>{s("no_membership_help")}</p>
            )}
          </fieldset>
          <section
            className="manager-form-section"
            aria-labelledby="manager-metadata-heading"
          >
            <h3 id="manager-metadata-heading">{s("metadata")}</h3>
            <p className="manager-help">{s("metadata_help")}</p>
            {metadataError && (
              <p className="manager-error" role="alert">
                {metadataError}
              </p>
            )}
            {!props.types.length && (
              <p className="manager-help">{s("no_metadata_types")}</p>
            )}
            <div className="manager-metadata-grid">
              {props.types.map((type) => {
                const options = props.metadata
                  .filter((value) => value.type === type.id)
                  .sort((a, b) => a.name.localeCompare(b.name));
                const values = options.filter((value) =>
                  draft.metadata.includes(value.id),
                );
                return (
                  <div className="manager-metadata-field" key={type.id}>
                    <Autocomplete
                      multiple
                      disabled={locked}
                      options={options}
                      value={values}
                      getOptionLabel={(value) => value.name}
                      getOptionSelected={(a, b) => a.id === b.id}
                      renderTags={() => null}
                      noOptionsText={s("no_options")}
                      openText={s("open_options")}
                      closeText={s("close_options")}
                      clearText={s("clear_values")}
                      onChange={(_event, selected) =>
                        field("metadata", [
                          ...draft.metadata.filter(
                            (id) => !options.some((option) => option.id === id),
                          ),
                          ...selected.map((value) => value.id),
                        ])
                      }
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          label={type.name}
                          variant="outlined"
                        />
                      )}
                    />
                    {values.length > 0 && (
                      <div className="manager-metadata-values">
                        {values.map((value) => (
                          <button
                            key={value.id}
                            type="button"
                            disabled={locked}
                            aria-label={s("remove_value", { name: value.name })}
                            onClick={() =>
                              field(
                                "metadata",
                                draft.metadata.filter((id) => id !== value.id),
                              )
                            }
                          >
                            {value.name}
                            <span aria-hidden="true">×</span>
                          </button>
                        ))}
                      </div>
                    )}
                    {valueType === type.id ? (
                      <div className="manager-inline-form">
                        <label className="manager-field">
                          {s("new_value", { name: type.name })}
                          <input
                            value={newValue}
                            maxLength={500}
                            disabled={locked}
                            autoFocus
                            onChange={(event) =>
                              setNewValue(event.target.value)
                            }
                          />
                        </label>
                        <div className="manager-inline-actions">
                          <button
                            type="button"
                            className="manager-button"
                            disabled={locked || !newValue.trim()}
                            onClick={addValue}
                          >
                            {metadataBusy ? s("saving") : s("add_value")}
                          </button>
                          <button
                            type="button"
                            className="manager-text-button"
                            disabled={locked}
                            onClick={() => {
                              setValueType(null);
                              setNewValue("");
                            }}
                          >
                            {s("cancel")}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="manager-text-button"
                        disabled={locked}
                        onClick={() => {
                          setValueType(type.id);
                          setNewValue("");
                        }}
                      >
                        {s("add_value")}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
            {showNewType ? (
              <div className="manager-inline-form">
                <label className="manager-field">
                  {s("field_name")}
                  <input
                    autoFocus
                    maxLength={100}
                    value={newType}
                    disabled={locked}
                    onChange={(event) => setNewType(event.target.value)}
                  />
                  <span className="manager-help">{s("field_help")}</span>
                </label>
                <div className="manager-inline-actions">
                  <button
                    className="manager-button"
                    type="button"
                    disabled={locked || !newType.trim()}
                    onClick={addType}
                  >
                    {metadataBusy ? s("saving") : s("create_field")}
                  </button>
                  <button
                    type="button"
                    className="manager-text-button"
                    disabled={locked}
                    onClick={() => setShowNewType(false)}
                  >
                    {s("cancel")}
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                className="manager-text-button"
                disabled={locked}
                onClick={() => setShowNewType(true)}
              >
                + {s("add_field")}
              </button>
            )}
          </section>
          <details className="manager-additional">
            <summary>{s("other_details")}</summary>
            <fieldset disabled={locked} className="manager-fieldset">
              <div className="manager-form-grid">
                <label className="manager-field">
                  {s("published_date")}
                  <input
                    type="date"
                    value={draft.published_date}
                    onChange={(event) =>
                      field("published_date", event.target.value)
                    }
                  />
                </label>
                <label className="manager-field">
                  {s("review_date")}
                  <input
                    type="date"
                    value={draft.reviewed_on}
                    onChange={(event) =>
                      field("reviewed_on", event.target.value)
                    }
                  />
                  <span className="manager-help">{s("date_help")}</span>
                </label>
              </div>
              <label className="manager-checkbox">
                <input
                  type="checkbox"
                  checked={draft.active}
                  onChange={(event) => field("active", event.target.checked)}
                />
                <span>
                  {s("active")}
                  <small>{s("active_help")}</small>
                </span>
              </label>
              <label className="manager-checkbox">
                <input
                  type="checkbox"
                  checked={draft.duplicatable}
                  onChange={(event) =>
                    field("duplicatable", event.target.checked)
                  }
                />
                <span>
                  {s("duplicatable")}
                  <small>{s("duplicatable_help")}</small>
                </span>
              </label>
            </fieldset>
          </details>
        </form>
      </DialogContent>
      <DialogActions>
        <button
          className="manager-button"
          type="button"
          disabled={locked}
          onClick={props.onClose}
        >
          {s("cancel")}
        </button>
        <button
          className="manager-button manager-button-primary"
          type="submit"
          form="manager-document-form"
          disabled={locked}
        >
          {busy ? s("saving") : item ? s("save") : s("upload")}
        </button>
      </DialogActions>
    </Dialog>
  );
}
