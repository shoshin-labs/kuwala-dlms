import React, { Component } from "react"
import Button from "@material-ui/core/Button"
import ExpansionPanel from "@material-ui/core/ExpansionPanel"
import ExpansionPanelSummary from "@material-ui/core/ExpansionPanelSummary"
import ExpansionPanelDetails from "@material-ui/core/ExpansionPanelSummary"
import Grid from "@material-ui/core/Grid"

import { APP_URLS } from "./urls"
import { Typography, TextField } from "@material-ui/core"

import { cloneDeep, isEqual, set } from "lodash"

import {
    FilteringState,
    IntegratedFiltering,
    PagingState,
    IntegratedPaging,
    CustomPaging
} from "@devexpress/dx-react-grid"
import {
    Grid as DataGrid,
    PagingPanel,
    Table,
    TableHeaderRow,
    TableFilterRow
} from "@devexpress/dx-react-grid-material-ui"

import ActionPanel from "./reusable/action_panel"
import ActionDialog from './reusable/action_dialog'
import { update_state, get_field_info_default } from './utils'
import VALIDATORS from './validators'
import KebabMenu from './reusable/kebab_menu'
import { MetadataAPI, SerializedMetadataType, SerializedMetadata, field_info } from './types'

interface MetadataProps {
    metadata_api: MetadataAPI
    show_toast_message: (message: string, is_success:boolean) => void
}

type panel_data = {
    [metadata_type: string]: boolean
}

interface MetadataState {
    panel_data: panel_data
    modals: MetadataModals
}

interface MetadataModals {
    create_type: {
        is_open: boolean
        type_name: string
    }
    edit_type: {
        is_open: boolean
        old_type: SerializedMetadataType
        new_name: string
    }
    create_meta: {
        is_open: boolean
        meta_type: SerializedMetadataType
        meta_name: string
    }
    delete_meta: {
        is_open: boolean
        metadata: SerializedMetadata
    }
    edit_meta: {
        is_open: boolean
        metadata: SerializedMetadata
        new_name: string
    }
    delete_type: {
        is_open: boolean
        meta_type: SerializedMetadataType
        confirm_text: field_info<string>
    }
}

export default class Metadata extends Component<MetadataProps, MetadataState> {
    modal_defaults: MetadataModals
    page_sizes: number[]
    default_page_size: number
    columnExtensions: any

    meta_type_defaults: SerializedMetadataType
    metadata_defaults: SerializedMetadata
    
    update_state: (update_func: (draft: MetadataState) => void) => Promise<void>

    constructor(props: MetadataProps) {
        super(props)

        this.metadata_defaults = {
            name: "",
            id: 0,
            type_name: "",
            type: 0
        }
        this.meta_type_defaults = {
            id: 0,
            name: ""
        }

        this.modal_defaults = {
            delete_meta: {
                is_open: false,
                metadata: this.metadata_defaults,
            },
            create_type: {
                is_open: false,
                type_name: ""
            },
            edit_type: {
                is_open: false,
                old_type: {
                    id: 0,
                    name: ""
                },
                new_name: ""
            },
            create_meta: {
                is_open: false,
                meta_type: this.meta_type_defaults,
                meta_name: ""
            },
            edit_meta: {
                is_open: false,
                metadata: this.metadata_defaults,
                new_name: ""
            },
            delete_type: {
                is_open: false,
                meta_type: this.meta_type_defaults,
                confirm_text: get_field_info_default("")
            }
        }
        this.state = {
            panel_data: this.props.metadata_api.state.metadata_types.reduce((panel_data, metadata_type) => {
                return set(panel_data, [metadata_type.name], false) 
            }, {} as panel_data),
            modals: cloneDeep(this.modal_defaults)
        }

        this.page_sizes = [10, 25, 50]
        this.default_page_size = this.page_sizes[0]

        this.close_modals = this.close_modals.bind(this)
        this.update_state = update_state.bind(this)


        this.columnExtensions = [
            {columnName: "actions", filteringEnabled: false},
            {columnName: "name", filteringEnabled: true}
        ]
    }

    componentDidUpdate(prev_props: MetadataProps, _prev_state: MetadataState) {
        if (!isEqual(
            prev_props.metadata_api.state.metadata_types,
            this.props.metadata_api.state.metadata_types
        )) {
            this.update_state(draft => {
                draft.panel_data = this.props.metadata_api.state.metadata_types.reduce((panel_data, metadata_type) => {
                    return set(panel_data, [metadata_type.name], false) 
                }, {} as panel_data)
            })
        
        }
    }

    close_modals() {
        this.update_state(draft => {
            draft.modals = cloneDeep(this.modal_defaults)
        })
    }

    render() {
        const panels = Object.keys(this.state.panel_data).map((type_name, idx) => {
            const expanded = this.state.panel_data[type_name]
            const metadata_type = this.props.metadata_api.state.metadata_types.find(to_test => to_test.name === type_name)
            if (metadata_type === undefined) {
                return <></>
            }
            return (
                <ExpansionPanel expanded={expanded} onChange={(_, expanded: boolean) => {
                    this.update_state(draft => {
                        draft.panel_data[metadata_type.name] = expanded
                    })
                }} key={idx}>
                    <ExpansionPanelSummary>
                        <Grid container>
                            <Grid item xs={6} style={{textAlign: "left"}}>
                                <Typography style={{
                                    fontWeight: 600
                                }}>{metadata_type.name}</Typography>
                            </Grid>
                            <Grid item xs={6} style={{
                                textAlign: "right"
                            }}>
                                <KebabMenu
                                    items={[
                                        [() => {
                                            this.update_state(draft => {
                                                draft.modals.create_meta.meta_type = metadata_type
                                                draft.modals.create_meta.is_open = true
                                            })
                                        }, "Add Metadata"],
                                        [() => {
                                            this.update_state(draft => {
                                                draft.modals.edit_type.old_type = metadata_type
                                                draft.modals.edit_type.is_open = true
                                            })
                                        }, "Edit Metadata Type"],
                                        [() => {
                                            this.update_state(draft => {
                                                draft.modals.delete_type.meta_type = metadata_type
                                                draft.modals.delete_type.is_open = true
                                            })
                                        }, "Delete Metadata Type"],
                                        [() => {
                                            window.open(APP_URLS.METADATA_SHEET(metadata_type.name))
                                        }, "Download Spreadsheet"]
                                    ]}
                                />
                            </Grid>
                        </Grid>
                    </ExpansionPanelSummary>
                    <ExpansionPanelDetails>
                        <DataGrid
                            rows={this.props.metadata_api.state.autocomplete_metadata[metadata_type.name] || []}
                            columns={[
                                { name: 'actions', title: 'Actions', getCellValue: (row: SerializedMetadata) => {
                                    return (
                                        <ActionPanel
                                            editFn={() => {
                                                this.update_state(draft => {
                                                    draft.modals.edit_meta.is_open = true
                                                    draft.modals.edit_meta.metadata = row
                                                    draft.modals.edit_meta.new_name = row.name
                                                })
                                            }}
                                            deleteFn={() => {
                                                this.update_state(draft => {
                                                    draft.modals.delete_meta.is_open = true
                                                    draft.modals.delete_meta.metadata = row
                                                })
                                            }}
                                        />
                                    )
                                }},
                                { name: 'name', title: "Metadata Name" }
                            ]}
                        >
                            <FilteringState
                                columnExtensions={this.columnExtensions}
                                onFiltersChange={filters => {
                                    console.log("filters", filters);
                                    if (filters.length === 0) {
                                        this.props.metadata_api.update_autocomplete(metadata_type, "")
                                    }
                                    else {
                                        filters.map(
                                            filter => this.props.metadata_api
                                                .update_autocomplete(
                                                    metadata_type, filter.value || ""
                                                )
                                        )
                                    }
                                }}
                            />
                            <IntegratedFiltering />
                            <PagingState
                                defaultPageSize={this.default_page_size}
                                currentPage={this.props.metadata_api.state.page_by_type[metadata_type.name]?.page - 1}
                                onCurrentPageChange={new_page => this.props.metadata_api.set_metadata_page(new_page + 1, metadata_type.name)}
                                // pageSize={this.props.library_versions_api.state.library_versions_page_size}
                                pageSize={this.props.metadata_api.state.page_by_type[metadata_type.name]?.page_size}
                                // onPageSizeChange={this.props.library_versions_api.set_page_size}
                                onPageSizeChange={new_page_size => this.props.metadata_api.set_metadata_page_size(new_page_size, metadata_type.name)}
                            />
                            <CustomPaging
                                totalCount={this.props.metadata_api.state.page_by_type[metadata_type.name]?.count}
                            />
                            <Table />
                            <TableHeaderRow />
                            <TableFilterRow />
                            <PagingPanel pageSizes={this.page_sizes} />
                        </DataGrid>
                    </ExpansionPanelDetails>
                </ExpansionPanel>
            )
        })

        return (
            <React.Fragment>
                <Button
                    onClick={_ => {
                        this.update_state(draft => {
                            draft.modals.create_type.is_open = true
                        })
                    }}
                    style={{
                        marginLeft: "1em",
                        marginBottom: "1em",
                        backgroundColor: "var(--action)",
                        color: "#FFFFFF"
                    }}
                >New Metadata Type</Button>
                {panels}
                {panels.length === 0 ?
                    <Typography variant="h6" style={{marginLeft: "3em"}}>No Metadata Types Found</Typography>
                : null}
                <ActionDialog
                    title={`Delete Metadata item ${this.state.modals.delete_meta.metadata.name} of type ${this.state.modals.delete_meta.metadata.type_name}?`}
                    open={this.state.modals.delete_meta.is_open}
                    get_actions={focus_ref => [(
                        <Button
                            key={0}
                            onClick={this.close_modals}
                            color="primary"
                        >
                            Cancel
                        </Button>
                    ), (
                        <Button
                            key={1}
                            onClick={()=> {
                                this.props.metadata_api.delete_metadata(this.state.modals.delete_meta.metadata)
                                this.close_modals()
                            }}
                            color="secondary"
                            ref={focus_ref}
                        >
                            Confirm
                        </Button>
                    )]}
                >
                    <Typography>
                        WARNING: Deleting a metadata will also delete each of that metadata on every content and is irreversible.
                    </Typography>
                </ActionDialog>
                <ActionDialog
                    title={"Create New Metadata Type"}
                    open={this.state.modals.create_type.is_open}
                    on_close={this.close_modals}
                    get_actions={ref => [<>
                                <Button
                                    key={0}
                                    onClick={this.close_modals}
                                    color="secondary"
                                    ref={ref}
                                >
                                    Cancel
                                </Button>
                                <Button
                                    key={1}
                                    onClick={()=> {
                                        this.props.metadata_api.add_metadata_type(this.state.modals.create_type.type_name)
                                            .catch(() => this.props.show_toast_message("Failed to create modal", false))
                                        this.close_modals()
                                    }}
                                    color="primary"
                                >
                                    Create
                                </Button>
                            </>]
                        }
               >
                    <TextField
                        fullWidth
                        label={"Metadata Type"}
                        value={this.state.modals.create_type.type_name}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.create_type.type_name = evt.target.value
                            })
                        }}
                    />
                </ActionDialog>
                <ActionDialog
                    title={`Create a new Metadata of Type ${this.state.modals.create_meta.meta_type.name}`}
                    open={this.state.modals.create_meta.is_open}
                    on_close={this.close_modals}
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
                            onClick={()=> {
                                this.props.metadata_api.add_metadata(this.state.modals.create_meta.meta_name, this.state.modals.create_meta.meta_type)
                                this.close_modals()
                            }}
                            color="primary"
                            ref={focus_ref}
                        >
                            Create
                        </Button>
                    )]}
                >
                    <TextField
                        fullWidth
                        label={"Metadata"}
                        value={this.state.modals.create_meta.meta_name}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.create_meta.meta_name = evt.target.value
                            })
                        }}
                    />
                </ActionDialog>
                <ActionDialog
                    title={`Edit Metadata ${this.state.modals.edit_meta.metadata.name}`}
                    open={this.state.modals.edit_meta.is_open}
                    on_close={this.close_modals}
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
                            onClick={()=> {
                                this.props.metadata_api.edit_metadata(this.state.modals.edit_meta.metadata, this.state.modals.edit_meta.new_name)
                                this.close_modals()
                            }}
                            color="primary"
                            ref={focus_ref}
                        >
                            Confirm
                        </Button>
                    )]}
                >
                    <TextField
                        fullWidth
                        label={"Metadata Name"}
                        value={this.state.modals.edit_meta.new_name}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.edit_meta.new_name = evt.target.value
                            })
                        }}
                    />
                </ActionDialog>
                <ActionDialog
                    title={`Edit Metadata Type ${this.state.modals.edit_type.old_type.name}`}
                    open={this.state.modals.edit_type.is_open}
                    on_close={this.close_modals}
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
                            onClick={()=> {
                                this.props.metadata_api.edit_metadata_type(this.state.modals.edit_type.old_type, this.state.modals.edit_type.new_name)
                                this.close_modals()
                            }}
                            color="primary"
                            ref={focus_ref}
                        >
                            Confirm
                        </Button>
                    )]}
                >
                    <TextField
                        fullWidth
                        label={"Metadata Type Name"}
                        value={this.state.modals.edit_type.new_name}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.edit_type.new_name = evt.target.value
                            })
                        }}
                    />
                </ActionDialog>
                <ActionDialog
                    title={`Delete Metadata Type ${this.state.modals.delete_type.meta_type.name}`}
                    open={this.state.modals.delete_type.is_open}
                    on_close={this.close_modals}
                    get_actions={focus_ref => [(
                        <Button
                            key={0}
                            onClick={this.close_modals}
                            color="primary"
                        >
                            Cancel
                        </Button>
                    ), (
                        <Button
                            key={1}
                            onClick={()=> {
                                this.update_state(draft => {
                                    draft.modals.delete_type.confirm_text.reason = VALIDATORS.DELETE_IF_EQUALS(
                                        draft.modals.delete_type.confirm_text.value, this.state.modals.delete_type.meta_type.name
                                    )
                                }).then(() => {
                                    if (this.state.modals.delete_type.confirm_text.reason === "") {
                                        this.props.metadata_api.delete_metadata_type(this.state.modals.delete_type.meta_type)
                                        this.close_modals()
                                    }
                                })
                            }}
                            color="secondary"
                            ref={focus_ref}
                        >
                            Confirm
                        </Button>
                    )]}
                >
                    <Typography>
                        WARNING: Deleting a metadata type will also delete all metadata of that type and is irreversible.
                        Re-enter "{this.state.modals.delete_type.meta_type.name}" to confirm deletion
                    </Typography>
                    <TextField
                        fullWidth
                        error={this.state.modals.delete_type.confirm_text.reason !== ""}
                        helperText={this.state.modals.delete_type.confirm_text.reason}
                        value={this.state.modals.delete_type.confirm_text.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.delete_type.confirm_text.value = evt.target.value
                            })
                        }}
                    />
                </ActionDialog>
            </React.Fragment>
        )
    }
        
}
