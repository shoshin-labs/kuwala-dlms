import React from 'react';
import { Grid, Box, Typography, Link, Button, TextField, Checkbox } from '@material-ui/core';
import { Folder, InsertDriveFile, DoubleArrow } from '@material-ui/icons';
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
import {
    Grid as DataGrid,
    PagingPanel,
    Table,
    TableHeaderRow,
} from "@devexpress/dx-react-grid-material-ui"
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
import { CustomPaging, PagingState } from '@devexpress/dx-react-grid';
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
        }

        this.auto_complete_filter = createFilterOptions<User>({
            ignoreCase: true
        })

        this.update_state = update_state.bind(this)
        this.close_modals = this.close_modals.bind(this)
        this.reset_selection = this.reset_selection.bind(this)
    }

    async close_modals() {
        return this.update_state(draft => {
            draft.modals = cloneDeep(this.modal_defaults)
        })
    }

    async reset_selection() {
        return this.update_state(draft => {
            draft.selected_files = []
            draft.selected_folders = []
        })
    }

    render() {
        return (
            <>
                <Grid container spacing={2} style={{paddingLeft: "15px", paddingRight: "15px"}}>
                    <Grid item sm={12}>
                        <Box display="flex" flexDirection="row">
                            <Typography variant="h3" style={{marginBottom: "5px"}}>Library Versions</Typography>
                            <Button
                                onClick={_ => {
                                    this.update_state(draft => {
                                        draft.modals.add_version.is_open = true
                                    })
                                }}
                                style={{
                                    marginLeft: "1em",
                                    marginBottom: "1em",
                                    backgroundColor: "#003c6c",
                                    color: "#FFFFFF"
                                }}
                            >
                                New Version
                            </Button>
                        </Box>
                        <DataGrid
                            columns={[
                                {name: "actions", title: "Actions", getCellValue: (row: LibraryVersion) => (
                                    <ActionPanel
                                        viewHint="view"
                                        viewFn={() => {
                                            this.props.library_versions_api.enter_version_root(row)
                                        }}
                                        deleteHint="Delete"
                                        deleteFn={() => {
                                            this.update_state(draft => {
                                                draft.modals.delete_version.is_open = true
                                                draft.modals.delete_version.to_delete = row
                                            })
                                        }}
                                        editHint="Edit"
                                        editFn={() => {
                                            this.update_state(draft => {
                                                draft.modals.edit_version.is_open = true
                                                draft.modals.edit_version.version = cloneDeep(row)
                                                draft.modals.edit_version.name.value = row.library_name
                                                draft.modals.edit_version.number.value = row.version_number
                                                const user = this.props.users_api.state.users.find(user => user.id === row.created_by)
                                                if (user !== undefined) {
                                                    draft.modals.edit_version.created_by = user
                                                }
                                            })
                                        }}
                                        imageFn={() => {
                                            this.update_state(draft => {
                                                draft.modals.set_banner.to_set = cloneDeep(row)
                                                draft.modals.set_banner.is_open = true
                                            })
                                        }}
                                        cloneHint="Clone"
                                        cloneFn={() => {
                                            this.props.library_versions_api.clone_version(row)
                                                .then(() => this.props.show_toast_message("Library Successfully Cloned", true))
                                        }}
                                        metadataHint="Set Metadata"
                                        buildFn={() => {
                                            this.update_state(draft => {
                                                draft.modals.set_version_metadata.is_open = true
                                                draft.modals.set_version_metadata.library_version = cloneDeep(row)
                                            })
                                        }}
                                    />
                                )},
                                {name: "library_name", title: "Name"},
                                {name: "version_number", title: "Version"},
                                {name: "created_by_name", title: "Creator", getCellValue: (row: LibraryVersion) => {
                                    const user = this.props.users_api.state.users.find(user => user.id === row.created_by)
                                    return user === undefined ? "None" : user.name
                                }},
                                {name: "created_on", title: "Created On"},
                            ]}
                            
                            rows={this.props.library_versions_api.state.library_versions.map((version: any) => {
                                const cloned = cloneDeep(version)
                                cloned.created_on = format(
                                    new Date(version.created_on),
                                    "MM/dd/yyyy"
                                    )
                                return cloned
                            })}
                        >
                            <Table
                                columnExtensions={[
                                    {columnName: 'actions', width: 200}
                                ]}
                            />
                            <PagingState
                                currentPage={this.props.library_versions_api.state.library_versions_page}
                                onCurrentPageChange={this.props.library_versions_api.set_page}
                                pageSize={this.props.library_versions_api.state.library_versions_page_size}
                                onPageSizeChange={this.props.library_versions_api.set_page_size}
                            />
                            <CustomPaging totalCount={this.props.library_versions_api.state.library_versions_count}/>
                            <TableHeaderRow />
                            <PagingPanel />
                        </DataGrid>
                    </Grid>
                </Grid>
                <Grid container spacing={2} style={{paddingLeft: "15px", paddingRight: "15px", marginTop:"20px"}}>
                    <Grid item sm={6}>
                        {
                            this.props.library_versions_api.state.current_version.id === 0 ?
                                <></> :
                                <Grid item style={{paddingLeft: "2em", paddingRight: "2em"}}>
                                    {(() => {
                                        const library_banner = this.props.library_versions_api.state.current_version.library_banner
                                        if (library_banner !== 0) {
                                            const version_banner = this.props.library_assets_api.state.assets_by_group[2]?.find(asset => asset.id === library_banner)
                                            if (version_banner !== undefined && version_banner.image_file !== null) {
                                                return <img src={version_banner.image_file} style={{maxHeight: "200px", maxWidth: "100%"}}></img>
                                            } else {
                                                return <></>
                                            }
                                        } else {
                                            return <></>
                                        }
                                    })()}
                                    <Box flexDirection="row" display="flex" style={{width: "100%"}}>
                                        <Box style={{
                                            paddingTop: "1em",
                                            paddingBottom: "1em",
                                        }}>
                                            <Typography style={{
                                                fontWeight: "bold",
                                                color: "#003c6c",
                                                fontSize: "16px"
                                            }}>Library Content</Typography>
                                        </Box>
                                        <Box marginLeft="auto"  style={{
                                            paddingTop: "1em",
                                            paddingBottom: "1em",
                                        }}>
                                            <KebabMenu
                                                items={[
                                                    [() => {
                                                        this.update_state(draft => {
                                                            draft.modals.add_folder.is_open = true
                                                        })
                                                    }, "Add Folder"],
                                                    [() => {
                                                        this.update_state(draft => {
                                                            draft.modals.add_module_to_version.is_open = true
                                                        })
                                                    }, "Add Module"]
                                                ]}
                                            />
                                        </Box>
                                    </Box>
                                    <Box flexDirection="row" display="flex">
                                        {
                                            [
                                                (() => {
                                                    const name = this.props.library_versions_api.state.current_version.library_name
                                                    return (
                                                        <Box key={0} flexDirection="row" display="flex">
                                                            <Typography>
                                                                {name === "" ? "None" : (
                                                                    <Link
                                                                        style={{cursor: "pointer"}}
                                                                        onClick={
                                                                            () => this.props.library_versions_api.enter_version_root(
                                                                                this.props.library_versions_api.state.current_version
                                                                            ).then(this.reset_selection)
                                                                        }
                                                                    >
                                                                        {name}
                                                                    </Link>
                                                                )}
                                                            </Typography>
                                                            <DoubleArrow />
                                                        </Box>
                                                    )
                                                })()
                                            ].concat(this.props.library_versions_api.state.path.map((folder, idx) => (
                                                <Box key={idx+1} flexDirection="row" display="flex">
                                                    <Typography>
                                                        <Link
                                                            style={{cursor: "pointer"}}
                                                            onClick={() => {
                                                                this.props.library_versions_api.enter_folder(folder, this.props.library_versions_api.state.path.length - idx - 1).then(this.reset_selection)
                                                            }}
                                                        >
                                                            {folder.folder_name}
                                                        </Link>
                                                    </Typography>
                                                    <DoubleArrow />
                                                </Box>
                                            )))
                                        }
                                    </Box>
                                    {this.props.library_versions_api.state.current_directory.folders.map((folder, idx) => (
                                        <Box key={idx} display="flex" flexDirection="row" width="100%">
                                            <Box>
                                                <Checkbox
                                                    checked={this.state.selected_folders.find(item => item.id === folder.id) !== undefined}
                                                    onChange={(_evt, checked) => {
                                                        this.update_state(draft => {
                                                            draft.selected_folders = checked ?
                                                                draft.selected_folders.concat(folder) :
                                                                draft.selected_folders.filter(item => item.id !== folder.id)
                                                        })
                                                    }}
                                                />
                                            </Box>
                                            <Box style={{paddingTop: "9px"}}>
                                                <Folder />
                                            </Box>
                                            {
                                                folder.logo_img > 0 ?
                                                    <Box style={{paddingTop: "9px", paddingLeft: "3px"}}>
                                                        <img
                                                            src={this.props.library_assets_api.state.assets_by_group[1]?.find(logo => logo.id === folder.logo_img)?.image_file as string}
                                                            style={{maxHeight: "24px"}}
                                                        />
                                                    </Box> :
                                                    <></>
                                            }
                                            <Box style={{paddingTop: "9px", paddingLeft: "3px"}}>
                                                <Typography>
                                                    <Link
                                                        style={{cursor: "pointer"}}
                                                        onClick={() => {
                                                            this.props.library_versions_api.enter_folder(folder).then(this.reset_selection)
                                                        }}
                                                    >
                                                        {folder.folder_name}
                                                    </Link>
                                                </Typography>
                                            </Box>
                                            <Box marginLeft="auto" style={{paddingTop: "9px"}}>
                                                <KebabMenu
                                                    items={([
                                                        [
                                                            () => {
                                                                this.update_state(draft => {
                                                                    draft.modals.delete_folder.is_open = true
                                                                    draft.modals.delete_folder.to_delete = cloneDeep(folder)
                                                                })
                                                            }, "Delete"
                                                        ], [
                                                            () => {
                                                                this.update_state(draft => {
                                                                    draft.modals.rename_folder.is_open = true
                                                                    draft.modals.rename_folder.to_rename = cloneDeep(folder)
                                                                })
                                                            }, "Rename"
                                                        ], [
                                                            () => {
                                                                this.update_state(draft => {
                                                                    draft.modals.move_folder.is_open = true
                                                                    draft.modals.move_folder.to_move = folder.id
                                                                    draft.modals.move_folder.copy = false
                                                                })
                                                            }, "Move"
                                                        ], [
                                                            () => {
                                                                this.update_state(draft => {
                                                                    draft.modals.move_folder.is_open = true
                                                                    draft.modals.move_folder.to_move = folder.id
                                                                    draft.modals.move_folder.copy = true
                                                                })
                                                            }, "Copy"
                                                        ]

                                                    ] as [() => void, string][]).concat(
                                                        //If we are in the top level version add set logo menu items
                                                        this.props.library_versions_api.state.path.length === 0 ?
                                                        [
                                                            [
                                                                () => {
                                                                    this.update_state(draft => {
                                                                        draft.modals.set_folder_logo.is_open = true
                                                                        draft.modals.set_folder_logo.to_change = cloneDeep(folder)
                                                                    })
                                                                }, "Set Logo"
                                                            ]
                                                        ] : []
                                                    )}
                                                />
                                            </Box>
                                        </Box>
                                    ))}
                                    {this.props.library_versions_api.state.current_directory.files.map((content: SerializedContent, idx) => (
                                        <Box
                                            key={this.props.library_versions_api.state.current_directory.folders.length + idx}
                                            display="flex"
                                            flexDirection="row"
                                            width="100%"
                                        >
                                            <Box>
                                                <Checkbox
                                                    checked={this.state.selected_files.find(item => item.id === content.id) !== undefined}
                                                    onChange={(_evt, checked) => {
                                                        this.update_state(draft => {
                                                            draft.selected_files = checked ?
                                                                draft.selected_files.concat(content) :
                                                                draft.selected_files.filter(item => item.id !== content.id)
                                                        })
                                                    }}
                                                />
                                            </Box>
                                            <Box style={{paddingTop: "9px"}}>
                                                <InsertDriveFile />
                                            </Box>
                                            <Box style={{paddingTop: "9px"}}>
                                                <Typography>
                                                    <Link
                                                        style={{cursor: "pointer"}}
                                                        onClick={() => {
                                                            this.update_state(draft => {
                                                                draft.modals.view_content.is_open = true
                                                                draft.modals.view_content.row = content
                                                            })
                                                        }}
                                                    >
                                                        {content.title}
                                                    </Link>
                                                </Typography>
                                            </Box>
                                            <Box marginLeft="auto" minWidth={35} style={{paddingTop: "9px"}}>
                                                <Typography>{prettyBytes(content.filesize === null ? 0 : content.filesize)}</Typography>
                                            </Box>
                                            <Box style={{paddingTop: "9px"}}>
                                                <KebabMenu
                                                    items={[
                                                        [
                                                            () => {
                                                                const path = this.props.library_versions_api.state.path
                                                                this.props.library_versions_api.remove_content_from_folder(
                                                                    path[path.length -1], this.state.selected_files
                                                                ).then(this.reset_selection)
                                                            },
                                                            "Remove Selected"
                                                        ],
                                                        [
                                                            () => {
                                                                this.update_state(draft => {
                                                                    draft.modals.move_content.is_open = true
                                                                })
                                                            },
                                                            "Move Selected"
                                                        ]
                                                    ]}
                                                />
                                            </Box>
                                        </Box>
                                    ))}
                                    {// Displays an empty message if there are no folders or files in the current directory
                                        this.props.library_versions_api.state.current_directory.folders.length === 0 &&
                                        this.props.library_versions_api.state.current_directory.files.length === 0 ? (
                                            <Typography style={{fontStyle: "italic"}}>No Files or Folders</Typography>
                                        ) : <></>
                                    }
                                    <Typography style={{fontWeight: "bold", color: "#003c6c"}}>Library Modules</Typography>
                                    {this.props.library_versions_api.state.modules_in_version.map((module: LibraryModule, idx) => (
                                        <Box
                                            key={this.props.library_versions_api.state.modules_in_version.length + idx}
                                            display="flex"
                                            flexDirection="row"
                                            width="100%"
                                        >
                                            <Box>
                                                <Typography>
                                                    {module.module_name}
                                                </Typography>
                                            </Box>
                                        </Box>
                                    ))}
                                    {// Displays an empty message if there are no modules in the current version
                                        this.props.library_versions_api.state.modules_in_version.length === 0 ? (
                                            <Typography style={{fontStyle: "italic"}}>No Modules added yet</Typography>
                                        ) : <></>
                                    }                        
                                </Grid>
                        }
                    </Grid>
                    <Grid item sm={6}>
                        <Button
                            onClick={() => {
                                const path = this.props.library_versions_api.state.path
                                const cd = path.length > 0 ?
				    path[path.length - 1] :
				    undefined
                                if (cd) {
                                    this.props.contents_api.add_selected_to_folder(cd)
                                }
                            }}
                            style={{
                                marginLeft: "1em",
                                marginBottom: "1em",
                                backgroundColor: "#003c6c",
                                color: "#FFFFFF"
                            }}
                        >Add Selected to CD</Button>
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
                            contents_api={this.props.contents_api}
                            metadata_api={this.props.metadata_api}
                            versions_api={this.props.library_versions_api}
                            selection
                            on_view={row => {
                                this.update_state(draft => {
                                    draft.modals.view_content.is_open = true
                                    draft.modals.view_content.row = row
                                })
                            }}
                        />
                    </Grid>
                </Grid>
                <ActionDialog
                    on_close={this.close_modals}
                    open={this.state.modals.add_version.is_open}
                    title={"Add a Library Version"}
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
                            onClick={() => {
                                this.update_state(draft => {
                                    draft.modals.add_version.name.reason = VALIDATORS.VERSION_NAME(draft.modals.add_version.name.value)
                                    draft.modals.add_version.number.reason = VALIDATORS.VERSION_NUMBER(draft.modals.add_version.number.value)
                                }).then(() => {
                                    return this.props.library_versions_api.add_version(
                                        this.state.modals.add_version.name.value,
                                        this.state.modals.add_version.number.value,
                                        this.state.modals.add_version.created_by.id
                                    ).then(
                                        () => this.props.show_toast_message("Created Successfully", true),
                                        () => this.props.show_toast_message("Failed to Create Version", false)
                                    )
                                }).then(this.close_modals)
                            }}
                            color="primary"
                            ref={focus_ref}
                        >
                            Add
                        </Button>
                    )]}
                >
                    <TextField
                        fullWidth
                        label={"Version Name"}
                        value={this.state.modals.add_version.name.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.add_version.name.value = evt.target.value
                            })
                        }}
                    />
                    <TextField
                        fullWidth
                        label={"Version Number"}
                        value={this.state.modals.add_version.number.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.add_version.number.value = evt.target.value
                            })
                        }}
                    />
                    <Autocomplete
                        value={this.state.modals.add_version.created_by}
                        onChange={(_evt, value: User | null) => {
                            if (value?.id === -1) {
                                this.props.users_api.add_user(value.name).then(() => {
                                    const new_user = this.props.users_api.state.users.find(user => user.name == value.name)
                                    if (new_user !== undefined) {
                                        this.update_state(draft => {
                                            draft.modals.add_version.created_by = new_user
                                        })
                                    }
                                })
                            } else if (!(value === null)) {
                                this.update_state(draft => {
                                    draft.modals.add_version.created_by = value
                                })
                            }
                        }}
                        filterOptions={(options, params) => {
                            const filtered = this.auto_complete_filter(options, params)
                            if (params.inputValue !== "") {
                                filtered.push({
                                    id: -1,
                                    name: params.inputValue
                                } as User)
                            }
                            return filtered
                        }}
                        handleHomeEndKeys
                        options={this.props.users_api.state.users}
                        getOptionLabel={option => {
                            return option.id === -1 ? `Add new User "${option.name}"` : option.name
                        }}
                        renderInput={params => (
                            <TextField
                                {...params}
                                variant={"standard"}
                                placeholder={"User"}
                            />
                        )}
                    />
                </ActionDialog>
                <ActionDialog
                    on_close={this.close_modals}
                    open={this.state.modals.edit_version.is_open}
                    title={"Edit a Library Version"}
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
                            onClick={() => {
                                this.update_state(draft => {
                                    draft.modals.edit_version.name.reason = VALIDATORS.VERSION_NAME(draft.modals.edit_version.name.value)
                                    draft.modals.edit_version.number.reason = VALIDATORS.VERSION_NUMBER(draft.modals.edit_version.number.value)
                                }).then(() => {
                                    return this.props.library_versions_api.update_version(
                                        this.state.modals.edit_version.version,
                                        this.state.modals.edit_version.name.value || undefined,
                                        this.state.modals.edit_version.number.value || undefined,
                                        this.state.modals.edit_version.created_by.id !== 0 ? this.state.modals.edit_version.created_by : undefined
                                    ).then(
                                        () => this.props.show_toast_message("Edited Successfully", true),
                                        err => this.props.show_toast_message(get_string_from_error(err.response.data.error, "Failed to edit version"), false),
                                    )
                                }).then(this.close_modals)
                            }}
                            color="primary"
                            ref={focus_ref}
                        >
                            Edit
                        </Button>
                    )]}
                >
                    <TextField
                        fullWidth
                        label={"Version Name"}
                        value={this.state.modals.edit_version.name.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.edit_version.name.value = evt.target.value
                            })
                        }}
                    />
                    <TextField
                        fullWidth
                        label={"Version Number"}
                        value={this.state.modals.edit_version.number.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.edit_version.number.value = evt.target.value
                            })
                        }}
                    />
                    <Autocomplete
                        value={this.state.modals.edit_version.created_by}
                        onChange={(_evt, value: User | null) => {
                            if (value?.id === -1) {
                                this.props.users_api.add_user(value.name).then(() => {
                                    const new_user = this.props.users_api.state.users.find(user => user.name == value.name)
                                    if (new_user !== undefined) {
                                        this.update_state(draft => {
                                            draft.modals.edit_version.created_by = new_user
                                        })
                                    }
                                })
                            } else if (!(value === null)) {
                                this.update_state(draft => {
                                    draft.modals.edit_version.created_by = value
                                })
                            }
                        }}
                        filterOptions={(options, params) => {
                            const filtered = this.auto_complete_filter(options, params)
                            if (params.inputValue !== "") {
                                filtered.push({
                                    id: -1,
                                    name: params.inputValue
                                } as User)
                            }
                            return filtered
                        }}
                        handleHomeEndKeys
                        options={this.props.users_api.state.users}
                        getOptionLabel={option => {
                            return option.id === -1 ? `Add new User "${option.name}"` : option.name
                        }}
                        renderInput={params => (
                            <TextField
                                {...params}
                                variant={"standard"}
                                placeholder={"User"}
                            />
                        )}
                    />
                </ActionDialog>
                <ActionDialog
                    on_close={this.close_modals}
                    open={this.state.modals.set_banner.is_open}
                    title={"Set Library Banner"}
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
                        {this.props.library_assets_api.state.assets_by_group[2]?.map((asset, idx) => {
                            return (
                                <Grid
                                    key={idx}
                                    item
                                    style={this.state.modals.set_banner.to_set.library_banner === asset.id
                                    ? {backgroundColor: "#e6f0f6"} : undefined}
                                    onClick={_ => {
                                        this.props.library_versions_api.set_version_image(this.state.modals.set_banner.to_set, asset)
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
                    open={this.state.modals.set_folder_logo.is_open}
                    title={"Set Folder Logo"}
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
                                    style={this.state.modals.set_folder_logo.to_change.logo_img === asset.id
                                    ? {backgroundColor: "#e6f0f6"} : undefined}
                                    onClick={_ => {
                                        this.props.library_versions_api.set_folder_logo(this.state.modals.set_folder_logo.to_change, asset)
                                        .then(this.close_modals)
                                        .then(this.props.library_versions_api.refresh_current_directory)
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
                    title={`Delete Version ${this.state.modals.delete_version.to_delete.library_name}?`}
                    open={this.state.modals.delete_version.is_open}
                    get_actions={focus_ref => [(
                        <Button
                            key={1}
                            onClick={()=> {
                                this.update_state(draft => {
                                    draft.modals.delete_version.name.reason = VALIDATORS.DELETE_IF_EQUALS(
                                        draft.modals.delete_version.name.value, this.state.modals.delete_version.to_delete.library_name
                                    )
                                }).then(() => {
                                    if (this.state.modals.delete_version.name.reason === "") {
                                        this.props.library_versions_api.delete_version(
                                            this.state.modals.delete_version.to_delete
                                        ).then(this.close_modals)
                                    }
                                })
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
                    <Typography>This action is irreversible. Please enter {this.state.modals.delete_version.to_delete.library_name} to confirm deletion</Typography>
                    <TextField
                        fullWidth
                        error={this.state.modals.delete_version.name.reason === ""}
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
                    title={"Add New Folder"}
                    get_actions={focus_ref => [(
                        <Button
                            key={2}
                            onClick={this.close_modals}
                            color="secondary"
                            ref={focus_ref}
                        >
                            Cancel
                        </Button>
                    ), (
                        <Button
                            key={1}
                            onClick={() => {
                                this.update_state(draft => {
                                    draft.modals.add_folder.name.reason = VALIDATORS.FOLDER_NAME(draft.modals.add_folder.name.value)
                                }).then(() => {
                                    if (this.state.modals.add_folder.name.reason === "") {
                                        const path = this.props.library_versions_api.state.path
                                        this.props.library_versions_api.create_child_folder(
                                            path.length > 0 ?
                                                path[path.length - 1] as LibraryFolder :
                                                this.props.library_versions_api.state.current_version,
                                            this.state.modals.add_folder.name.value
                                        )
                                            .then(this.close_modals)
                                    }
                                })
                            }}
                            color="primary"
                        >
                            Add
                        </Button>
                    )]}
                    open={this.state.modals.add_folder.is_open}
                >
                    <TextField
                        label={"Folder Name"}
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
                    title={`Delete Folder ${this.state.modals.delete_folder.to_delete.folder_name}`}
                    open={this.state.modals.delete_folder.is_open}
                    get_actions={focus_ref => [(
                        <Button
                            key={1}
                            onClick={()=> {
                                this.update_state(draft => {
                                    draft.modals.delete_folder.name.reason = VALIDATORS.DELETE_IF_EQUALS(
                                        draft.modals.delete_folder.name.value, this.state.modals.delete_folder.to_delete.folder_name
                                    )
                                }).then(() => {
                                    if (this.state.modals.delete_folder.name.reason === "") {
                                        this.props.library_versions_api.delete_folder(
                                            this.state.modals.delete_folder.to_delete
                                        ).then(this.close_modals)
                                    }
                                })
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
                    <Typography>This action is irreversible. Please enter {this.state.modals.delete_folder.to_delete.folder_name} to confirm deletion</Typography>
                    <TextField
                        label={"Folder Name"}
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
                    title={`Rename Folder ${this.state.modals.rename_folder.to_rename.folder_name}`}
                    open={this.state.modals.rename_folder.is_open}
                    get_actions={focus_ref => [(
                        <Button
                            key={2}
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
                                    draft.modals.rename_folder.name.reason = VALIDATORS.FOLDER_NAME(
                                        draft.modals.rename_folder.name.value
                                    )
                                }).then(() => {
                                    if (this.state.modals.rename_folder.name.reason === "") {
                                        this.props.library_versions_api.rename_folder(
                                            this.state.modals.rename_folder.to_rename, this.state.modals.rename_folder.name.value
                                        ).then(this.close_modals)
                                    }
                                })
                            }}
                            color="secondary"
                            ref={focus_ref}
                        >
                            Rename
                        </Button>
                    )]}
                >
                    <TextField
                        label={"New Folder Name"}
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
                    title={`Move Contents ${this.state.selected_files.map(content => content.file_name).join(", ")}`}
                    open={this.state.modals.move_content.is_open}
                    get_actions={focus_ref => [(
                        <Button
                            key={2}
                            onClick={this.close_modals}
                            color="primary"
                            ref={focus_ref}
                        >
                            Cancel
                        </Button>
                    ), (
                        <Button
                            key={1}
                            onClick={()=> {
                                const path = this.props.library_versions_api.state.path
                                console.log("path: ", path[path.length - 1]);
                                console.log("selected: ", this.state.selected_files);
                                this.props.library_versions_api.remove_content_from_folder(
                                    path[path.length - 1],
                                    this.state.selected_files
                                ).then(() => this.props.library_versions_api.add_content_to_folder(
                                    this.state.modals.move_content.destination_folder[0],
                                    this.state.selected_files
                                )).then(() => this.reset_selection()).then(this.close_modals)
                            }}
                            color="secondary"
                        >
                            Move
                        </Button>
                    )]}
                >
                    <Autocomplete
                        value={this.state.modals.move_content.destination_folder}
                        onChange={(_evt:any, value: [LibraryFolder, string] | null) => {
                            if (value !== null) {
                                this.update_state(draft => {
                                    draft.modals.move_content.destination_folder = value
                                })
                            }
                        }}
                        filterOptions={(options: any, params: any) => {
                            return this.auto_complete_filter(options, params)
                        }}
                        handleHomeEndKeys   
                        options={this.props.library_versions_api.state.folders_in_version}
                        getOptionLabel={option => option[1]}
                        renderInput={params => (
                            <TextField
                                {...params}
                                variant={"standard"}
                                placeholder={"Destination"}
                            />
                        )}
                    />
                </ActionDialog>
                <ActionDialog
                    title={`Choose a Module to add to the Library`}
                    open={this.state.modals.add_module_to_version.is_open}
                    get_actions={focus_ref => [(
                        <Button
                            key={2}
                            onClick={this.close_modals}
                            color="primary"
                        >
                            Cancel
                        </Button>
                    ), (
                        <Button
                            key={1}
                            onClick={()=> {
                                this.props.library_versions_api.add_module_to_version(
                                    this.props.library_versions_api.state.current_version,
                                    this.state.modals.add_module_to_version.to_add
                                ).then(this.close_modals)
                            }}
                            color="secondary"
                            ref={focus_ref}
                        >
                            Add
                        </Button>
                    )]}
                >
                    <Autocomplete
                        value={this.state.modals.add_module_to_version.to_add}
                        onChange={(_evt, value: LibraryModule | null) => {
                            if (!(value === null)) {
                                this.update_state(draft => {
                                    draft.modals.add_module_to_version.to_add = value
                                })
                            }
                        }}
                        filterOptions={(options, params) => {
                            const filtered = this.auto_complete_filter(options, params)
                            if (params.inputValue !== "") {
                                filtered.push({
                                    id: -1,
                                    module_name: params.inputValue
                                } as LibraryModule)
                            }
                            return filtered
                        }}
                        handleHomeEndKeys
                        options={this.props.library_modules_api.state.library_modules}
                        getOptionLabel={option => option.module_name}
                        renderInput={params => (
                            <TextField
                                {...params}
                                variant={"standard"}
                                placeholder={"Module"}
                            />
                        )}
                    />
                </ActionDialog>
                <ActionDialog
                    title={`Set Metadata Types of Version ${this.state.modals.set_version_metadata.library_version.library_name}`}
                    open={this.state.modals.set_version_metadata.is_open}
                    get_actions={focus_ref => [(
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
                    {this.props.metadata_api.state.metadata_types.map((metadata_type, idx) => {
                        return <Box flexDirection="row" display="flex" key={idx}>
                            <Box>
                                <Checkbox
                                    checked={this.state.modals.set_version_metadata.library_version.metadata_types.find(id => id === metadata_type.id) !== undefined}
                                    onChange={(_evt, checked) => {
                                        (checked ?
                                            this.props.library_versions_api.add_metadata_type_to_version :
                                            this.props.library_versions_api.remove_metadata_type_to_version)(
                                                this.state.modals.set_version_metadata.library_version,
                                                metadata_type
                                            )
                                            .then(version => {
                                                console.log(checked, version)
                                                this.update_state(draft => {
                                                    draft.modals.set_version_metadata.library_version = version
                                                })
                                            })
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
                        "Copy Folder To" : "Move Folder To"}
                    open={this.state.modals.move_folder.is_open}
                    get_actions={focus_ref => [(
                        <Button
                            key={1}
                            onClick={this.close_modals}
                            color="primary"
                            ref={focus_ref}
                        >
                            Cancel
                        </Button>
                    ), (
                        <Button
                            key={2}
                            onClick={() => {
                                this.props.library_versions_api.move_folder(
                                    this.state.modals.move_folder.to_move,
                                    this.state.modals.move_folder.copy,
                                    this.state.modals.move_folder
                                        .destination_folder.id === 0 ||
                                        this.state.modals.move_folder
                                        .top_level_folder ?
                                        undefined :
                                        this.state.modals.move_folder
                                            .destination_folder.id,
                                    this.state.modals.move_folder
                                        .destination_library.id === 0 ?
                                        undefined :
                                        this.state.modals.move_folder.destination_library.id,
                                )
                                this.close_modals()
                            }}
                            color="secondary"
                            ref={focus_ref}
                        >
                            {this.state.modals.move_folder.copy ? "Copy" : "Move"}
                        </Button>
                    )]}
                >
                    <Autocomplete
                        style={{
                            width: "100%", minWidth: 0
                        }}
                        freeSolo
                        value={this.state.modals.move_folder.destination_library}
                        options={this.props.library_versions_api.state
                            .autocomplete_versions}
                        onChange={(_, input) => {
                            if (isString(input)) {
                                this.update_state(draft => {
                                    draft.modals.move_folder.destination_library_input
                                        = input
                                })
                            } else if (input !== null) {
                                this.update_state(draft => {
                                    draft.modals.move_folder.destination_library
                                        = input
                                })
                                console.log("updating autocomplete")
                                this.props.library_versions_api
                                    .update_folder_autocomplete(input)
                            }
                        }}
                        onInputChange={(_, prefix) => this.props.library_versions_api
                            .update_version_autocomplete(prefix)}
                        getOptionLabel={version => version.id == 0 ? "" :
                            `${version.library_name} @ ${version.version_number}`}
                        filterOptions={(options, params) => {
                            return this.auto_complete_filter(options, params)
                        }}
                        renderInput={params => <TextField
                            {...params}
                            variant="standard"
                            placeholder="Destination Version"
                        />}
                    />
                    <Typography>Top Level Folder?</Typography>
                    <Checkbox
                        checked={this.state.modals.move_folder.top_level_folder}
                        onChange={(_, checked) => this.update_state(draft => {
                            draft.modals.move_folder.top_level_folder = checked
                        })}
                    />
                    {this.state.modals.move_folder.top_level_folder ?
                    <></> :
                    <Autocomplete
                        value={this.state.modals.move_folder.destination_folder}
                        options={
                            this.props.library_versions_api.state.autocomplete_folders
                        }
                        onChange={(_, folder) => {
                            if (folder) this.update_state(draft => {
                                draft.modals.move_folder.destination_folder = folder
                            })
                        }}
                        getOptionLabel={folder =>
                            folder.breadcrumb?.map(folder => folder.folder_name)
                            .join("/") || ""}
                        filterOptions={(options, params) => {
                            return this.auto_complete_filter(options, params)
                        }}
                        renderInput={params => <TextField
                            {...params}
                            variant="standard"
                            placeholder="Destination Folder"
                        />}
                    />}
                </ActionDialog>
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
            </>
        )
    }
}
