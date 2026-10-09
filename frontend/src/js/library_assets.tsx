import React, { Component, RefObject } from "react";
import { LibraryAssetsAPI, AssetGroup, LibraryAsset, field_info } from "./types";
import { Grid, Button, TextField, Typography } from "@material-ui/core";
import { cloneDeep } from "lodash";
import ActionDialog from "./reusable/action_dialog";
import { update_state, get_field_info_default, get_string_from_error } from "./utils";
import s from "./locales/advanced-tabs.en.json";

interface LibraryAssetsProps { library_assets_api: LibraryAssetsAPI }
interface LibraryAssetsModals {
    add_asset: { is_open: boolean; file: File | null; group: AssetGroup };
    delete_asset: { is_open: boolean; to_delete: LibraryAsset; confirm_filename: field_info<string> };
}
interface LibraryAssetsState { modals: LibraryAssetsModals; busy: boolean; error: string }

export default class LibraryAssets extends Component<LibraryAssetsProps, LibraryAssetsState> {
    modal_defaults: LibraryAssetsModals;
    update_state: (update: (draft: LibraryAssetsState) => void) => Promise<void>;
    file_input_ref: RefObject<HTMLInputElement>;

    constructor(props: LibraryAssetsProps) {
        super(props);
        const asset: LibraryAsset = { id: 0, image_file: null, image_group: 1, file_name: null };
        this.modal_defaults = {
            add_asset: { is_open: false, file: null, group: 1 },
            delete_asset: { is_open: false, to_delete: asset, confirm_filename: get_field_info_default("") },
        };
        this.state = { modals: cloneDeep(this.modal_defaults), busy: false, error: "" };
        this.file_input_ref = React.createRef();
        this.update_state = update_state.bind(this);
        this.close_modals = this.close_modals.bind(this);
    }

    asset_name(asset: LibraryAsset) {
        return asset.file_name || s.assets_unnamed.replace("{id}", String(asset.id));
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

    render() {
        const api = this.props.library_assets_api;
        const modals = this.state.modals;
        const groups: { id: AssetGroup; title: string; add: string }[] = [
            { id: 1, title: s.assets_logos, add: s.assets_add_logo },
            { id: 2, title: s.assets_banners, add: s.assets_add_banner },
        ];
        const deleting = modals.delete_asset;
        const deleteName = this.asset_name(deleting.to_delete);
        const feedback = this.state.error ? <p className="advanced-form-error" role="alert">{this.state.error}</p> : null;
        const cancel = (ref?: React.RefObject<HTMLButtonElement>) => <Button key="cancel" disabled={this.state.busy} onClick={this.close_modals} ref={ref}>{s.cancel}</Button>;
        return <section className="advanced-page">
            <div className="advanced-page-heading"><div><h2>{s.assets_heading}</h2><p>{s.assets_intro}</p></div></div>
            {groups.map(group => {
                const assets = api.state.assets_by_group[group.id] || [];
                return <section key={group.id} className="advanced-asset-group" aria-labelledby={`asset-group-${group.id}`}>
                    <div className="advanced-section-heading">
                        <h3 id={`asset-group-${group.id}`}>{group.title}</h3>
                        <Button variant="outlined" color="primary" onClick={() => this.update_state(draft => {
                            draft.error = "";
                            draft.modals.add_asset.is_open = true;
                            draft.modals.add_asset.group = group.id;
                        })}>{group.add}</Button>
                    </div>
                    {!assets.length ? <p className="advanced-empty">{s.assets_empty.replace("{group}", group.title.toLowerCase())}</p> : <Grid container spacing={3}>
                        {assets.map(asset => {
                            const name = this.asset_name(asset);
                            return <Grid item xs={12} sm={6} md={4} key={asset.id}>
                                <div className="advanced-asset-item">
                                    {asset.image_file ? <a className="advanced-asset-preview" href={asset.image_file} target="_blank" rel="noopener noreferrer" aria-label={s.assets_open_image.replace("{name}", name)}>
                                        <img src={asset.image_file} alt={name} />
                                    </a> : <p className="advanced-empty">{s.assets_missing_image}</p>}
                                    <p className="advanced-asset-name">{name}</p>
                                    <Button variant="outlined" onClick={() => this.update_state(draft => {
                                        draft.error = "";
                                        draft.modals.delete_asset.is_open = true;
                                        draft.modals.delete_asset.to_delete = asset;
                                    })} aria-label={s.assets_delete_image.replace("{name}", name)}>{s.delete}</Button>
                                </div>
                            </Grid>;
                        })}
                    </Grid>}
                </section>;
            })}
            <ActionDialog title={modals.add_asset.group === 1 ? s.assets_add_logo : s.assets_add_banner} open={modals.add_asset.is_open} on_close={this.close_modals}
                get_actions={ref => [cancel(ref), <Button key="upload" color="primary" variant="contained" disabled={this.state.busy} onClick={() => {
                    const file = this.file_input_ref.current?.files?.item(0);
                    if (!file) { this.update_state(draft => { draft.error = s.assets_choose_image; }); return; }
                    this.run_action(() => api.add_library_asset(file, modals.add_asset.group));
                }}>{this.state.busy ? s.saving : s.upload}</Button>]}>
                {feedback}
                <div className="advanced-file-field">
                    <label htmlFor="advanced-asset-file">{s.assets_image_file}</label>
                    <input id="advanced-asset-file" accept="image/*" type="file" ref={this.file_input_ref} disabled={this.state.busy} aria-describedby="advanced-asset-file-help" onChange={() => this.update_state(draft => { draft.error = ""; })} />
                    <p id="advanced-asset-file-help" className="advanced-help">{s.assets_image_help}</p>
                </div>
            </ActionDialog>
            <ActionDialog title={s.assets_delete_title.replace("{name}", deleteName)} open={deleting.is_open} on_close={this.close_modals}
                get_actions={ref => [cancel(ref), <Button key="delete" color="primary" variant="contained" disabled={this.state.busy} onClick={async () => {
                    if (deleting.confirm_filename.value !== deleteName) {
                        await this.update_state(draft => { draft.modals.delete_asset.confirm_filename.reason = s.confirm_mismatch.replace("{name}", deleteName); });
                        return;
                    }
                    this.run_action(() => api.delete_library_asset(deleting.to_delete));
                }}>{this.state.busy ? s.saving : s.delete}</Button>]}>
                <Typography>{s.assets_delete_prompt.replace("{name}", deleteName)}</Typography>
                {feedback}
                <TextField id="advanced-delete-asset-confirm" fullWidth required disabled={this.state.busy} label={deleting.to_delete.file_name ? s.assets_confirm_filename : s.assets_confirm_identity}
                    error={!!deleting.confirm_filename.reason} helperText={deleting.confirm_filename.reason} value={deleting.confirm_filename.value}
                    onChange={event => { const value = event.target.value; this.update_state(draft => { draft.modals.delete_asset.confirm_filename.value = value; draft.modals.delete_asset.confirm_filename.reason = ""; draft.error = ""; }); }} />
            </ActionDialog>
        </section>;
    }
}
