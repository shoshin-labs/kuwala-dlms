import React, { RefObject } from "react";
import { Button, Grid, Link, TextField, Typography } from "@material-ui/core";
import { field_info, LibraryAssetsAPI, LibraryAsset, LibraryModule, LibraryModulesAPI } from "./types";
import ActionPanel from "./reusable/action_panel";
import { get_field_info_default, get_string_from_error, update_state } from "./utils";
import { cloneDeep } from "lodash";
import ActionDialog from "./reusable/action_dialog";
import { APP_URLS } from "./urls";
import s from "./locales/advanced-tabs.en.json";

interface LibraryModulesProps {
    library_modules_api: LibraryModulesAPI;
    library_assets_api: LibraryAssetsAPI;
}
interface LibraryModulesModals {
    set_logo_image: { is_open: boolean; to_change: LibraryModule };
    add_module: { is_open: boolean; module_name: field_info<string> };
    edit_module: { is_open: boolean; to_change: LibraryModule; module_name: field_info<string> };
    delete_module: { is_open: boolean; module_name: field_info<string>; to_delete: LibraryModule };
}
interface LibraryModulesState { modals: LibraryModulesModals; busy: boolean; error: string }

export default class LibraryModules extends React.Component<LibraryModulesProps, LibraryModulesState> {
    update_state: (update: (draft: LibraryModulesState) => void) => Promise<void>;
    add_module_file_ref: RefObject<HTMLInputElement>;
    edit_module_file_ref: RefObject<HTMLInputElement>;
    modal_defaults: LibraryModulesModals;

    constructor(props: LibraryModulesProps) {
        super(props);
        this.add_module_file_ref = React.createRef();
        this.edit_module_file_ref = React.createRef();
        const module: LibraryModule = { id: 0, logo_img: 0, module_file: "", module_name: "", file_name: "" };
        this.modal_defaults = {
            set_logo_image: { is_open: false, to_change: module },
            add_module: { is_open: false, module_name: get_field_info_default("") },
            edit_module: { is_open: false, module_name: get_field_info_default(""), to_change: module },
            delete_module: { is_open: false, module_name: get_field_info_default(""), to_delete: module },
        };
        this.state = { modals: cloneDeep(this.modal_defaults), busy: false, error: "" };
        this.update_state = update_state.bind(this);
        this.close_modals = this.close_modals.bind(this);
    }

    close_modals() {
        if (this.state.busy) return;
        return this.update_state(draft => { draft.modals = cloneDeep(this.modal_defaults); draft.error = ""; });
    }

    async run_action(action: () => Promise<any>) {
        if (this.state.busy) return;
        await this.update_state(draft => { draft.busy = true; draft.error = ""; });
        try {
            await action();
            await this.update_state(draft => { draft.modals = cloneDeep(this.modal_defaults); });
        } catch (error) {
            await this.update_state(draft => { draft.error = get_string_from_error(error?.response?.data?.error || error?.data?.error || error, s.request_failed); });
        } finally {
            await this.update_state(draft => { draft.busy = false; });
        }
    }

    name_error(name: string) {
        return !name.trim() ? s.required_name : name.trim().length > 300 ? s.name_too_long.replace("{limit}", "300") : "";
    }

    logo_name(asset: LibraryAsset) {
        return asset.file_name || s.assets_unnamed.replace("{id}", String(asset.id));
    }

    render() {
        const api = this.props.library_modules_api;
        const modals = this.state.modals;
        const adding = modals.add_module;
        const editing = modals.edit_module;
        const deleting = modals.delete_module;
        const logos = (this.props.library_assets_api.state.assets_by_group[1] || []).filter(asset => !!asset.image_file);
        const feedback = this.state.error ? <p className="advanced-form-error" role="alert">{this.state.error}</p> : null;
        const cancel = (ref?: React.RefObject<HTMLButtonElement>) => <Button key="cancel" disabled={this.state.busy} onClick={this.close_modals} ref={ref}>{s.cancel}</Button>;
        const submit = (label: string, action: () => void) => <Button key="submit" variant="contained" color="primary" disabled={this.state.busy} onClick={action}>{this.state.busy ? s.saving : label}</Button>;
        const nameField = (modal: "add_module" | "edit_module") => <TextField id={modal === "add_module" ? "advanced-add-module-name" : "advanced-edit-module-name"} fullWidth required disabled={this.state.busy} label={s.modules_name}
            inputProps={{ maxLength: 300 }} error={!!modals[modal].module_name.reason} helperText={modals[modal].module_name.reason} value={modals[modal].module_name.value}
            onChange={event => { const value = event.target.value; this.update_state(draft => { draft.modals[modal].module_name.value = value; draft.modals[modal].module_name.reason = ""; draft.error = ""; }); }} />;
        return <section className="advanced-page">
            <div className="advanced-page-heading">
                <div><h2>{s.modules_heading}</h2><p>{s.modules_intro}</p></div>
                <Button variant="contained" color="primary" onClick={() => this.update_state(draft => { draft.error = ""; draft.modals.add_module.is_open = true; })}>{s.modules_add}</Button>
            </div>
            {!api.state.library_modules.length ? <div className="advanced-empty"><p>{s.modules_empty}</p><p>{s.modules_empty_help}</p></div> : <ul className="advanced-entry-list">
                {api.state.library_modules.map(row => <li key={row.id} className="advanced-entry-list-item">
                    <div className="advanced-entry-description">
                        <h3>{row.module_name}</h3>
                        <dl className="advanced-entry-details"><div><dt>{s.filename}</dt><dd>
                            {row.file_name ? <Link target="_blank" rel="noopener noreferrer" href={new URL(row.file_name, APP_URLS.MODULE_FOLDER).href} aria-label={s.modules_open_file.replace("{name}", row.module_name)}>{row.file_name}</Link> : s.modules_file_missing}
                        </dd></div></dl>
                    </div>
                    <div className="advanced-entry-actions"><ActionPanel
                        imageHint={s.modules_set_logo}
                        imageFn={() => this.update_state(draft => { draft.error = ""; draft.modals.set_logo_image.is_open = true; draft.modals.set_logo_image.to_change = row; })}
                        editHint={s.modules_edit}
                        editFn={() => this.update_state(draft => { draft.error = ""; draft.modals.edit_module.is_open = true; draft.modals.edit_module.to_change = row; draft.modals.edit_module.module_name.value = row.module_name; })}
                        deleteHint={s.modules_delete}
                        deleteFn={() => this.update_state(draft => { draft.error = ""; draft.modals.delete_module.is_open = true; draft.modals.delete_module.to_delete = row; })}
                    /></div>
                </li>)}
            </ul>}
            <ActionDialog title={s.modules_set_logo} open={modals.set_logo_image.is_open} on_close={this.close_modals} get_actions={ref => [cancel(ref)]}>
                {feedback}
                {!logos.length ? <p className="advanced-empty">{s.modules_logos_empty}</p> : <Grid container spacing={2}>
                    {logos.map(asset => {
                        const name = this.logo_name(asset);
                        const selected = modals.set_logo_image.to_change.logo_img === asset.id;
                        return <Grid item xs={12} sm={6} md={4} key={asset.id}>
                            <button type="button" className="advanced-image-choice" disabled={this.state.busy} aria-pressed={selected}
                                aria-label={s.modules_use_logo.replace("{name}", name)} onClick={() => this.run_action(() => api.set_module_logo(modals.set_logo_image.to_change, asset))}>
                                <img src={asset.image_file || undefined} alt="" />
                                <span>{name}</span>
                                {selected && <strong>{s.modules_logo_selected}</strong>}
                            </button>
                        </Grid>;
                    })}
                </Grid>}
            </ActionDialog>
            <ActionDialog title={s.modules_add} open={adding.is_open} on_close={this.close_modals} get_actions={ref => [cancel(ref), submit(s.modules_add, () => {
                const reason = this.name_error(adding.module_name.value);
                if (reason) { this.update_state(draft => { draft.modals.add_module.module_name.reason = reason; }); return; }
                const file = this.add_module_file_ref.current?.files?.item(0);
                if (!file || !/\.zip$/i.test(file.name)) { this.update_state(draft => { draft.error = s.modules_choose_zip; }); return; }
                this.run_action(() => api.add_module(adding.module_name.value.trim(), file));
            })]}>
                {feedback}
                {nameField("add_module")}
                <div className="advanced-file-field">
                    <label htmlFor="advanced-add-module-file">{s.modules_zip_file}</label>
                    <input id="advanced-add-module-file" type="file" accept=".zip,application/zip,application/x-zip-compressed" ref={this.add_module_file_ref} disabled={this.state.busy}
                        aria-describedby="advanced-add-module-file-help" onChange={() => this.update_state(draft => { draft.error = ""; })} />
                    <p id="advanced-add-module-file-help" className="advanced-help">{s.modules_zip_help}</p>
                </div>
            </ActionDialog>
            <ActionDialog title={s.modules_edit} open={editing.is_open} on_close={this.close_modals} get_actions={ref => [cancel(ref), submit(s.save, () => {
                const reason = this.name_error(editing.module_name.value);
                if (reason) { this.update_state(draft => { draft.modals.edit_module.module_name.reason = reason; }); return; }
                const file = this.edit_module_file_ref.current?.files?.item(0);
                if (file && !/\.zip$/i.test(file.name)) { this.update_state(draft => { draft.error = s.modules_zip_only; }); return; }
                this.run_action(() => api.edit_module(editing.to_change, editing.module_name.value.trim(), file));
            })]}>
                {feedback}
                {nameField("edit_module")}
                <div className="advanced-file-field">
                    <label htmlFor="advanced-edit-module-file">{s.modules_replace_file}</label>
                    <input id="advanced-edit-module-file" type="file" accept=".zip,application/zip,application/x-zip-compressed" ref={this.edit_module_file_ref} disabled={this.state.busy}
                        aria-describedby="advanced-edit-module-file-help" onChange={() => this.update_state(draft => { draft.error = ""; })} />
                    <p id="advanced-edit-module-file-help" className="advanced-help">{s.modules_replace_help}</p>
                </div>
            </ActionDialog>
            <ActionDialog title={s.modules_delete} open={deleting.is_open} on_close={this.close_modals} get_actions={ref => [cancel(ref), submit(s.delete, () => {
                if (deleting.module_name.value !== deleting.to_delete.module_name) {
                    this.update_state(draft => { draft.modals.delete_module.module_name.reason = s.confirm_mismatch.replace("{name}", deleting.to_delete.module_name); });
                    return;
                }
                this.run_action(() => api.delete_module(deleting.to_delete));
            })]}>
                <Typography>{s.modules_delete_prompt.replace("{name}", deleting.to_delete.module_name)}</Typography>
                {feedback}
                <TextField id="advanced-delete-module-confirm" fullWidth required disabled={this.state.busy} label={s.confirm_name} value={deleting.module_name.value} error={!!deleting.module_name.reason} helperText={deleting.module_name.reason}
                    onChange={event => { const value = event.target.value; this.update_state(draft => { draft.modals.delete_module.module_name.value = value; draft.modals.delete_module.module_name.reason = ""; draft.error = ""; }); }} />
            </ActionDialog>
        </section>;
    }
}
