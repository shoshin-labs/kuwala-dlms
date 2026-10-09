import React from "react";
import { Button, TextField, Typography } from "@material-ui/core";
import { field_info, LibraryVersion, LibraryVersionsAPI } from "./types";
import ActionPanel from "./reusable/action_panel";
import { get_field_info_default, get_string_from_error, update_state } from "./utils";
import { cloneDeep } from "lodash";
import ActionDialog from "./reusable/action_dialog";
import s from "./locales/advanced-tabs.en.json";

interface LibraryImagesModal {
    build_version: { is_open: boolean; to_build: LibraryVersion; name: field_info<string> };
}
interface LibraryImagesState { modals: LibraryImagesModal; busy: boolean; error: string }
interface LibraryImagesProps {
    library_versions_api: LibraryVersionsAPI;
    show_toast_message: (message: string, is_success: boolean) => void;
}

export default class LibraryImages extends React.Component<LibraryImagesProps, LibraryImagesState> {
    modal_defaults: LibraryImagesModal;
    update_state: (update: (draft: LibraryImagesState) => void) => Promise<void>;

    constructor(props: LibraryImagesProps) {
        super(props);
        const version: LibraryVersion = { id: 0, library_name: "", version_number: "", library_banner: 0, created_by: 0, metadata_types: [] };
        this.modal_defaults = { build_version: { is_open: false, to_build: version, name: get_field_info_default("") } };
        this.state = { modals: cloneDeep(this.modal_defaults), busy: false, error: "" };
        this.update_state = update_state.bind(this);
        this.close_modals = this.close_modals.bind(this);
    }

    close_modals() {
        if (this.state.busy) return;
        return this.update_state(draft => { draft.modals = cloneDeep(this.modal_defaults); draft.error = ""; });
    }

    async create_export() {
        if (this.state.busy) return;
        const modal = this.state.modals.build_version;
        if (modal.name.value !== modal.to_build.library_name) {
            await this.update_state(draft => { draft.modals.build_version.name.reason = s.confirm_mismatch.replace("{name}", modal.to_build.library_name); });
            return;
        }
        await this.update_state(draft => { draft.busy = true; draft.error = ""; });
        try {
            await this.props.library_versions_api.build_version(modal.to_build);
            this.props.show_toast_message(s.exports_success, true);
            await this.update_state(draft => { draft.modals = cloneDeep(this.modal_defaults); });
        } catch (error) {
            await this.update_state(draft => { draft.error = get_string_from_error(error?.response?.data?.error || error?.data?.error || error, s.exports_failed); });
        } finally {
            await this.update_state(draft => { draft.busy = false; });
        }
    }

    async change_page(page: number) {
        if (this.state.busy) return;
        await this.update_state(draft => { draft.busy = true; draft.error = ""; });
        try {
            await this.props.library_versions_api.set_page(page);
        } catch (error) {
            await this.update_state(draft => { draft.error = get_string_from_error(error?.response?.data?.error || error?.data?.error || error, s.exports_page_failed); });
        } finally {
            await this.update_state(draft => { draft.busy = false; });
        }
    }

    render() {
        const api = this.props.library_versions_api;
        const versions = api.state.library_versions;
        const pageCount = Math.ceil(api.state.library_versions_count / api.state.library_versions_page_size);
        const modal = this.state.modals.build_version;
        return <section className="advanced-page">
            <div className="advanced-page-heading"><div><h2>{s.exports_heading}</h2><p>{s.exports_intro}</p></div></div>
            {!modal.is_open && this.state.error && <p className="advanced-form-error" role="alert">{this.state.error}</p>}
            {!versions.length ? <div className="advanced-empty"><p>{s.exports_empty}</p><p>{s.exports_empty_help}</p></div> : <ul className="advanced-entry-list">
                {versions.map(row => <li key={row.id} className="advanced-entry-list-item">
                    <div className="advanced-entry-description">
                        <h3>{row.library_name}</h3>
                        <dl className="advanced-entry-details"><div><dt>{s.exports_version}</dt><dd>{row.version_number}</dd></div></dl>
                    </div>
                    <div className="advanced-entry-actions"><ActionPanel
                        downloadHint={s.exports_create}
                        downloadFn={() => this.update_state(draft => { draft.error = ""; draft.modals.build_version.is_open = true; draft.modals.build_version.to_build = row; })}
                    /></div>
                </li>)}
            </ul>}
            {pageCount > 1 && <nav className="versions-pagination" aria-label={s.exports_pages}>
                <Button variant="outlined" disabled={this.state.busy || api.state.library_versions_page <= 0} onClick={() => this.change_page(api.state.library_versions_page - 1)}>{s.previous}</Button>
                <span>{s.page.replace("{page}", String(api.state.library_versions_page + 1)).replace("{total}", String(pageCount))}</span>
                <Button variant="outlined" disabled={this.state.busy || api.state.library_versions_page + 1 >= pageCount} onClick={() => this.change_page(api.state.library_versions_page + 1)}>{s.next}</Button>
            </nav>}
            <ActionDialog title={s.exports_title.replace("{name}", modal.to_build.library_name)} open={modal.is_open} on_close={this.close_modals}
                get_actions={ref => [
                    <Button key="cancel" onClick={this.close_modals} disabled={this.state.busy} ref={ref}>{s.cancel}</Button>,
                    <Button key="export" variant="contained" color="primary" disabled={this.state.busy} onClick={() => this.create_export()}>{this.state.busy ? s.creating : s.exports_create}</Button>,
                ]}>
                <Typography>{s.exports_prompt.replace("{name}", modal.to_build.library_name)}</Typography>
                {this.state.error && <p className="advanced-form-error" role="alert">{this.state.error}</p>}
                <TextField id="advanced-export-catalogue-confirm" fullWidth required disabled={this.state.busy} label={s.exports_confirm_name} error={!!modal.name.reason} helperText={modal.name.reason} value={modal.name.value}
                    onChange={event => { const value = event.target.value; this.update_state(draft => { draft.modals.build_version.name.value = value; draft.modals.build_version.name.reason = ""; draft.error = ""; }); }} />
            </ActionDialog>
        </section>;
    }
}
