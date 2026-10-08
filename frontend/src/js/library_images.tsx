import React from 'react';
import {Button, TextField, Typography} from '@material-ui/core';
import {
    field_info,
    LibraryVersion,
    LibraryVersionsAPI,
} from './types';
import { Grid, Table, TableHeaderRow } from '@devexpress/dx-react-grid-material-ui';
import ActionPanel from './reusable/action_panel';
import {get_field_info_default, get_string_from_error, update_state} from './utils';
import {cloneDeep} from "lodash";
import ActionDialog from "./reusable/action_dialog";
import VALIDATORS from "./validators";
import strings from './locales/curator.en.json';


interface LibraryImagesState {
    modals: LibraryImagesModal
}

interface LibraryImagesModal {
    build_version: {
        is_open: boolean
        to_build: LibraryVersion
        name: field_info<string>
    }
}

interface LibraryImagesProps {
    library_versions_api: LibraryVersionsAPI
    show_toast_message: (message: string, is_success: boolean) => void
} 

export default class LibraryImages extends React.Component<LibraryImagesProps, LibraryImagesState> {
    modal_defaults: LibraryImagesModal
    library_version_default: LibraryVersion
    update_state: (update_func: (draft: LibraryImagesState) => void) => Promise<void>
    constructor(props: Readonly<LibraryImagesProps>) {
        super(props)
        this.library_version_default = {
            id: 0,
            library_name: "",
            version_number: "",
            library_banner: 0,
            created_by: 0,
            metadata_types: []
        }
        this.modal_defaults = {
            build_version: {
                is_open: false,
                to_build: this.library_version_default,
                name: get_field_info_default("")
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
                <Typography variant="h2">{strings.images}</Typography>
                <Grid
                    columns={[
                        {name: "library_name", title: "Name"},
                        {name: "actions", title: "actions", getCellValue: (row: LibraryVersion) => {
                            return <ActionPanel
                                downloadHint={strings.create_export}
                                downloadFn={() => {
                                    this.update_state(draft => {
                                        draft.modals.build_version.is_open = true
                                        draft.modals.build_version.to_build = row
                                    })
                                }}
                            />
                        }}
                    ]}
                    rows={this.props.library_versions_api.state.library_versions}
                >
                    <Table
                        columnExtensions={[
                            {columnName: 'actions', width: 170}
                        ]}
                    />
                    <TableHeaderRow />
                </Grid>
                <ActionDialog
                    title={`Build Library Version ${this.state.modals.build_version.to_build.library_name}?`}
                    open={this.state.modals.build_version.is_open}
                    get_actions={focus_ref => [(
                        <Button
                            key={1}
                            onClick={()=> {
                                this.update_state(draft => {
                                    draft.modals.build_version.name.reason = VALIDATORS.BUILD_IF_EQUAL(
                                        draft.modals.build_version.name.value, this.state.modals.build_version.to_build.library_name
                                    )
                                }).then(() => {
                                    if (this.state.modals.build_version.name.reason === "") {
                                        this.props.library_versions_api.build_version(
                                            this.state.modals.build_version.to_build
                                        ).then(
                                            () => this.props.show_toast_message("Library Built Successfully", true),
                                                err => this.props.show_toast_message(get_string_from_error(err.response.data.error, "Failed to build library"), false),
                                            )
                                            .then(this.close_modals)
                                    }
                                })
                            }}
                            color="secondary"
                        >
                            Build
                        </Button>
                    ), (
                        <Button
                            key={2}
                            onClick={this.close_modals}
                            color="primary"
                            ref={focus_ref}
                        >
                            Cancel
                        </Button>
                    )]}
                >
                    <Typography>This action will take some time. Please enter {this.state.modals.build_version.to_build.library_name} to confirm build</Typography>
                    <TextField
                        fullWidth
                        error={this.state.modals.build_version.name.reason === ""}
                        helperText={this.state.modals.build_version.name.reason}
                        value={this.state.modals.build_version.name.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.build_version.name.value = evt.target.value
                            })
                        }}
                    />
                </ActionDialog>
            </>
        )
    }
}
