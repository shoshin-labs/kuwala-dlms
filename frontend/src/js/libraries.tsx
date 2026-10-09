import React from 'react';
import viewStrings from './locales/versions-view.en.json';
import strings from './locales/curator.en.json';
import versionsStrings from './locales/versions.en.json';
import { folderDestinationAllowed, transferMembership } from './version_move_safety';
import { Grid, Box, Typography, Button, TextField, Checkbox } from '@material-ui/core';
import { Folder, InsertDriveFile } from '@material-ui/icons';
import {
    LibraryVersionsAPI,
    LibraryVersion,
    field_info,
    UsersAPI,
    LibraryAssetsAPI,
    SerializedContent,
    MetadataAPI,
    ContentsAPI,
    User,
    LibraryFolder,
    LibraryModulesAPI, LibraryModule
} from './types';
import prettyBytes from 'pretty-bytes';
import ActionPanel from './reusable/action_panel';
import ActionDialog from './reusable/action_dialog';
import { cloneDeep, isString } from 'lodash';
import { get_field_info_default, update_state } from './utils';
import VALIDATORS from './validators';
import { ViewContentModal } from './reusable/view_content_modal';
import ContentSearch from './reusable/content_search';
import { Autocomplete, createFilterOptions } from '@material-ui/lab';
import { format } from 'date-fns';
import KebabMenu from './reusable/kebab_menu';
import { get_string_from_error } from "./utils";

interface LibrariesProps {
    users_api: UsersAPI
    library_assets_api: LibraryAssetsAPI
    library_versions_api: LibraryVersionsAPI
    metadata_api: MetadataAPI
    contents_api: ContentsAPI
    library_modules_api: LibraryModulesAPI
    show_toast_message: (message: string, is_success: boolean) => void
}

interface LibrariesState {
    modals: LibrariesModals
    selected_folders: LibraryFolder[]
    selected_files: SerializedContent[]
    operation_busy: boolean
    operation_error: string
    destination_loading: boolean
}

interface LibrariesModals {
    add_version: {
        is_open: boolean
        name: field_info<string>
        number: field_info<string>
        banner: field_info<number>
        created_by: User
    }
    edit_version: {
        is_open: boolean
        version: LibraryVersion
        name: field_info<string>
        number: field_info<string>
        created_by: User
    }
    delete_version: {
        is_open: boolean
        to_delete: LibraryVersion
        name: field_info<string>
    }
    view_content: {
        is_open: boolean
        row: SerializedContent
    }
    set_banner: {
        to_set: LibraryVersion
        is_open: boolean
    }
    add_folder: {
        is_open: boolean
        parent: LibraryFolder | null
        name: field_info<string>
    }
    rename_folder: {
        is_open: boolean
        to_rename: LibraryFolder
        name: field_info<string>
    }
    delete_folder: {
        is_open: boolean
        name: field_info<string>
        to_delete: LibraryFolder
    }
    set_folder_logo: {
        is_open: boolean
        to_change: LibraryFolder
    }
    move_content: {
        is_open: boolean
        destination_folder: [LibraryFolder, string]
    }
    add_module_to_version: {
        is_open: boolean
        to_add: LibraryModule
    }
    set_version_metadata: {
        is_open: boolean
        library_version: LibraryVersion
    }
    move_folder: {
        is_open: boolean
        to_move: number
        copy: boolean
        top_level_folder: boolean
        destination_folder: LibraryFolder
        destination_folder_input: string
        destination_library: LibraryVersion
        destination_library_input: string
    }
    column_select: {
        is_open: boolean
    }
}

export default class Libraries extends React.Component<LibrariesProps, LibrariesState> {
    modal_defaults: LibrariesModals
    library_version_default: LibraryVersion
    library_folder_default: LibraryFolder
    library_module_default: LibraryModule
    content_defaults: SerializedContent
    user_defaults: User
    auto_complete_filter: any
    update_state: (update_func: (draft: LibrariesState) => void) => Promise<void>
    constructor(props: LibrariesProps) {
        super(props)

        this.library_version_default = {
            id: 0,
            library_name: "",
            version_number: "",
            library_banner: 0,
            created_by: 0,
            metadata_types: []
        }

        this.content_defaults = {
            id: 0,
            file_name: "",
            filesize: 0,
            content_file: "",
            title: "",
            display_title: "",
            description: null,
            modified_on: "",
            reviewed_on: "",
            copyright_notes: null,
            rights_statement: null,
            additional_notes: "",
            active: false,
            duplicatable: false,
            metadata: [],
            metadata_info: [],
            published_year: ""
        }
        
        this.user_defaults = {
            id: 0,
            name: ""
        }

        this.library_folder_default = {
            id: 0,
            banner_img: 0,
            folder_name: "",
            library_content: [],
            logo_img: 0,
            parent: null,
            version: 0,
            breadcrumb: [],
        }

        this.library_module_default = {
            id: 0,
            module_name: "",
            module_file: "",
            logo_img: 0,
            file_name: ""
        }

        this.modal_defaults = {
            add_version: {
                is_open: false,
                name: get_field_info_default(""),
                number: get_field_info_default(""),
                banner: get_field_info_default(0),
                created_by: cloneDeep(this.user_defaults)
            },
            edit_version: {
                is_open: false,
                version: cloneDeep(this.library_version_default),
                name: get_field_info_default(""),
                number: get_field_info_default(""),
                created_by: cloneDeep(this.user_defaults),
            },
            delete_version: {
                is_open: false,
                to_delete: this.library_version_default,
                name: get_field_info_default("")
            },
            view_content: {
                is_open: false,
                row: cloneDeep(this.content_defaults)
            },
            set_banner: {
                to_set: cloneDeep(this.library_version_default),
                is_open: false
            },
            add_folder: {
                is_open: false,
                parent: null,
                name: get_field_info_default("")
            },
            rename_folder: {
                is_open: false,
                name: get_field_info_default(""),
                to_rename: cloneDeep(this.library_folder_default)
            },
            delete_folder: {
                is_open: false,
                name: get_field_info_default(""),
                to_delete: cloneDeep(this.library_folder_default)
            },
            set_folder_logo: {
                is_open: false,
                to_change: cloneDeep(this.library_folder_default)
            },
            move_content: {
                is_open: false,
                destination_folder: [cloneDeep(this.library_folder_default), ""]
            },
            add_module_to_version: {
                is_open: false,
                to_add: cloneDeep(this.library_module_default)
            },
            set_version_metadata: {
                is_open: false,
                library_version: cloneDeep(this.library_version_default)
            },
            move_folder: {
                is_open: false,
                to_move: 0,
                copy: false,
                top_level_folder: true,
                destination_folder: {id: 0, folder_name: "None Selected"} as any,
                destination_folder_input: "",
                destination_library: {
                    id: 0, library_name: "None Selected", version_number: "None"
                } as any,
                destination_library_input: "",
            },
            column_select: {
                is_open: false
            }
        }

        this.state = {
            modals: cloneDeep(this.modal_defaults),
            selected_files: [],
            selected_folders: [],
            operation_busy: false,
            operation_error: "",
            destination_loading: false,
        }

        this.auto_complete_filter = createFilterOptions<User>({
            ignoreCase: true
        })

        this.update_state = update_state.bind(this)
        this.close_modals = this.close_modals.bind(this)
        this.reset_selection = this.reset_selection.bind(this)
    }

    async close_modals() {
        if (this.state.operation_busy || this.state.destination_loading) return;
        return this.update_state(draft => {
            draft.modals = cloneDeep(this.modal_defaults)
            draft.operation_error = ""
        })
    }

    async run_dialog(operation: () => Promise<unknown>) {
        if (this.state.operation_busy || this.state.destination_loading) return;
        await this.update_state(draft => {
            draft.operation_busy = true;
            draft.operation_error = "";
        });
        try {
            await operation();
            await this.update_state(draft => { draft.operation_busy = false; });
            await this.close_modals();
            this.props.show_toast_message(versionsStrings.operation_saved, true);
        } catch (failure) {
            const detail = get_string_from_error(failure?.response?.data?.error, "");
            await this.update_state(draft => {
                draft.operation_busy = false;
                draft.operation_error = versionsStrings.operation_error + (detail ? " " + detail : "");
            });
        }
    }

    dialog_error() {
        return this.state.operation_error ? <Typography color="error" role="alert">{this.state.operation_error}</Typography> : null;
    }

    document_move_ready() {
        const path = this.props.library_versions_api.state.path;
        const source = path[path.length - 1];
        const destination = this.state.modals.move_content.destination_folder[0];
        return Boolean(source && destination.id && source.id !== destination.id &&
            this.props.library_versions_api.state.folders_in_version.some(([folder]) => folder.id === destination.id) &&
            this.state.selected_files.length && this.state.selected_files.every((document) =>
                this.props.library_versions_api.state.current_directory.files.some((item) => item.id === document.id)));
    }

    folder_move_ready() {
        const move = this.state.modals.move_folder;
        if (!move.to_move || !move.destination_library.id) return false;
        if (move.top_level_folder) return true;
        const folders = this.props.library_versions_api.state.autocomplete_folders.filter((folder) =>
            folder.version === move.destination_library.id);
        const destination = folders.find((folder) => folder.id === move.destination_folder.id);
        return Boolean(destination && folderDestinationAllowed(move.to_move, destination, folders));
    }

    async reset_selection() {
        await this.props.contents_api.set_selection([])
        return this.update_state(draft => {
            draft.selected_files = []
            draft.selected_folders = []
        })
    }

    render() {
        const api = this.props.library_versions_api
        const version = api.state.current_version
        const path = api.state.path
        const currentFolder = path[path.length - 1]
        const pageCount = Math.ceil(api.state.library_versions_count / api.state.library_versions_page_size)
        const reportError = () => this.props.show_toast_message(viewStrings.action_failed, false)
        const openVersion = (row: LibraryVersion) => api.enter_version_root(row).then(this.reset_selection).catch(reportError)
        const openFolder = (folder: LibraryFolder) => api.enter_folder(folder).then(this.reset_selection).catch(reportError)
        const openMove = (files: SerializedContent[]) => this.update_state(draft => {
            draft.selected_files = files
            draft.modals.move_content = cloneDeep(this.modal_defaults.move_content)
            draft.modals.move_content.is_open = true
        })
        const removeFiles = (files: SerializedContent[]) => {
            if (!currentFolder || files.length === 0) return
            api.remove_content_from_folder(currentFolder, files).then(this.reset_selection).catch(reportError)
        }
        return (
            <div className="advanced-page versions-page">
                <header className="advanced-page-heading">
                    <div>
                        <h2>{viewStrings.heading}</h2>
                        <p>{viewStrings.intro}</p>
                    </div>
                    <Button variant="contained" color="primary" onClick={() => this.update_state(draft => {
                        draft.modals.add_version.is_open = true
                    })}>{viewStrings.new_version}</Button>
                </header>
                <div className="version-list" aria-label={viewStrings.heading}>
                    {api.state.library_versions.map(row => {
                        const creator = this.props.users_api.state.users.find(user => user.id === row.created_by)
                        return <article className="version-row" key={row.id} data-selected={row.id === version.id}>
                            <div className="version-row-description">
                                <h3>{row.library_name}</h3>
                                <p className="version-identifier">{row.version_number}</p>
                                <p className="version-row-meta">
                                    {creator?.name && <span>{creator.name}</span>}
                                    {row.created_on && <span>{viewStrings.created} {format(new Date(row.created_on), "d MMM yyyy")}</span>}
                                    {row.id === version.id && <strong>{viewStrings.open_version}</strong>}
                                </p>
                            </div>
                            <div className="version-row-actions">
                                <Button variant="outlined" onClick={() => openVersion(row)}>{viewStrings.open}</Button>
                                <ActionPanel
                                    deleteHint={viewStrings.delete_version}
                                    deleteFn={() => this.update_state(draft => {
                                        draft.modals.delete_version = cloneDeep(this.modal_defaults.delete_version)
                                        draft.modals.delete_version.is_open = true
                                        draft.modals.delete_version.to_delete = row
                                    })}
                                    editHint={viewStrings.edit_version}
                                    editFn={() => this.update_state(draft => {
                                        draft.modals.edit_version.is_open = true
                                        draft.modals.edit_version.version = cloneDeep(row)
                                        draft.modals.edit_version.name.value = row.library_name
                                        draft.modals.edit_version.number.value = row.version_number
                                        draft.modals.edit_version.created_by = creator || cloneDeep(this.user_defaults)
                                    })}
                                    imageHint={viewStrings.change_banner}
                                    imageFn={() => this.update_state(draft => {
                                        draft.modals.set_banner.to_set = cloneDeep(row)
                                        draft.modals.set_banner.is_open = true
                                    })}
                                    cloneHint={viewStrings.copy_version}
                                    cloneFn={() => api.clone_version(row).then(() => this.props.show_toast_message(viewStrings.version_copied, true)).catch(reportError)}
                                    metadataHint={viewStrings.choose_metadata}
                                    buildFn={() => this.update_state(draft => {
                                        draft.modals.set_version_metadata.is_open = true
                                        draft.modals.set_version_metadata.library_version = cloneDeep(row)
                                    })}
                                />
                            </div>
                        </article>
                    })}
                    {api.state.library_versions_count === 0 && <p className="advanced-empty">{viewStrings.no_versions}</p>}
                </div>
                {pageCount > 1 && <nav className="versions-pagination" aria-label={viewStrings.pagination}>
                    <Button variant="outlined" disabled={api.state.library_versions_page === 0} onClick={() => api.set_page(api.state.library_versions_page - 1).catch(reportError)}>{viewStrings.previous}</Button>
                    <span>{viewStrings.page.replace("{page}", String(api.state.library_versions_page + 1)).replace("{total}", String(pageCount))}</span>
                    <Button variant="outlined" disabled={api.state.library_versions_page + 1 >= pageCount} onClick={() => api.set_page(api.state.library_versions_page + 1).catch(reportError)}>{viewStrings.next}</Button>
                </nav>}
                {version.id === 0 ? <div className="advanced-empty versions-start">
                    <h3>{viewStrings.start_heading}</h3>
                    <p>{viewStrings.start_help}</p>
                </div> : <section className="version-workspace" aria-label={viewStrings.workspace}>
                    <header className="version-workspace-heading">
                        <div><p className="advanced-eyebrow">{viewStrings.open_version}</p><h3>{version.library_name}</h3><p className="version-identifier">{version.version_number}</p></div>
                    </header>
                    <nav className="version-breadcrumb" aria-label={viewStrings.location}>
                        <Button onClick={() => openVersion(version)} aria-current={path.length === 0 ? "page" : undefined}>{viewStrings.all_libraries}</Button>
                        {path.map((folder, idx) => <React.Fragment key={folder.id}>
                            <span aria-hidden="true">/</span>
                            <Button onClick={() => openFolder(folder)} aria-current={idx === path.length - 1 ? "page" : undefined}>{folder.folder_name}</Button>
                        </React.Fragment>)}
                    </nav>
                    <header className="advanced-section-heading">
                        <div><h3>{currentFolder ? currentFolder.folder_name : viewStrings.libraries}</h3><p>{currentFolder ? viewStrings.folder_help : viewStrings.libraries_help}</p></div>
                        <Button variant="outlined" onClick={() => this.update_state(draft => {
                            draft.modals.add_folder = cloneDeep(this.modal_defaults.add_folder)
                            draft.modals.add_folder.is_open = true
                            draft.modals.add_folder.parent = currentFolder || null
                        })}>{currentFolder ? viewStrings.new_section : viewStrings.new_library}</Button>
                    </header>
                    <div className="version-folder-list">
                        {api.state.current_directory.folders.map(folder => <div className="version-folder-row" key={folder.id}>
                            <Button className="version-item-open" onClick={() => openFolder(folder)}>
                                <Folder aria-hidden="true" />
                                <span>{folder.folder_name}</span>
                            </Button>
                            <KebabMenu items={[
                                [() => this.update_state(draft => {
                                    draft.modals.rename_folder.is_open = true
                                    draft.modals.rename_folder.to_rename = cloneDeep(folder)
                                    draft.modals.rename_folder.name.value = folder.folder_name
                                }), viewStrings.rename],
                                [() => this.update_state(draft => {
                                    draft.modals.move_folder = cloneDeep(this.modal_defaults.move_folder)
                                    draft.modals.move_folder.is_open = true
                                    draft.modals.move_folder.to_move = folder.id
                                    draft.modals.move_folder.destination_library = cloneDeep(version)
                                }).then(() => api.update_folder_autocomplete(version)), viewStrings.move],
                                [() => this.update_state(draft => {
                                    draft.modals.move_folder = cloneDeep(this.modal_defaults.move_folder)
                                    draft.modals.move_folder.is_open = true
                                    draft.modals.move_folder.copy = true
                                    draft.modals.move_folder.to_move = folder.id
                                    draft.modals.move_folder.destination_library = cloneDeep(version)
                                }).then(() => api.update_folder_autocomplete(version)), viewStrings.copy],
                                ...(folder.parent === null ? [[() => this.update_state(draft => {
                                    draft.modals.set_folder_logo.is_open = true
                                    draft.modals.set_folder_logo.to_change = folder
                                }), viewStrings.change_logo] as [() => void, string]] : []),
                                [() => this.update_state(draft => {
                                    draft.modals.delete_folder = cloneDeep(this.modal_defaults.delete_folder)
                                    draft.modals.delete_folder.is_open = true
                                    draft.modals.delete_folder.to_delete = folder
                                }), viewStrings.delete_group]
                            ]} />
                        </div>)}
                        {!api.state.current_directory.folders.length && <p className="advanced-empty">{currentFolder ? viewStrings.no_sections : viewStrings.no_libraries}</p>}
                    </div>
                    {currentFolder && <section className="version-documents" aria-label={viewStrings.documents}>
                        <header className="advanced-section-heading"><h3>{viewStrings.documents}</h3><span>{api.state.current_directory.files.length} {api.state.current_directory.files.length === 1 ? viewStrings.document_count : viewStrings.documents_count}</span></header>
                        <p className="advanced-help">{viewStrings.membership_help}</p>
                        {this.state.selected_files.length > 0 && <div className="version-selection-toolbar" role="region" aria-label={viewStrings.selected_documents}>
                            <strong>{viewStrings.selected_count.replace("{count}", String(this.state.selected_files.length))}</strong>
                            <Button onClick={() => openMove(this.state.selected_files)}>{viewStrings.move_selected}</Button>
                            <Button onClick={() => removeFiles(this.state.selected_files)}>{viewStrings.remove_selected}</Button>
                            <Button onClick={this.reset_selection}>{viewStrings.clear_selection}</Button>
                        </div>}
                        {api.state.current_directory.files.map(content => <div className="version-document-row" key={content.id}>
                            <Checkbox inputProps={{"aria-label": viewStrings.select_document.replace("{title}", content.title || content.file_name)}} checked={this.state.selected_files.some(file => file.id === content.id)} onChange={(_, checked) => this.update_state(draft => {
                                draft.selected_files = checked ? draft.selected_files.concat(content) : draft.selected_files.filter(file => file.id !== content.id)
                            })} />
                            <Button className="version-item-open" onClick={() => this.update_state(draft => {
                                draft.modals.view_content.is_open = true
                                draft.modals.view_content.row = content
                            })}><InsertDriveFile aria-hidden="true"/><span>{content.title || content.file_name}<small>{Number.isFinite(content.filesize) && content.filesize >= 0 ? prettyBytes(content.filesize) : viewStrings.size_unknown}</small></span></Button>
                            <KebabMenu items={[
                                [() => openMove([content]), viewStrings.move_document],
                                [() => removeFiles([content]), viewStrings.remove_document]
                            ]}/>
                        </div>)}
                        {!api.state.current_directory.files.length && <p className="advanced-empty">{viewStrings.no_documents}</p>}
                        <details className="version-document-picker">
                            <summary>{viewStrings.add_existing}</summary>
                            <p className="advanced-help">{viewStrings.picker_help}</p>
                            <div className="advanced-section-heading">
                                <Button variant="contained" color="primary" disabled={!this.props.contents_api.state.selection.length} onClick={() => this.props.contents_api.add_selected_to_folder(currentFolder).catch(reportError)}>{viewStrings.add_selected.replace("{count}", String(this.props.contents_api.state.selection.length))}</Button>
                                <Button variant="outlined" onClick={() => this.update_state(draft => {draft.modals.column_select.is_open = true})}>{viewStrings.columns}</Button>
                            </div>
                            <div className="version-picker-table"><ContentSearch contents_api={this.props.contents_api} metadata_api={this.props.metadata_api} selection on_view={content => this.update_state(draft => {
                                draft.modals.view_content.row = content
                                draft.modals.view_content.is_open = true
                            })}/></div>
                        </details>
                    </section>}
                    {path.length === 0 && <details className="version-modules">
                        <summary>{viewStrings.optional_modules}</summary>
                        <p className="advanced-help">{viewStrings.modules_help}</p>
                        {api.state.modules_in_version.map(module => <div className="version-folder-row" key={module.id}><span>{module.module_name}</span><Button onClick={() => api.remove_module_from_version(version, module).catch(reportError)}>{viewStrings.remove_module}</Button></div>)}
                        {!api.state.modules_in_version.length && <p>{viewStrings.no_modules}</p>}
                        <Button variant="outlined" onClick={() => this.update_state(draft => {draft.modals.add_module_to_version.is_open = true})}>{viewStrings.add_module}</Button>
                    </details>}
                </section>}
                <ActionDialog
                    on_close={this.close_modals}
                    open={this.state.modals.add_version.is_open}
                    title={versionsStrings.create_title}
                    get_actions={focus_ref => [(
                        <Button
                            key={0}
                            onClick={this.close_modals}
                            disabled={this.state.operation_busy || this.state.destination_loading}
                            color="secondary"
                        >
                            {versionsStrings.cancel}
                        </Button>
                    ), (
                        <Button
                            key={1}
                            disabled={this.state.operation_busy}
                            onClick={async () => {
                                const name = this.state.modals.add_version.name.value.trim();
                                const number = this.state.modals.add_version.number.value.trim();
                                await this.update_state(draft => {
                                    draft.modals.add_version.name.reason = !name || name.length > 300 ? versionsStrings.name_required : "";
                                    draft.modals.add_version.number.reason = !number || number.length > 300 ? versionsStrings.identifier_required : "";
                                });
                                if (this.state.modals.add_version.name.reason || this.state.modals.add_version.number.reason) return;
                                this.run_dialog(() => this.props.library_versions_api.add_version(
                                    name, number, this.state.modals.add_version.created_by.id || null
                                ));
                            }}
                            color="primary"
                            ref={focus_ref}
                        >
                            {this.state.operation_busy ? versionsStrings.saving : versionsStrings.create}
                        </Button>
                    )]}
                >
                    {this.dialog_error()}
                    <TextField
                        id="advanced-create-version-name"
                        fullWidth
                        disabled={this.state.operation_busy}
                        label={versionsStrings.version_name}
                        error={Boolean(this.state.modals.add_version.name.reason)}
                        helperText={this.state.modals.add_version.name.reason}
                        value={this.state.modals.add_version.name.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.add_version.name.value = evt.target.value
                            })
                        }}
                    />
                    <TextField
                        id="advanced-create-version-identifier"
                        fullWidth
                        disabled={this.state.operation_busy}
                        label={versionsStrings.version_identifier}
                        error={Boolean(this.state.modals.add_version.number.reason)}
                        helperText={this.state.modals.add_version.number.reason}
                        value={this.state.modals.add_version.number.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.add_version.number.value = evt.target.value
                            })
                        }}
                    />
                    <Autocomplete
                        disabled={this.state.operation_busy}
                        value={this.state.modals.add_version.created_by.id ? this.state.modals.add_version.created_by : null}
                        onChange={async (_evt, value: User | null) => {
                            if (value?.id === -1) {
                                const name = value.name.trim();
                                if (!name || this.state.operation_busy) return;
                                await this.update_state(draft => {
                                    draft.operation_busy = true;
                                    draft.operation_error = "";
                                });
                                try {
                                    await this.props.users_api.add_user(name);
                                    const creator = this.props.users_api.state.users.find(user => user.name === name);
                                    if (!creator) throw new Error(versionsStrings.creator_unavailable);
                                    await this.update_state(draft => { draft.modals.add_version.created_by = creator; });
                                } catch (failure) {
                                    await this.update_state(draft => { draft.operation_error = versionsStrings.creator_error; });
                                } finally {
                                    await this.update_state(draft => { draft.operation_busy = false; });
                                }
                            } else {
                                await this.update_state(draft => {
                                    draft.modals.add_version.created_by = value || cloneDeep(this.user_defaults);
                                    draft.operation_error = "";
                                });
                            }
                        }}
                        filterOptions={(options, params) => {
                            const filtered = this.auto_complete_filter(options, params)
                            const name = params.inputValue.trim();
                            if (name && !options.some(user => user.name.toLocaleLowerCase() === name.toLocaleLowerCase())) {
                                filtered.push({
                                    id: -1,
                                    name
                                } as User)
                            }
                            return filtered
                        }}
                        handleHomeEndKeys
                        options={this.props.users_api.state.users}
                        getOptionSelected={(a, b) => a.id === b.id}
                        getOptionLabel={option => {
                            return option.id === -1 ? `${versionsStrings.new_creator}: ${option.name}` : option.name
                        }}
                        renderInput={params => (
                            <TextField
                                {...params}
                                variant={"standard"}
                                label={versionsStrings.creator}
                            />
                        )}
                    />
                </ActionDialog>
                <ActionDialog
                    on_close={this.close_modals}
                    open={this.state.modals.edit_version.is_open}
                    title={versionsStrings.edit_title}
                    get_actions={focus_ref => [(
                        <Button
                            key={0}
                            onClick={this.close_modals}
                            disabled={this.state.operation_busy || this.state.destination_loading}
                            color="secondary"
                        >
                            {versionsStrings.cancel}
                        </Button>
                    ), (
                        <Button
                            key={1}
                            disabled={this.state.operation_busy}
                            onClick={async () => {
                                const name = this.state.modals.edit_version.name.value.trim();
                                const number = this.state.modals.edit_version.number.value.trim();
                                await this.update_state(draft => {
                                    draft.modals.edit_version.name.reason = !name || name.length > 300 ? versionsStrings.name_required : "";
                                    draft.modals.edit_version.number.reason = !number || number.length > 300 ? versionsStrings.identifier_required : "";
                                });
                                if (this.state.modals.edit_version.name.reason || this.state.modals.edit_version.number.reason) return;
                                this.run_dialog(() => this.props.library_versions_api.update_version(
                                    this.state.modals.edit_version.version, name, number,
                                    this.state.modals.edit_version.created_by.id ? this.state.modals.edit_version.created_by : undefined
                                ));
                            }}
                            color="primary"
                            ref={focus_ref}
                        >
                            {this.state.operation_busy ? versionsStrings.saving : versionsStrings.save}
                        </Button>
                    )]}
                >
                    {this.dialog_error()}
                    <TextField
                        id="advanced-edit-version-name"
                        fullWidth
                        disabled={this.state.operation_busy}
                        label={versionsStrings.version_name}
                        error={Boolean(this.state.modals.edit_version.name.reason)}
                        helperText={this.state.modals.edit_version.name.reason}
                        value={this.state.modals.edit_version.name.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.edit_version.name.value = evt.target.value
                            })
                        }}
                    />
                    <TextField
                        id="advanced-edit-version-identifier"
                        fullWidth
                        disabled={this.state.operation_busy}
                        label={versionsStrings.version_identifier}
                        error={Boolean(this.state.modals.edit_version.number.reason)}
                        helperText={this.state.modals.edit_version.number.reason}
                        value={this.state.modals.edit_version.number.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.edit_version.number.value = evt.target.value
                            })
                        }}
                    />
                    <Autocomplete
                        disabled={this.state.operation_busy}
                        value={this.state.modals.edit_version.created_by.id ? this.state.modals.edit_version.created_by : null}
                        onChange={async (_evt, value: User | null) => {
                            if (value?.id === -1) {
                                const name = value.name.trim();
                                if (!name || this.state.operation_busy) return;
                                await this.update_state(draft => {
                                    draft.operation_busy = true;
                                    draft.operation_error = "";
                                });
                                try {
                                    await this.props.users_api.add_user(name);
                                    const creator = this.props.users_api.state.users.find(user => user.name === name);
                                    if (!creator) throw new Error(versionsStrings.creator_unavailable);
                                    await this.update_state(draft => { draft.modals.edit_version.created_by = creator; });
                                } catch (failure) {
                                    await this.update_state(draft => { draft.operation_error = versionsStrings.creator_error; });
                                } finally {
                                    await this.update_state(draft => { draft.operation_busy = false; });
                                }
                            } else {
                                await this.update_state(draft => {
                                    draft.modals.edit_version.created_by = value || cloneDeep(this.user_defaults);
                                    draft.operation_error = "";
                                });
                            }
                        }}
                        filterOptions={(options, params) => {
                            const filtered = this.auto_complete_filter(options, params)
                            const name = params.inputValue.trim();
                            if (name && !options.some(user => user.name.toLocaleLowerCase() === name.toLocaleLowerCase())) {
                                filtered.push({
                                    id: -1,
                                    name
                                } as User)
                            }
                            return filtered
                        }}
                        handleHomeEndKeys
                        options={this.props.users_api.state.users}
                        getOptionSelected={(a, b) => a.id === b.id}
                        getOptionLabel={option => {
                            return option.id === -1 ? `${versionsStrings.new_creator}: ${option.name}` : option.name
                        }}
                        renderInput={params => (
                            <TextField
                                {...params}
                                variant={"standard"}
                                label={versionsStrings.creator}
                                helperText={versionsStrings.creator_edit_help}
                            />
                        )}
                    />
                </ActionDialog>
                <ActionDialog
                    on_close={this.close_modals}
                    open={this.state.modals.set_banner.is_open}
                    title={versionsStrings.banner_title}
                    get_actions={focus_ref => [(
                        <Button
                            key={0}
                            onClick={this.close_modals}
                            disabled={this.state.operation_busy || this.state.destination_loading}
                            color="secondary"
                            ref={focus_ref}
                        >
                            {versionsStrings.cancel}
                        </Button>
                    )]}
                >
                    {this.dialog_error()}
                    {!(this.props.library_assets_api.state.assets_by_group[2] || []).some(asset => asset.id > 0 && asset.image_file) &&
                        <Typography>{versionsStrings.banner_empty}</Typography>}
                    <Grid container spacing={2}>
                        {this.props.library_assets_api.state.assets_by_group[2]?.filter(asset => asset.id > 0 && asset.image_file).map(asset => {
                            return (
                                <Grid key={asset.id} item>
                                    <Button
                                        variant="outlined"
                                        disabled={this.state.operation_busy}
                                        aria-pressed={this.state.modals.set_banner.to_set.library_banner === asset.id}
                                        style={{minHeight: 132, minWidth: 120, maxWidth: 200,
                                            display: "flex", flexDirection: "column", gap: 8,
                                            backgroundColor: this.state.modals.set_banner.to_set.library_banner === asset.id ? "#e6f0f6" : undefined}}
                                        onClick={() => this.run_dialog(() => this.props.library_versions_api.set_version_image(
                                            this.state.modals.set_banner.to_set, asset))}
                                    >
                                        <img src={asset.image_file || ""} alt=""
                                            style={{maxHeight: "100px", maxWidth: "100px"}} />
                                        <Typography style={{overflowWrap: "anywhere"}}>{asset.file_name || versionsStrings.unnamed_image}</Typography>
                                    </Button>
                                </Grid>
                            )
                        })}
                    </Grid>
                </ActionDialog>
                <ActionDialog
                    on_close={this.close_modals}
                    open={this.state.modals.set_folder_logo.is_open}
                    title={versionsStrings.logo_title}
                    get_actions={focus_ref => [(
                        <Button
                            key={0}
                            onClick={this.close_modals}
                            disabled={this.state.operation_busy || this.state.destination_loading}
                            color="secondary"
                            ref={focus_ref}
                        >
                            {versionsStrings.cancel}
                        </Button>
                    )]}
                >
                    {this.dialog_error()}
                    {!(this.props.library_assets_api.state.assets_by_group[1] || []).some(asset => asset.id > 0 && asset.image_file) &&
                        <Typography>{versionsStrings.logo_empty}</Typography>}
                    <Grid container spacing={2}>
                        {this.props.library_assets_api.state.assets_by_group[1]?.filter(asset => asset.id > 0 && asset.image_file).map(asset => {
                            return (
                                <Grid key={asset.id} item>
                                    <Button
                                        variant="outlined"
                                        disabled={this.state.operation_busy}
                                        aria-pressed={this.state.modals.set_folder_logo.to_change.logo_img === asset.id}
                                        style={{minHeight: 132, minWidth: 120, maxWidth: 200,
                                            display: "flex", flexDirection: "column", gap: 8,
                                            backgroundColor: this.state.modals.set_folder_logo.to_change.logo_img === asset.id ? "#e6f0f6" : undefined}}
                                        onClick={() => this.run_dialog(async () => {
                                            await this.props.library_versions_api.set_folder_logo(this.state.modals.set_folder_logo.to_change, asset);
                                            await this.props.library_versions_api.refresh_current_directory();
                                        })}
                                    >
                                        <img src={asset.image_file || ""} alt=""
                                            style={{maxHeight: "100px", maxWidth: "100px"}} />
                                        <Typography style={{overflowWrap: "anywhere"}}>{asset.file_name || versionsStrings.unnamed_image}</Typography>
                                    </Button>
                                </Grid>
                            )
                        })}
                    </Grid>
                </ActionDialog>
                <ActionDialog
                    title={versionsStrings.delete_version_title}
                    on_close={this.close_modals}
                    open={this.state.modals.delete_version.is_open}
                    get_actions={focus_ref => [(
                        <Button
                            key={1}
                            disabled={this.state.operation_busy}
                            onClick={async () => {
                                await this.update_state(draft => {
                                    draft.modals.delete_version.name.reason = draft.modals.delete_version.name.value === draft.modals.delete_version.to_delete.library_name ? "" : versionsStrings.confirmation_mismatch;
                                });
                                if (!this.state.modals.delete_version.name.reason) this.run_dialog(() =>
                                    this.props.library_versions_api.delete_version(this.state.modals.delete_version.to_delete));
                            }}
                            color="secondary"
                        >
                            {this.state.operation_busy ? versionsStrings.saving : versionsStrings.delete}
                        </Button>
                    ), (
                        <Button
                            key={2}
                            onClick={this.close_modals}
                            disabled={this.state.operation_busy || this.state.destination_loading}
                            color="primary"
                            ref={focus_ref}
                        >
                            {versionsStrings.cancel}
                        </Button>
                    )]}
                >
                    {this.dialog_error()}
                    <Typography>{versionsStrings.delete_version_help}</Typography>
                    <Typography component="p"><strong>{this.state.modals.delete_version.to_delete.library_name}</strong></Typography>
                    <TextField
                        id="advanced-delete-version-name"
                        fullWidth
                        disabled={this.state.operation_busy}
                        label={versionsStrings.confirm_name}
                        error={this.state.modals.delete_version.name.reason !== ""}
                        helperText={this.state.modals.delete_version.name.reason}
                        value={this.state.modals.delete_version.name.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.delete_version.name.value = evt.target.value
                            })
                        }}
                    />
                </ActionDialog>
                <ViewContentModal
                    is_open={this.state.modals.view_content.is_open}
                    on_close={this.close_modals}
                    metadata_api={this.props.metadata_api}
                    row={this.state.modals.view_content.row}
                />
                <ActionDialog
                    title={this.props.library_versions_api.state.path.length ? versionsStrings.new_section : versionsStrings.new_library}
                    on_close={this.close_modals}
                    get_actions={focus_ref => [(
                        <Button
                            key={2}
                            onClick={this.close_modals}
                            disabled={this.state.operation_busy || this.state.destination_loading}
                            color="secondary"
                            ref={focus_ref}
                        >
                            {versionsStrings.cancel}
                        </Button>
                    ), (
                        <Button
                            key={1}
                            disabled={this.state.operation_busy}
                            onClick={async () => {
                                const name = this.state.modals.add_folder.name.value.trim();
                                await this.update_state(draft => { draft.modals.add_folder.name.reason = !name || name.length > 300 ? versionsStrings.name_required : ""; });
                                if (this.state.modals.add_folder.name.reason) return;
                                const path = this.props.library_versions_api.state.path;
                                this.run_dialog(() => this.props.library_versions_api.create_child_folder(
                                    path.length ? path[path.length - 1] : this.props.library_versions_api.state.current_version, name));
                            }}
                            color="primary"
                        >
                            {this.state.operation_busy ? versionsStrings.saving : versionsStrings.add}
                        </Button>
                    )]}
                    open={this.state.modals.add_folder.is_open}
                >
                    {this.dialog_error()}
                    <TextField
                        id="advanced-create-folder-name"
                        disabled={this.state.operation_busy}
                        label={this.props.library_versions_api.state.path.length ? versionsStrings.section_name : versionsStrings.library_name}
                        fullWidth
                        error={this.state.modals.add_folder.name.reason !== ""}
                        helperText={this.state.modals.add_folder.name.reason}
                        value={this.state.modals.add_folder.name.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.add_folder.name.value = evt.target.value
                            })
                        }}
                    />
                </ActionDialog>
                <ActionDialog
                    title={versionsStrings.delete_folder_title}
                    on_close={this.close_modals}
                    open={this.state.modals.delete_folder.is_open}
                    get_actions={focus_ref => [(
                        <Button
                            key={1}
                            disabled={this.state.operation_busy}
                            onClick={async () => {
                                await this.update_state(draft => {
                                    draft.modals.delete_folder.name.reason = draft.modals.delete_folder.name.value === draft.modals.delete_folder.to_delete.folder_name ? "" : versionsStrings.confirmation_mismatch;
                                });
                                if (!this.state.modals.delete_folder.name.reason) this.run_dialog(() =>
                                    this.props.library_versions_api.delete_folder(this.state.modals.delete_folder.to_delete));
                            }}
                            color="secondary"
                        >
                            {this.state.operation_busy ? versionsStrings.saving : versionsStrings.delete}
                        </Button>
                    ), (
                        <Button
                            key={2}
                            onClick={this.close_modals}
                            disabled={this.state.operation_busy || this.state.destination_loading}
                            color="primary"
                            ref={focus_ref}
                        >
                            {versionsStrings.cancel}
                        </Button>
                    )]}
                >
                    {this.dialog_error()}
                    <Typography>{versionsStrings.delete_folder_help}</Typography>
                    <Typography component="p"><strong>{this.state.modals.delete_folder.to_delete.folder_name}</strong></Typography>
                    <TextField
                        id="advanced-delete-folder-name"
                        label={versionsStrings.confirm_name}
                        disabled={this.state.operation_busy}
                        fullWidth
                        error={this.state.modals.delete_folder.name.reason !== ""}
                        helperText={this.state.modals.delete_folder.name.reason}
                        value={this.state.modals.delete_folder.name.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.delete_folder.name.value = evt.target.value
                            })
                        }}
                    />
                </ActionDialog>
                <ActionDialog
                    title={versionsStrings.rename_folder_title}
                    on_close={this.close_modals}
                    open={this.state.modals.rename_folder.is_open}
                    get_actions={focus_ref => [(
                        <Button
                            key={2}
                            onClick={this.close_modals}
                            disabled={this.state.operation_busy || this.state.destination_loading}
                            color="primary"
                        >
                            {versionsStrings.cancel}
                        </Button>
                    ), (
                        <Button
                            key={1}
                            disabled={this.state.operation_busy}
                            onClick={async () => {
                                const name = this.state.modals.rename_folder.name.value.trim();
                                await this.update_state(draft => { draft.modals.rename_folder.name.reason = !name || name.length > 300 ? versionsStrings.name_required : ""; });
                                if (this.state.modals.rename_folder.name.reason) return;
                                this.run_dialog(() => this.props.library_versions_api.rename_folder(this.state.modals.rename_folder.to_rename, name));
                            }}
                            color="secondary"
                            ref={focus_ref}
                        >
                            {this.state.operation_busy ? versionsStrings.saving : versionsStrings.rename}
                        </Button>
                    )]}
                >
                    {this.dialog_error()}
                    <TextField
                        id="advanced-rename-folder-name"
                        disabled={this.state.operation_busy}
                        label={versionsStrings.rename_folder_name}
                        fullWidth
                        error={this.state.modals.rename_folder.name.reason !== ""}
                        helperText={this.state.modals.rename_folder.name.reason}
                        value={this.state.modals.rename_folder.name.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.rename_folder.name.value = evt.target.value
                            })
                        }}
                    />
                </ActionDialog>
                <ActionDialog
                    title={versionsStrings.move_documents_title}
                    on_close={this.close_modals}
                    open={this.state.modals.move_content.is_open}
                    get_actions={focus_ref => [(
                        <Button
                            key={2}
                            onClick={this.close_modals}
                            disabled={this.state.operation_busy || this.state.destination_loading}
                            color="primary"
                            ref={focus_ref}
                        >
                            {versionsStrings.cancel}
                        </Button>
                    ), (
                        <Button
                            key={1}
                            disabled={this.state.operation_busy || !this.document_move_ready()}
                            onClick={() => {
                                if (!this.document_move_ready()) {
                                    this.update_state(draft => { draft.operation_error = versionsStrings.invalid_document_destination; });
                                    return;
                                }
                                const path = this.props.library_versions_api.state.path
                                const source = path[path.length - 1];
                                const destination = this.state.modals.move_content.destination_folder[0];
                                const documents = [...this.state.selected_files];
                                this.run_dialog(async () => {
                                    await transferMembership(
                                        () => this.props.library_versions_api.add_content_to_folder(destination, documents),
                                        () => this.props.library_versions_api.remove_content_from_folder(source, documents)
                                    );
                                    await this.reset_selection();
                                });
                            }}
                            color="secondary"
                        >
                            {this.state.operation_busy ? versionsStrings.saving : versionsStrings.move}
                        </Button>
                    )]}
                >
                    {this.dialog_error()}
                    <Typography>{versionsStrings.move_documents_help}</Typography>
                    <Autocomplete
                        disabled={this.state.operation_busy}
                        value={this.state.modals.move_content.destination_folder[0].id ? this.state.modals.move_content.destination_folder : null}
                        onChange={(_evt:any, value: [LibraryFolder, string] | null) => {
                            this.update_state(draft => {
                                draft.modals.move_content.destination_folder = value || cloneDeep(this.modal_defaults.move_content.destination_folder);
                                draft.operation_error = "";
                            });
                        }}
                        filterOptions={(options: any, params: any) => {
                            return this.auto_complete_filter(options, params)
                        }}
                        handleHomeEndKeys   
                        options={this.props.library_versions_api.state.folders_in_version.filter(([folder]) =>
                            folder.id !== this.props.library_versions_api.state.path.slice(-1)[0]?.id)}
                        getOptionSelected={(a, b) => a[0].id === b[0].id}
                        getOptionLabel={option => option[1]}
                        renderInput={params => (
                            <TextField
                                {...params}
                                variant={"standard"}
                                label={versionsStrings.document_destination}
                            />
                        )}
                    />
                </ActionDialog>
                <ActionDialog
                    title={versionsStrings.module_title}
                    open={this.state.modals.add_module_to_version.is_open}
                    on_close={this.close_modals}
                    get_actions={focus_ref => [(
                        <Button
                            key={2}
                            onClick={this.close_modals}
                            disabled={this.state.operation_busy || this.state.destination_loading}
                            color="primary"
                        >
                            {versionsStrings.cancel}
                        </Button>
                    ), (
                        <Button
                            key={1}
                            disabled={this.state.operation_busy || !this.props.library_versions_api.state.current_version.id ||
                                !this.props.library_modules_api.state.library_modules.some(module =>
                                    module.id > 0 && module.id === this.state.modals.add_module_to_version.to_add.id)}
                            onClick={()=> {
                                if (!this.props.library_versions_api.state.current_version.id ||
                                    !this.props.library_modules_api.state.library_modules.some(module =>
                                        module.id > 0 && module.id === this.state.modals.add_module_to_version.to_add.id)) return;
                                this.run_dialog(() => this.props.library_versions_api.add_module_to_version(
                                    this.props.library_versions_api.state.current_version,
                                    this.state.modals.add_module_to_version.to_add
                                ));
                            }}
                            color="secondary"
                            ref={focus_ref}
                        >
                            {this.state.operation_busy ? versionsStrings.saving : versionsStrings.add}
                        </Button>
                    )]}
                >
                    {this.dialog_error()}
                    <Typography>{versionsStrings.module_help}</Typography>
                    {!this.props.library_modules_api.state.library_modules.some(module => module.id > 0) &&
                        <Typography>{versionsStrings.module_empty}</Typography>}
                    <Autocomplete
                        disabled={this.state.operation_busy}
                        value={this.state.modals.add_module_to_version.to_add.id > 0 ? this.state.modals.add_module_to_version.to_add : null}
                        onChange={(_evt, value: LibraryModule | null) => {
                            this.update_state(draft => {
                                draft.modals.add_module_to_version.to_add = value || cloneDeep(this.library_module_default);
                                draft.operation_error = "";
                            });
                        }}
                        handleHomeEndKeys
                        options={this.props.library_modules_api.state.library_modules.filter(module => module.id > 0)}
                        getOptionSelected={(a, b) => a.id === b.id}
                        getOptionLabel={option => option.module_name}
                        noOptionsText={versionsStrings.module_no_matches}
                        renderInput={params => (
                            <TextField
                                {...params}
                                variant={"standard"}
                                label={versionsStrings.module_label}
                            />
                        )}
                    />
                </ActionDialog>
                <ActionDialog
                    title={versionsStrings.metadata_title}
                    open={this.state.modals.set_version_metadata.is_open}
                    on_close={this.close_modals}
                    get_actions={focus_ref => [(
                        <Button
                            key={2}
                            onClick={this.close_modals}
                            disabled={this.state.operation_busy || this.state.destination_loading}
                            color="primary"
                            ref={focus_ref}
                        >
                            {versionsStrings.close}
                        </Button>
                    )]}
                >
                    {this.dialog_error()}
                    <Typography>{versionsStrings.metadata_help}</Typography>
                    {this.state.operation_busy && <Typography role="status">{versionsStrings.saving}</Typography>}
                    {!this.props.metadata_api.state.metadata_types.length && <Typography>{versionsStrings.metadata_empty}</Typography>}
                    {this.props.metadata_api.state.metadata_types.map((metadata_type, idx) => {
                        return <Box component="label" alignItems="center" flexDirection="row" display="flex" key={metadata_type.id}>
                            <Box>
                                <Checkbox
                                    disabled={this.state.operation_busy}
                                    inputProps={{"aria-label": metadata_type.name}}
                                    checked={this.state.modals.set_version_metadata.library_version.metadata_types.find(id => id === metadata_type.id) !== undefined}
                                    onChange={async (_evt, checked) => {
                                        if (this.state.operation_busy) return;
                                        await this.update_state(draft => {
                                            draft.operation_busy = true;
                                            draft.operation_error = "";
                                        });
                                        try {
                                            const version = await (checked ?
                                                this.props.library_versions_api.add_metadata_type_to_version :
                                                this.props.library_versions_api.remove_metadata_type_to_version)(
                                                this.state.modals.set_version_metadata.library_version,
                                                metadata_type
                                            );
                                            await this.update_state(draft => {
                                                draft.modals.set_version_metadata.library_version = version;
                                            });
                                        } catch (failure) {
                                            await this.update_state(draft => { draft.operation_error = versionsStrings.operation_error; });
                                        } finally {
                                            await this.update_state(draft => { draft.operation_busy = false; });
                                        }
                                    }}
                                />
                            </Box>
                            <Box>
                                {metadata_type.name}
                            </Box>
                        </Box>
                    })}
                </ActionDialog>
                <ActionDialog
                    title={this.state.modals.move_folder.copy ?
                        versionsStrings.copy_folder_title : versionsStrings.move_folder_title}
                    open={this.state.modals.move_folder.is_open}
                    on_close={this.close_modals}
                    get_actions={focus_ref => [(
                        <Button
                            key={1}
                            onClick={this.close_modals}
                            disabled={this.state.operation_busy || this.state.destination_loading}
                            color="primary"
                            ref={focus_ref}
                        >
                            {versionsStrings.cancel}
                        </Button>
                    ), (
                        <Button
                            key={2}
                            disabled={this.state.operation_busy || this.state.destination_loading || !this.folder_move_ready()}
                            onClick={() => {
                                if (!this.folder_move_ready()) {
                                    this.update_state(draft => { draft.operation_error = versionsStrings.invalid_folder_destination; });
                                    return;
                                }
                                const move = this.state.modals.move_folder;
                                this.run_dialog(async () => {
                                    await this.props.library_versions_api.move_folder(move.to_move, move.copy,
                                        move.top_level_folder ? undefined : move.destination_folder.id,
                                        move.destination_library.id);
                                    await this.reset_selection();
                                });
                            }}
                            color="secondary"
                            ref={focus_ref}
                        >
                            {this.state.operation_busy ? versionsStrings.saving :
                                this.state.modals.move_folder.copy ? versionsStrings.copy : versionsStrings.move}
                        </Button>
                    )]}
                >
                    {this.dialog_error()}
                    <Typography>{versionsStrings.folder_move_help}</Typography>
                    <Autocomplete
                        style={{
                            width: "100%", minWidth: 0
                        }}
                        disabled={this.state.operation_busy || this.state.destination_loading}
                        value={this.state.modals.move_folder.destination_library.id ? this.state.modals.move_folder.destination_library : null}
                        options={this.props.library_versions_api.state
                            .autocomplete_versions}
                        onChange={async (_, input) => {
                            await this.update_state(draft => {
                                draft.modals.move_folder.destination_library = input || cloneDeep(this.modal_defaults.move_folder.destination_library);
                                draft.modals.move_folder.destination_folder = cloneDeep(this.modal_defaults.move_folder.destination_folder);
                                draft.destination_loading = Boolean(input);
                                draft.operation_error = "";
                            });
                            if (!input) return;
                            try {
                                await this.props.library_versions_api.update_folder_autocomplete(input);
                            } catch (failure) {
                                await this.update_state(draft => { draft.operation_error = versionsStrings.operation_error; });
                            } finally {
                                await this.update_state(draft => { draft.destination_loading = false; });
                            }
                        }}
                        onInputChange={(_, prefix) => this.props.library_versions_api
                            .update_version_autocomplete(prefix).catch(() => this.update_state(draft => {
                                draft.operation_error = versionsStrings.operation_error;
                            }))}
                        getOptionSelected={(a, b) => a.id === b.id}
                        getOptionLabel={version => version.id == 0 ? "" :
                            `${version.library_name} @ ${version.version_number}`}
                        filterOptions={(options, params) => {
                            return this.auto_complete_filter(options, params)
                        }}
                        renderInput={params => <TextField
                            {...params}
                            variant="standard"
                            label={versionsStrings.destination_version}
                        />}
                    />
                    {this.state.destination_loading && <Typography role="status">{versionsStrings.destination_loading}</Typography>}
                    <Typography component="label">
                    <Checkbox
                        disabled={this.state.operation_busy || this.state.destination_loading}
                        checked={this.state.modals.move_folder.top_level_folder}
                        onChange={(_, checked) => this.update_state(draft => {
                            draft.modals.move_folder.top_level_folder = checked
                        })}
                    />
                    {versionsStrings.destination_at_root}
                    </Typography>
                    {this.state.modals.move_folder.top_level_folder ?
                    <></> :
                    <Autocomplete
                        disabled={this.state.operation_busy || this.state.destination_loading || !this.state.modals.move_folder.destination_library.id}
                        value={this.state.modals.move_folder.destination_folder.id ? this.state.modals.move_folder.destination_folder : null}
                        options={
                            this.props.library_versions_api.state.autocomplete_folders.filter((folder) =>
                                folder.version === this.state.modals.move_folder.destination_library.id &&
                                folderDestinationAllowed(this.state.modals.move_folder.to_move, folder,
                                    this.props.library_versions_api.state.autocomplete_folders))
                        }
                        onChange={(_, folder) => {
                            this.update_state(draft => {
                                draft.modals.move_folder.destination_folder = folder || cloneDeep(this.modal_defaults.move_folder.destination_folder);
                                draft.operation_error = "";
                            })
                        }}
                        getOptionLabel={folder =>
                            folder.breadcrumb?.map(folder => folder.folder_name)
                            .join("/") || ""}
                        getOptionSelected={(a, b) => a.id === b.id}
                        filterOptions={(options, params) => {
                            return this.auto_complete_filter(options, params)
                        }}
                        renderInput={params => <TextField
                            {...params}
                            variant="standard"
                            label={versionsStrings.folder_destination}
                        />}
                    />}
                </ActionDialog>
                <ActionDialog
                    open={this.state.modals.column_select.is_open}
                    title={versionsStrings.columns_title}
                    on_close={this.close_modals}
                    get_actions={focus_ref => [(
                        <Button
                            key={2}
                            onClick={this.close_modals}
                            color="primary"
                            ref={focus_ref}
                        >
                            {versionsStrings.close}
                        </Button>
                    )]}
                >
                    {["filesize", "content_file", "rights_statement", "description", "modified_on", "reviewed_on", "copyright_notes", "published_year", "duplicatable"].map((name, idx) => {
                        const label = versionsStrings.column_labels[name] || name;
                        return <Box component="label" alignItems="center" flexDirection="row" display="flex" key={name}>
                            <Box key={0}>
                                <Checkbox
                                    inputProps={{"aria-label": label}}
                                    checked={this.props.metadata_api.state.show_columns[name]}
                                    onChange={(_, checked) => {
                                        this.props.metadata_api.set_view_metadata_column(draft => {
                                            draft[name] = checked
                                        })
                                    }}
                                />
                            </Box>
                            <Box key={1}>
                                <Typography>{label}</Typography>
                            </Box>
                        </Box>
                    })}
                    {this.props.metadata_api.state.metadata_types.map((metadata_type, idx) => {
                        return <Box component="label" alignItems="center" flexDirection="row" display="flex" key={metadata_type.id}>
                            <Box key={0}>
                                <Checkbox
                                    inputProps={{"aria-label": metadata_type.name}}
                                    checked={this.props.metadata_api.state.show_columns[metadata_type.name]}
                                    onChange={(_, checked) => {
                                        this.props.metadata_api.set_view_metadata_column(draft => {
                                            draft[metadata_type.name] = checked
                                        })
                                    }}
                                />
                            </Box>
                            <Box key={1}>
                                <Typography>{metadata_type.name}</Typography>
                            </Box>
                        </Box>
                    })}
                </ActionDialog>
            </div>
        )
    }
}
