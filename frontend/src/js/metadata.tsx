import React, { Component } from "react";
import { Button, TextField, Typography, ExpansionPanel, ExpansionPanelSummary, ExpansionPanelDetails } from "@material-ui/core";
import ExpandMore from "@material-ui/icons/ExpandMore";
import { cloneDeep, isEqual } from "lodash";
import { FilteringState, PagingState, CustomPaging } from "@devexpress/dx-react-grid";
import { Grid as DataGrid, PagingPanel, Table, TableHeaderRow, TableFilterRow } from "@devexpress/dx-react-grid-material-ui";
import ActionPanel from "./reusable/action_panel";
import ActionDialog from "./reusable/action_dialog";
import KebabMenu from "./reusable/kebab_menu";
import { update_state, get_field_info_default, get_string_from_error } from "./utils";
import { MetadataAPI, SerializedMetadataType, SerializedMetadata, field_info } from "./types";
import { APP_URLS } from "./urls";
import s from "./locales/advanced-tabs.en.json";

interface MetadataProps {
    metadata_api: MetadataAPI;
    show_toast_message: (message: string, is_success: boolean) => void;
}
interface MetadataModals {
    create_type: { is_open: boolean; type_name: string };
    edit_type: { is_open: boolean; old_type: SerializedMetadataType; new_name: string };
    create_meta: { is_open: boolean; meta_type: SerializedMetadataType; meta_name: string };
    delete_meta: { is_open: boolean; metadata: SerializedMetadata };
    edit_meta: { is_open: boolean; metadata: SerializedMetadata; new_name: string };
    delete_type: { is_open: boolean; meta_type: SerializedMetadataType; confirm_text: field_info<string> };
}
interface MetadataState {
    panel_data: { [id: string]: boolean };
    modals: MetadataModals;
    error: string;
    busy: boolean;
}

export default class Metadata extends Component<MetadataProps, MetadataState> {
    modal_defaults: MetadataModals;
    update_state: (update: (draft: MetadataState) => void) => Promise<void>;

    constructor(props: MetadataProps) {
        super(props);
        const type: SerializedMetadataType = { id: 0, name: "" };
        const metadata: SerializedMetadata = { id: 0, name: "", type: 0, type_name: "" };
        this.modal_defaults = {
            create_type: { is_open: false, type_name: "" },
            edit_type: { is_open: false, old_type: type, new_name: "" },
            create_meta: { is_open: false, meta_type: type, meta_name: "" },
            delete_meta: { is_open: false, metadata },
            edit_meta: { is_open: false, metadata, new_name: "" },
            delete_type: { is_open: false, meta_type: type, confirm_text: get_field_info_default("") },
        };
        this.state = { panel_data: {}, modals: cloneDeep(this.modal_defaults), error: "", busy: false };
        this.update_state = update_state.bind(this);
        this.close_modals = this.close_modals.bind(this);
    }

    componentDidUpdate(previous: MetadataProps) {
        if (!isEqual(previous.metadata_api.state.metadata_types, this.props.metadata_api.state.metadata_types)) {
            this.update_state(draft => {
                const panels: { [id: string]: boolean } = {};
                this.props.metadata_api.state.metadata_types.forEach(type => { panels[type.id] = !!draft.panel_data[type.id]; });
                draft.panel_data = panels;
            });
        }
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
            await this.update_state(draft => { draft.modals = cloneDeep(this.modal_defaults); draft.error = ""; });
        } catch (error) {
            await this.update_state(draft => { draft.error = get_string_from_error(error?.response?.data?.error || error?.data?.error || error, s.request_failed); });
        } finally {
            await this.update_state(draft => { draft.busy = false; });
        }
    }

    valid_name(name: string, limit: number) {
        const error = !name.trim() ? s.required_name : name.trim().length > limit ? s.name_too_long.replace("{limit}", String(limit)) : "";
        if (error) this.update_state(draft => { draft.error = error; });
        return !error;
    }

    render() {
        const api = this.props.metadata_api;
        const modals = this.state.modals;
        const modalOpen = Object.values(modals).some(modal => modal.is_open);
        const feedback = this.state.error ? <p className="advanced-form-error" role="alert">{this.state.error}</p> : null;
        const cancel = (ref?: React.RefObject<HTMLButtonElement>) => <Button key="cancel" disabled={this.state.busy} onClick={this.close_modals} ref={ref}>{s.cancel}</Button>;
        const primary = (label: string, action: () => void) => <Button key="submit" color="primary" variant="contained" disabled={this.state.busy} onClick={action}>{this.state.busy ? s.saving : label}</Button>;
        return <section className="advanced-page">
            <div className="advanced-page-heading">
                <div><h2>{s.metadata_heading}</h2><p>{s.metadata_intro}</p></div>
                <Button variant="contained" color="primary" onClick={() => this.update_state(draft => { draft.error = ""; draft.modals.create_type.is_open = true; })}>{s.metadata_new_type}</Button>
            </div>
            {!modalOpen && feedback}
            {api.state.metadata_types.length === 0 ? <div className="advanced-empty"><p>{s.metadata_empty}</p><p>{s.metadata_empty_help}</p></div> :
                api.state.metadata_types.map(type => {
                    const rows = api.state.autocomplete_metadata[type.name] || [];
                    const page = api.state.page_by_type[type.name];
                    return <ExpansionPanel key={type.id} className="advanced-metadata-group" expanded={!!this.state.panel_data[type.id]} onChange={(_, expanded) => this.update_state(draft => { draft.panel_data[type.id] = expanded; })}>
                        <ExpansionPanelSummary expandIcon={<ExpandMore />} aria-controls={`metadata-values-${type.id}`} id={`metadata-type-${type.id}`}>
                            <Typography component="h3">{type.name}</Typography>
                        </ExpansionPanelSummary>
                        <ExpansionPanelDetails className="advanced-metadata-details" id={`metadata-values-${type.id}`}>
                            <div className="advanced-section-heading">
                                <Button variant="outlined" color="primary" onClick={() => this.update_state(draft => { draft.error = ""; draft.modals.create_meta.meta_type = type; draft.modals.create_meta.is_open = true; })}>{s.metadata_add_value}</Button>
                                <KebabMenu items={[
                                    [() => this.update_state(draft => { draft.error = ""; draft.modals.edit_type.old_type = type; draft.modals.edit_type.new_name = type.name; draft.modals.edit_type.is_open = true; }), s.metadata_rename_type],
                                    [() => this.update_state(draft => { draft.error = ""; draft.modals.delete_type.meta_type = type; draft.modals.delete_type.is_open = true; }), s.metadata_delete_type],
                                    [() => { window.open(APP_URLS.METADATA_SHEET(type.name), "_blank", "noopener,noreferrer"); }, s.metadata_spreadsheet],
                                ]} />
                            </div>
                            <div className="advanced-table">
                                <DataGrid rows={rows} columns={[
                                    { name: "name", title: s.metadata_value },
                                    { name: "actions", title: s.actions, getCellValue: (row: SerializedMetadata) => <ActionPanel
                                        editHint={s.metadata_edit_value_title.replace("{name}", row.name)}
                                        deleteHint={s.metadata_delete_value_title.replace("{name}", row.name)}
                                        editFn={() => this.update_state(draft => { draft.error = ""; draft.modals.edit_meta.metadata = row; draft.modals.edit_meta.new_name = row.name; draft.modals.edit_meta.is_open = true; })}
                                        deleteFn={() => this.update_state(draft => { draft.error = ""; draft.modals.delete_meta.metadata = row; draft.modals.delete_meta.is_open = true; })} /> },
                                ]}>
                                    <FilteringState columnExtensions={[{columnName: "actions", filteringEnabled: false}]} onFiltersChange={filters => {
                                        api.update_autocomplete(type, filters.find(filter => filter.columnName === "name")?.value || "")
                                            .catch(error => this.update_state(draft => { draft.error = get_string_from_error(error?.response?.data?.error || error?.data?.error || error, s.request_failed); }));
                                    }} />
                                    <PagingState currentPage={(page?.page || 1) - 1} pageSize={page?.page_size || 10}
                                        onCurrentPageChange={next => api.set_metadata_page(next + 1, type.name).catch(error => this.update_state(draft => { draft.error = get_string_from_error(error?.response?.data?.error || error?.data?.error || error, s.request_failed); }))}
                                        onPageSizeChange={size => api.set_metadata_page_size(size, type.name).catch(error => this.update_state(draft => { draft.error = get_string_from_error(error?.response?.data?.error || error?.data?.error || error, s.request_failed); }))} />
                                    <CustomPaging totalCount={page?.count || 0} />
                                    <Table columnExtensions={[{columnName: "actions", width: 160}]} messages={{noData: s.metadata_values_empty}} />
                                    <TableHeaderRow />
                                    <TableFilterRow messages={{filterPlaceholder: s.metadata_filter}} editorComponent={props => props.disabled ? null : <TableFilterRow.Editor {...props} inputProps={{"aria-label": s.metadata_filter}} />} />
                                    {(page?.count || 0) > (page?.page_size || 10) && <PagingPanel pageSizes={[10, 25, 50]} messages={{rowsPerPage: s.metadata_rows_per_page}} />}
                                </DataGrid>
                            </div>
                        </ExpansionPanelDetails>
                    </ExpansionPanel>;
                })}
            <ActionDialog title={s.metadata_create_type_title} open={modals.create_type.is_open} on_close={this.close_modals} get_actions={ref => [cancel(ref), primary(s.create, () => {
                if (this.valid_name(this.state.modals.create_type.type_name, 100)) this.run_action(() => api.add_metadata_type(this.state.modals.create_type.type_name.trim()));
            })]}>
                {feedback}<TextField id="advanced-metadata-create-type-name" fullWidth required disabled={this.state.busy} label={s.metadata_type_name} value={modals.create_type.type_name} inputProps={{maxLength: 100}} onChange={event => { const value = event.target.value; this.update_state(draft => { draft.modals.create_type.type_name = value; draft.error = ""; }); }} />
            </ActionDialog>
            <ActionDialog title={s.metadata_create_value_title.replace("{name}", modals.create_meta.meta_type.name)} open={modals.create_meta.is_open} on_close={this.close_modals} get_actions={ref => [cancel(ref), primary(s.create, () => {
                if (this.valid_name(this.state.modals.create_meta.meta_name, 500)) this.run_action(() => api.add_metadata(this.state.modals.create_meta.meta_name.trim(), this.state.modals.create_meta.meta_type));
            })]}>
                {feedback}<TextField id="advanced-metadata-create-value-name" fullWidth required disabled={this.state.busy} label={s.metadata_value_name} value={modals.create_meta.meta_name} inputProps={{maxLength: 500}} onChange={event => { const value = event.target.value; this.update_state(draft => { draft.modals.create_meta.meta_name = value; draft.error = ""; }); }} />
            </ActionDialog>
            <ActionDialog title={s.metadata_edit_value_title.replace("{name}", modals.edit_meta.metadata.name)} open={modals.edit_meta.is_open} on_close={this.close_modals} get_actions={ref => [cancel(ref), primary(s.save, () => {
                if (this.valid_name(this.state.modals.edit_meta.new_name, 500)) this.run_action(() => api.edit_metadata(this.state.modals.edit_meta.metadata, this.state.modals.edit_meta.new_name.trim()));
            })]}>
                {feedback}<TextField id="advanced-metadata-edit-value-name" fullWidth required disabled={this.state.busy} label={s.metadata_value_name} value={modals.edit_meta.new_name} inputProps={{maxLength: 500}} onChange={event => { const value = event.target.value; this.update_state(draft => { draft.modals.edit_meta.new_name = value; draft.error = ""; }); }} />
            </ActionDialog>
            <ActionDialog title={s.metadata_edit_type_title.replace("{name}", modals.edit_type.old_type.name)} open={modals.edit_type.is_open} on_close={this.close_modals} get_actions={ref => [cancel(ref), primary(s.save, () => {
                if (this.valid_name(this.state.modals.edit_type.new_name, 100)) this.run_action(() => api.edit_metadata_type(this.state.modals.edit_type.old_type, this.state.modals.edit_type.new_name.trim()));
            })]}>
                {feedback}<TextField id="advanced-metadata-edit-type-name" fullWidth required disabled={this.state.busy} label={s.metadata_type_name} value={modals.edit_type.new_name} inputProps={{maxLength: 100}} onChange={event => { const value = event.target.value; this.update_state(draft => { draft.modals.edit_type.new_name = value; draft.error = ""; }); }} />
            </ActionDialog>
            <ActionDialog title={s.metadata_delete_value_title.replace("{name}", modals.delete_meta.metadata.name)} open={modals.delete_meta.is_open} on_close={this.close_modals} get_actions={ref => [cancel(ref), primary(s.delete, () => this.run_action(() => api.delete_metadata(this.state.modals.delete_meta.metadata)))]}>
                <p>{s.metadata_delete_value_warning}</p>{feedback}
            </ActionDialog>
            <ActionDialog title={s.metadata_delete_type_title.replace("{name}", modals.delete_type.meta_type.name)} open={modals.delete_type.is_open} on_close={this.close_modals} get_actions={ref => [cancel(ref), primary(s.delete, () => {
                const modal = this.state.modals.delete_type;
                if (modal.confirm_text.value !== modal.meta_type.name) {
                    this.update_state(draft => { draft.modals.delete_type.confirm_text.reason = s.confirm_mismatch.replace("{name}", modal.meta_type.name); });
                    return;
                }
                this.run_action(() => api.delete_metadata_type(this.state.modals.delete_type.meta_type));
            })]}>
                <p>{s.metadata_delete_type_warning}</p>{feedback}
                <TextField id="advanced-metadata-delete-type-confirm" fullWidth required disabled={this.state.busy} label={s.confirm_name} error={!!modals.delete_type.confirm_text.reason} helperText={modals.delete_type.confirm_text.reason} value={modals.delete_type.confirm_text.value} onChange={event => { const value = event.target.value; this.update_state(draft => { draft.modals.delete_type.confirm_text.value = value; draft.modals.delete_type.confirm_text.reason = ""; draft.error = ""; }); }} />
            </ActionDialog>
        </section>;
    }
}
