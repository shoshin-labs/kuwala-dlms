import React, { RefObject } from 'react';
import { Button, Grid, Link, TextField } from '@material-ui/core';
import { field_info, LibraryAssetsAPI, LibraryModule, LibraryModulesAPI } from './types';
import { Grid as DataGrid, Table, TableHeaderRow } from '@devexpress/dx-react-grid-material-ui';
import ActionPanel from './reusable/action_panel';
import { get_field_info_default, update_state } from './utils';
import { cloneDeep } from 'lodash';
import ActionDialog from './reusable/action_dialog';
import VALIDATORS from './validators';
import { APP_URLS } from './urls';

interface LibraryModulesProps {
    library_modules_api: LibraryModulesAPI
    library_assets_api: LibraryAssetsAPI
}
interface LibraryModulesState {
    modals: LibraryModulesModals
}

interface LibraryModulesModals {
    set_logo_image: {
        is_open: boolean
        to_change: LibraryModule
    }
    add_module: {
        is_open: boolean
        module_name: field_info<string>
    }
    edit_module: {
        is_open: boolean
        to_change: LibraryModule
        module_name: field_info<string>
    }
    delete_module: {
        is_open: boolean
        module_name: field_info<string>
        to_delete: LibraryModule
    }
}

export default class LibraryModules extends React.Component<LibraryModulesProps, LibraryModulesState> {
    update_state: (update_func: (draft: LibraryModulesState) => void) => Promise<void>
    add_module_file_ref: RefObject<HTMLInputElement>
    edit_module_file_ref: RefObject<HTMLInputElement>
    modal_defaults: LibraryModulesModals
    library_module_default: LibraryModule
    constructor(props: Readonly<LibraryModulesProps>) {
        super(props)

        this.add_module_file_ref = React.createRef()
        this.edit_module_file_ref = React.createRef()
        
        this.library_module_default = {
            id: 0,
            logo_img: 0,
            module_file: "",
            module_name: "",
            file_name: ""
        }

        this.modal_defaults = {
            set_logo_image: {
                is_open: false,
                to_change: this.library_module_default
            },
            add_module: {
                is_open: false,
                module_name: get_field_info_default("")
            },
            edit_module: {
                is_open: false,
                module_name: get_field_info_default(""),
                to_change: this.library_module_default
            },
            delete_module: {
                is_open: false,
                module_name: get_field_info_default(""),
                to_delete: this.library_module_default
            }
        }

        this.state = {
            modals: cloneDeep(this.modal_defaults)
        }

        this.update_state = update_state.bind(this)
        this.close_modals = this.close_modals.bind(this)
    }

    async close_modals() {
        return this.update_state(draft => {
            draft.modals = cloneDeep(this.modal_defaults)
        })
    }

    render() {
        return (
            <>
                <Button
                    onClick={() => {
                        this.update_state(draft => {
                            draft.modals.add_module.is_open = true
                        })
                    }}
                    style={{
                        marginLeft: "1em",
                        marginBottom: "1em",
                        backgroundColor: "#003c6c",
                        color: "#FFFFFF"
                    }}
                >Add Module</Button>
                <DataGrid
                    columns={[
                        {name: "module_name", title: "Name"},
                        {name: "file_name", title: "File", getCellValue: (row) => {
                            return <Link target="_blank" href={new URL(row.file_name, APP_URLS.MODULE_FOLDER).href}>
                                {row.file_name}
                            </Link>
                        }},
                        {name: "logo_img", title: "Logo", getCellValue: (row: LibraryModule) => {
                            return <ActionPanel
                                imageFn={() => this.update_state(draft => {
                                    draft.modals.set_logo_image.is_open = true
                                    draft.modals.set_logo_image.to_change = row
                                })}
                            />

                        }},
                        {name: "actions", title: "Actions", getCellValue: (row: LibraryModule) => {
                            return <ActionPanel
                                editFn={() => {
                                    this.update_state(draft => {
                                        draft.modals.edit_module.is_open = true
                                        draft.modals.edit_module.to_change = row
                                        draft.modals.edit_module.module_name.value = row.module_name
                                    })
                                }}
                                deleteFn={() => {
                                    this.update_state(draft => {
                                        draft.modals.delete_module.is_open = true
                                        draft.modals.delete_module.to_delete = row
                                    })
                                }}
                            />
                        }}
                    ]}
                    rows={this.props.library_modules_api.state.library_modules}
                >
                    <Table
                        columnExtensions={[
                            {columnName: 'actions', width: 100},
                            {columnName: 'module_file', width: 500}
                        ]}
                    />
                    <TableHeaderRow />
                </DataGrid>
                <ActionDialog
                    on_close={this.close_modals}
                    open={this.state.modals.set_logo_image.is_open}
                    title={"Set Module Logo"}
                    get_actions={focus_ref => [(
                        <Button
                            key={0}
                            onClick={this.close_modals}
                            color="secondary"
                            ref={focus_ref}
                        >
                            Cancel
                        </Button>
                    )]}
                >
                    <Grid container spacing={2}>
                        {this.props.library_assets_api.state.assets_by_group[1]?.map((asset, idx) => {
                            return (
                                <Grid
                                    key={idx}
                                    item
                                    style={this.state.modals.set_logo_image.to_change.logo_img === asset.id
                                    ? {backgroundColor: "#e6f0f6"} : undefined}
                                    onClick={_ => {
                                        this.props.library_modules_api.set_module_logo(
                                            this.state.modals.set_logo_image.to_change,
                                            asset
                                        )
                                        .then(this.close_modals)
                                    }}
                                >
                                    <img
                                        src={asset.image_file === null ? "" : asset.image_file}
                                        style={{maxHeight: "100px", maxWidth: "100px"}}
                                    />
                                </Grid>
                            )
                        })}
                    </Grid>
                </ActionDialog>
                <ActionDialog
                    on_close={this.close_modals}
                    open={this.state.modals.add_module.is_open}
                    title={"Add Module"}
                    get_actions={focus_ref => [(
                        <Button
                            key={0}
                            onClick={this.close_modals}
                            color="secondary"
                        >
                            Cancel
                        </Button>
                    ), (
                        <Button
                            key={1}
                            onClick={async () => {
                                await this.update_state(draft => {
                                    draft.modals.add_module.module_name.reason = VALIDATORS.MODULE_NAME(
                                        draft.modals.add_module.module_name.value
                                    )
                                })
                                
                                const reason = this.state.modals.add_module.module_name.reason
                                const file = this.edit_module_file_ref.current?.files?.item(0)

                                if (
				     reason === "" && file !== null && file !== undefined
				     && (file.type === "application/zip" || file.type === "x-zip-compressed")
				) {
				    console.log("added")
                                    return this.props.library_modules_api.add_module(
                                        this.state.modals.add_module.module_name.value,
                                        file
                                    ).then(this.close_modals)
                                }
                            }}
                            color="primary"
                            ref={focus_ref}
                        >
                            Add
                        </Button>
                    )]}
                >
                    <Grid item xs={12} style={{marginBottom: "10px"}}>
                        <TextField
                            fullWidth
                            error={this.state.modals.add_module.module_name.reason !== ""}
                            helperText={this.state.modals.add_module.module_name.reason}
                            label={"Module Name"}
                            value={this.state.modals.add_module.module_name.value}
                            onChange={evt => {
                                evt.persist()
                                this.update_state(draft => {
                                    draft.modals.add_module.module_name.value = evt.target.value
                                })
                            }}
                        />
                    </Grid>
                    <Grid item xs={12} style={{marginBottom: "10px"}}>
                        <input
                            accept=".zip"
                            id="raised-button-file"
                            type="file"
                            ref={this.edit_module_file_ref}
                        />
                    </Grid>
                </ActionDialog>
                <ActionDialog
                    on_close={this.close_modals}
                    open={this.state.modals.edit_module.is_open}
                    title={"Edit Module"}
                    get_actions={focus_ref => [(
                        <Button
                            key={0}
                            onClick={this.close_modals}
                            color="secondary"
                            ref={focus_ref}
                        >
                            Cancel
                        </Button>
                    ), (
                        <Button
                            key={1}
                            onClick={async () => {
                                await this.update_state(draft => {
                                    draft.modals.edit_module.module_name.reason = VALIDATORS.MODULE_NAME(
                                        draft.modals.edit_module.module_name.value
                                    )
                                })
                                
                                const reason = this.state.modals.edit_module.module_name.reason
                                const file = this.edit_module_file_ref.current?.files?.item(0)

                                if (reason === "") {
                                    return this.props.library_modules_api.edit_module(
                                        this.state.modals.edit_module.to_change,
                                        this.state.modals.edit_module.module_name.value,
                                        file
                                    ).then(this.close_modals)
                                }
                            }}
                            color="primary"
                        >
                            Edit
                        </Button>
                    )]}
                >
                    <Grid item xs={12} style={{marginBottom: "10px"}}>
                        <TextField
                            fullWidth
                            error={this.state.modals.edit_module.module_name.reason !== ""}
                            helperText={this.state.modals.edit_module.module_name.reason}
                            label={"Module Name"}
                            value={this.state.modals.edit_module.module_name.value}
                            onChange={evt => {
                                evt.persist()
                                this.update_state(draft => {
                                    draft.modals.edit_module.module_name.value = evt.target.value
                                })
                            }}
                        />
                    </Grid>
                    <Grid item xs={12} style={{marginBottom: "10px"}}>
                        <input
                            accept=".zip"
                            id="raised-button-file"
                            type="file"
                            ref={this.edit_module_file_ref}
                        />
                    </Grid>
                </ActionDialog>
                <ActionDialog
                    on_close={this.close_modals}
                    open={this.state.modals.delete_module.is_open}
                    title={"Delete Module"}
                    get_actions={focus_ref => [(
                        <Button
                            key={0}
                            onClick={async () => {
                                await this.update_state(draft => {
                                    draft.modals.delete_module.module_name.reason = VALIDATORS.DELETE_IF_EQUALS(
                                        draft.modals.delete_module.module_name.value,
                                        draft.modals.delete_module.to_delete.module_name
                                    )
                                })

                                if (this.state.modals.delete_module.module_name.reason === "") {
                                    return this.props.library_modules_api.delete_module(this.state.modals.delete_module.to_delete)
                                        .then(this.close_modals)
                                }
                            }}
                            color="secondary"
                        >
                            Delete
                        </Button>
                    ), (
                        <Button
                            key={1}
                            onClick={this.close_modals}
                            color="primary"
                            ref={focus_ref}
                        >
                            Cancel
                        </Button>
                    )]}
                >
                    <TextField
                        fullWidth
                        error={this.state.modals.delete_module.module_name.reason !== ""}
                        helperText={this.state.modals.delete_module.module_name.reason}
                        label={`Re-Enter ${this.state.modals.delete_module.to_delete.module_name} to confirm`}
                        value={this.state.modals.delete_module.module_name.value}
                        onChange={evt => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.delete_module.module_name.value = evt.target.value
                            })
                        }}
                    />
                </ActionDialog>
            </>
        )
    }
}
