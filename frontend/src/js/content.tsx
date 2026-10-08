import React, { Component } from 'react';


import { APP_URLS } from './urls';
import { cloneDeep, isUndefined } from 'lodash';
import ActionDialog from './reusable/action_dialog';
import {Box, Button, Checkbox, TextField, Typography} from '@material-ui/core';
import Axios from 'axios';
import VALIDATORS from './validators';
import { update_state } from './utils';
import ContentModal from './reusable/content_modal';

import { MetadataAPI, SerializedContent, ContentsAPI, SerializedMetadata, metadata_dict } from './types';
import { ViewContentModal } from './reusable/view_content_modal';
import ContentSearch from './reusable/content_search';
import BulkContentModal from "./reusable/bulk_content_modal";
import {Autocomplete, createFilterOptions} from '@material-ui/lab';


interface ContentProps {
    metadata_api: MetadataAPI
    contents_api: ContentsAPI
    show_toast_message: (message: string, is_success: boolean) => void
    close_toast: () => void
    show_loader: () => void
    remove_loader: () => void
}

interface ContentState {
    modals: ContentModals
}

interface ContentModals {
    add: {
        is_open: boolean
    }
    view: {
        is_open: boolean
        row: SerializedContent
    }
    edit: {
        is_open: boolean
        row: SerializedContent
    }
    delete_content: {
        is_open: boolean
    }
    bulk_add: {
        is_open: boolean
    }
    bulk_edit: {
        is_open: boolean
        to_add: metadata_dict
        to_remove: metadata_dict
    }
    column_select: {
        is_open: boolean
    }
    bulk_download: {
        is_open: boolean
    }
}

export default class Content extends Component<ContentProps, ContentState> {

    update_state: (update_func: (draft: ContentState) => void) => Promise<void>

    modal_defaults: ContentModals
    content_defaults: SerializedContent
    auto_complete_filter: any;

    constructor(props: ContentProps) {
        super(props)

        this.update_state = update_state.bind(this)

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
            metadata: [],
            metadata_info: [],
            published_year: "",
            duplicatable: false
        }

        this.modal_defaults = {
            add: {
                is_open: false
            },
            view: {
                is_open: false,
                row: this.content_defaults
            },
            edit: {
                is_open: false,
                row: this.content_defaults
            },
            delete_content: {
                is_open: false,
            },
            bulk_add: {
                is_open: false,
            },
            bulk_edit: {
                is_open: false,
                to_add: {},
                to_remove: {},
            },
            column_select: {
                is_open: false,
            },
            bulk_download: {
                is_open: false,
            }
        }

        this.state = {
            modals: cloneDeep(this.modal_defaults)
        }

        this.auto_complete_filter = createFilterOptions<(string | SerializedMetadata)[]>({
            ignoreCase: true
        })

        this.close_modals = this.close_modals.bind(this)
        this.update_state = this.update_state.bind(this)
    }

    //Resets the state of a given modal. Use this to close the modal.
    close_modals() {
        this.update_state(draft => {
            draft.modals = cloneDeep(this.modal_defaults)
        })
    }

    render() {
        const {
            add,
            view,
            edit,
            bulk_add
        } = this.state.modals
        const {
            metadata_api,
            contents_api
        } = this.props
        return (
            <React.Fragment>
                <Button
                    onClick={_ => {
                        this.update_state(draft => {
                            draft.modals.add.is_open = true
                        })
                    }}
                    style={{
                        marginLeft: "1em",
                        marginBottom: "1em",
                        backgroundColor: "#003c6c",
                        color: "#FFFFFF"
                    }}
                >New Content
                </Button>
                <Button
                    onClick={_ => this.update_state(draft => {
                        draft.modals.delete_content.is_open = true
                    })}
                    style={{
                        marginLeft: "1em",
                        marginBottom: "1em",
                        backgroundColor: "#003c6c",
                        color: "#FFFFFF"
                    }}
                >Delete Selected
                </Button>
                <Button
                    onClick={_ => {
                        this.update_state(draft => {
                            draft.modals.bulk_add.is_open = true
                        })
                    }}
                    style={{
                        marginLeft: "1em",
                        marginBottom: "1em",
                        backgroundColor: "#003c6c",
                        color: "#FFFFFF"
                    }}
                >Add Bulk Content
                </Button>
                <Button
                    onClick={_ => this.props.contents_api.bulk_download()}
                    style={{
                        marginLeft: "1em",
                        marginBottom: "1em",
                        backgroundColor: "#003c6c",
                        color: "#FFFFFF"
                    }}
                >
                    Bulk Download
                </Button>
                <Button
                    onClick={_ => {
                        this.update_state(draft => {
                            draft.modals.bulk_edit.is_open = true
                        })
                    }}
                    style={{
                        marginLeft: "1em",
                        marginBottom: "1em",
                        backgroundColor: "#003c6c",
                        color: "#FFFFFF"
                    }}
                >
                    Bulk Edit
                </Button>
                <Button
                    onClick={_ => {
                        this.update_state(draft => {
                            draft.modals.column_select.is_open = true
                        })
                    }}
                    style={{
                        marginLeft: "1em",
                        marginBottom: "1em",
                        float: "right",
                        marginRight: "1em",
                        //backgroundColor: "#003c6c",
                        //color: "#FFFFFF"
                    }}
                    variant="outlined"
                >
                    Column Select
                </Button>
                <ContentSearch
                    contents_api={contents_api}
                    metadata_api={metadata_api}
                    on_edit={row => {
                        this.update_state(draft => {
                            draft.modals.edit.is_open = true
                            draft.modals.edit.row = row
                        })
                    }}
                    on_view={row => {
                        this.update_state(draft => {
                            draft.modals.view.is_open = true
                            draft.modals.view.row = row
                        })
                    }}
                />
                <ActionDialog
                    title={`Delete ${this.props.contents_api.state.selection.length} Content Item(s)?`}
                    open={this.state.modals.delete_content.is_open}
                    get_actions={(focus_ref: any) => [(
                        <Button
                            key={1}
                            onClick={()=> {
                                this.props.contents_api.delete_selection()
                                this.close_modals()
                            }}
                            color="secondary"
                        >
                            Delete
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
                    <Typography>This action is irreversible</Typography>
                </ActionDialog>
                <ActionDialog
                    title="Bulk Download"
                    open={this.state.modals.bulk_download.is_open}
                    get_actions={(focus_ref: any) => [(
                        <Button
                            key={1}
                            onClick={()=> {
                                this.props.contents_api.bulk_download()
                                this.close_modals()
                            }}
                            color="secondary"
                        >
                            Download
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
                    <Typography>Bulk download may take some time</Typography>
                </ActionDialog>
                <ContentModal
                    is_open={add.is_open}
                    on_close={() => {
                        this.update_state(draft => {
                            draft.modals.add.is_open = false
                        })
                    }}
                    metadata_api={metadata_api}
                    contents_api={this.props.contents_api}
                    modal_type={"add"}
                    validators={{
                        content_file: VALIDATORS.ADD_FILE,
                        title: VALIDATORS.TITLE,
                        display_title: VALIDATORS.DISPLAY_TITLE,
                        description: VALIDATORS.DESCRIPTION,
                        year: VALIDATORS.YEAR,
                        reviewed_on: VALIDATORS.REVIEWED_ON,
                        metadata: VALIDATORS.METADATA,
                        copyright_notes: VALIDATORS.COPYRIGHT_NOTES,
                        rights_statement: VALIDATORS.RIGHTS_STATEMENT,
                        additional_notes: VALIDATORS.ADDITIONAL_NOTES,
                        duplicatable: () => "",
                        active: () => ""
                    }}
                    show_toast_message={this.props.show_toast_message}
                    show_loader={this.props.show_loader}
                    remove_loader={this.props.remove_loader}
                />
                <ContentModal
                    is_open={edit.is_open}
                    on_close={() => {
                        this.update_state(draft => {
                            draft.modals.edit.is_open = false
                        })
                    }}
                    metadata_api={metadata_api}
                    contents_api={this.props.contents_api}
                    modal_type={"edit"}
                    row={edit.row}
                    validators={{
                        content_file: VALIDATORS.EDIT_FILE,
                        title: VALIDATORS.TITLE,
                        display_title: VALIDATORS.DISPLAY_TITLE,
                        description: VALIDATORS.DESCRIPTION,
                        year: VALIDATORS.YEAR,
                        reviewed_on: VALIDATORS.REVIEWED_ON,
                        metadata: VALIDATORS.METADATA,
                        copyright_notes: VALIDATORS.COPYRIGHT_NOTES,
                        rights_statement: VALIDATORS.RIGHTS_STATEMENT,
                        additional_notes: VALIDATORS.ADDITIONAL_NOTES,
                        duplicatable: () => "",
                        active: () => ""
                    }}
                    show_toast_message={this.props.show_toast_message}
                    show_loader={this.props.show_loader}
                    remove_loader={this.props.remove_loader}
                />
                <ViewContentModal
                    is_open={view.is_open}
                    metadata_api={metadata_api}
                    on_close={this.close_modals}
                    row={view.row}
                />
                <BulkContentModal
                    is_open={bulk_add.is_open}
                    on_close={() => {
                        this.update_state(draft => {
                            draft.modals.bulk_add.is_open = false
                        })
                    }}
                    show_toast_message={this.props.show_toast_message}
                    show_loader={this.props.show_loader}
                    remove_loader={this.props.remove_loader}>
               </BulkContentModal>
               <ActionDialog
                    open={this.state.modals.column_select.is_open}
                    title="Show Metadata Columns"
                    get_actions={focus_ref => [(
                        <Button
                            key={2}
                            onClick={() => {
                                this.update_state(draft => {
                                    draft.modals.column_select.is_open = false
                                })
                            }}
                            color="primary"
                            ref={focus_ref}
                        >
                            Close
                        </Button>
                    )]}
                >
                    {["filesize", "content_file", "rights_statement", "description", "modified_on", "reviewed_on", "copyright_notes", "published_year", "duplicatable"].map((name, idx) => {
                        return <Box flexDirection="row" display="flex" key={idx}>
                            <Box key={0}>
                                <Checkbox
                                    checked={this.props.metadata_api.state.show_columns[name]}
                                    onChange={(_, checked) => {
                                        this.props.metadata_api.set_view_metadata_column(draft => {
                                            draft[name] = checked
                                        })
                                    }}
                                />
                            </Box>
                            <Box key={1}>
                                <Typography>{name}</Typography>
                            </Box>
                        </Box>
                    })}
                    {this.props.metadata_api.state.metadata_types.map((metadata_type, idx) => {
                        return <Box flexDirection="row" display="flex" key={idx + 999}>
                            <Box key={0}>
                                <Checkbox
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
                <ActionDialog
                    title={`Bulk Edit ${
                        this.props.contents_api.state.selection.length
                    } Items`}
                    open={this.state.modals.bulk_edit.is_open}
                    get_actions={focus_ref => [(
                        <Button
                            key={2}
                            onClick={() => {
                                this.update_state(draft => {
                                    draft.modals.bulk_edit.is_open = false
                                })
                            }}
                            color="secondary"
                            ref={focus_ref}
                        >
                            Close
                        </Button>
                    ), (
                        <Button
                            key={2}
                            onClick={() => {
                                this.update_state(draft => {
                                    draft.modals.bulk_edit.is_open = false
                                })
                                if (
                                    this.props.contents_api.state.selection.length > 0
                                ) {
                                    this.props.contents_api.bulk_edit(
                                        ([] as SerializedMetadata[]).concat(
                                            ...Object.values(
                                                this.state.modals.bulk_edit.to_add
                                            )
                                        ),
                                        ([] as SerializedMetadata[]).concat(
                                            ...Object.values(
                                                this.state.modals.bulk_edit.to_remove
                                            )
                                        ),
                                    )
                                }
                            }}
                            color="primary"
                            ref={focus_ref}
                        >
                            Edit
                        </Button>
                    )]}
                >
                    <Typography variant="h5">Add Metadata</Typography>
                    {this.props.metadata_api.state.metadata_types
                        .map(metadata_type => <Autocomplete
                            multiple
                            value={this.state.modals.bulk_edit
                                .to_add[metadata_type.name]}
                            onChange={(_evt, value: SerializedMetadata[]) => {
                                //Determine which tokens are real or generated
                                //by the "Add new metadata ..." option
                                let valid_meta = value.filter(
                                    to_check => to_check.id !== 0
                                )
                                let add_meta_tokens = value.filter(
                                    to_check => to_check.id === 0
                                )
                                if (add_meta_tokens.length > 0) {
                                    const to_add = add_meta_tokens[0]
                                    this.props.metadata_api.add_metadata(
                                        to_add.name, metadata_type
                                    ).then(res => {
                                        //add the created metadata to
                                        //valid_metadata with its new id
                                        valid_meta.push(res?.data)
                                        add_meta_tokens = []
                                    })
                                    .then(() => {
                                        this.props.metadata_api.refresh_metadata()
                                    })
                                    .then(() => {
                                        this.update_state(draft => {
                                            draft.modals.bulk_edit
                                                .to_add[metadata_type.name]
                                                = valid_meta
                                        })
                                    })
                                } else {
                                    this.update_state(draft => {
                                        draft.modals.bulk_edit
                                            .to_add[metadata_type.name]
                                            = valid_meta
                                    })
                                }

                            }}
                            filterOptions={(options, params) => {
                                const filtered = this.auto_complete_filter(
                                    options, params
                                )
                                const already_loaded_metadata = this.props
                                    .metadata_api.state
                                    .metadata_by_type[metadata_type.name]
                                    ?.find(match =>
                                        match.name == params.inputValue)
                                if (
                                    params.inputValue !== '' &&
                                    isUndefined(already_loaded_metadata)
                                ) {
                                    filtered.push({
                                        id: 0,
                                        name: params.inputValue,
                                        type: metadata_type.id,
                                        type_name: metadata_type.name
                                    } as SerializedMetadata)
                                }
                                return filtered
                            }}
                            handleHomeEndKeys
                            options={this.props.metadata_api.state
                                .autocomplete_metadata[metadata_type.name] || []}
                            getOptionLabel={option => {
                                if (isUndefined(option)) {
                                    return "undefined"
                                }
                                return option.id === 0 ?
                                    `Add new Metadata "${option.name}"` :
                                    option.name
                            }}
                            renderInput={(params) => (
                                <TextField
                                    {...params}
                                    variant={"standard"}
                                    label={metadata_type.name}
                                    placeholder={metadata_type.name}
                                />
                            )}
                            onInputChange={(_, name) => {
                                this.props.metadata_api
                                    .update_autocomplete(
                                        metadata_type, name
                                    )
                            }}
                        />
                    )}
                    <Typography variant="h5">Remove Metadata</Typography>
                    {this.props.metadata_api.state.metadata_types
                        .map(metadata_type => <Autocomplete
                            multiple
                            value={this.state.modals.bulk_edit
                                .to_remove[metadata_type.name]}
                            onChange={(_evt, value: SerializedMetadata[]) => {
                                //Determine which tokens are real or generated
                                //by the "Add new metadata ..." option
                                let valid_meta = value.filter(
                                    to_check => to_check.id !== 0
                                )
                                let add_meta_tokens = value.filter(
                                    to_check => to_check.id === 0
                                )
                                if (add_meta_tokens.length > 0) {
                                    const to_add = add_meta_tokens[0]
                                    this.props.metadata_api.add_metadata(
                                        to_add.name, metadata_type
                                    ).then(res => {
                                        //add the created metadata to
                                        //valid_metadata with its new id
                                        valid_meta.push(res?.data)
                                        add_meta_tokens = []
                                    })
                                    .then(() => {
                                        this.props.metadata_api.refresh_metadata()
                                    })
                                    .then(() => {
                                        this.update_state(draft => {
                                            draft.modals.bulk_edit
                                                .to_remove[metadata_type.name]
                                                = valid_meta
                                        })
                                    })
                                } else {
                                    this.update_state(draft => {
                                        draft.modals.bulk_edit
                                            .to_remove[metadata_type.name]
                                            = valid_meta
                                    })
                                }

                            }}
                            filterOptions={(options, params) => {
                                const filtered = this.auto_complete_filter(
                                    options, params
                                )
                                const already_loaded_metadata = this.props
                                    .metadata_api.state
                                    .metadata_by_type[metadata_type.name]
                                    ?.find(match =>
                                        match.name == params.inputValue)
                                if (
                                    params.inputValue !== '' &&
                                    isUndefined(already_loaded_metadata)
                                ) {
                                    filtered.push({
                                        id: 0,
                                        name: params.inputValue,
                                        type: metadata_type.id,
                                        type_name: metadata_type.name
                                    } as SerializedMetadata)
                                }
                                return filtered
                            }}
                            handleHomeEndKeys
                            options={this.props.metadata_api.state
                                .autocomplete_metadata[metadata_type.name] || []}
                            getOptionLabel={option => {
                                if (isUndefined(option)) {
                                    return "undefined"
                                }
                                return option.id === 0 ?
                                    `Add new Metadata "${option.name}"` :
                                    option.name
                            }}
                            renderInput={(params) => (
                                <TextField
                                    {...params}
                                    variant={"standard"}
                                    label={metadata_type.name}
                                    placeholder={metadata_type.name}
                                />
                            )}
                            onInputChange={(_, name) => {
                                this.props.metadata_api
                                    .update_autocomplete(
                                        metadata_type, name
                                    )
                            }}
                        />
                    )}
                </ActionDialog>
            </React.Fragment>
        )
    }
}
