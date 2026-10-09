import { Sorting } from '@devexpress/dx-react-grid';
import Axios from 'axios';
import { format } from 'date-fns';
import { APIs, AssetGroup, ContentsProviderState, content_fields, content_filters, LibraryAsset, LibraryAssetsState, LibraryFolder, LibraryVersion, LibraryVersionsState, MetadataProviderState, search_state, SerializedContent, SerializedMetadata, SerializedMetadataType, User, UserProviderState, LibraryModulesState, LibraryModule,
UtilsState, 
show_metadata_column,
metadata_dict} from '../types';
import { APP_URLS, get_data } from '../urls';
import { update_state } from '../utils';
import { cloneDeep, get, range } from 'lodash';
import React from 'react';
import strings from '../locales/curator.en.json';
import { debounce } from "lodash";

interface GlobalStateProps {
    render: React.ComponentType<{
        apis: APIs
    }>
}
interface GlobalStateState {
    initializing: boolean
    initialization_error: boolean
    contents_api: ContentsProviderState
    metadata_api: MetadataProviderState
    library_assets_api: LibraryAssetsState
    library_versions_api: LibraryVersionsState
    users_api: UserProviderState
    library_modules_api: LibraryModulesState
    utils_api: UtilsState
}

export default class GlobalState extends React.Component<GlobalStateProps, GlobalStateState> {
    search_defaults: search_state
    update_state: (update_func: (draft: GlobalStateState) => void) => Promise<void>
    debounced_load_rows: () => Promise<any>
    constructor(props: GlobalStateProps) {
        super(props)

        this.search_defaults = {
            active: "active",
            copyright_notes: "",
            file_size_from: null,
            file_size_to: null,
            filename: "",
            metadata: {},
            reviewed_from: null,
            reviewed_to: null,
            title: "",
            display_title: "",
            years_from: null,
            years_to: null,
            duplicatable: "all"
        }

        const versions_page_sizes = [5]
        const contents_page_sizes = [10, 25, 100]

        this.state = {
            initializing: true,
            initialization_error: false,
            contents_api: {
                last_request_timestamp: 0,
                display_rows: [],
                loaded_content: [],
                page: 0,
                page_size: contents_page_sizes[0],
                total_count: 0,
                search: cloneDeep(this.search_defaults),
                filter_out: [],
                selection: [],
                page_sizes: contents_page_sizes,
                sorting: [],
                show_columns: {},
            },
            metadata_api: {
                metadata_by_type: {},
                page_by_type: {},
                metadata_types: [],
                show_columns: {},
                autocomplete_metadata: {},
            },
            library_assets_api: {
                assets: [],
                assets_by_group: {},
                group_name: {
                    1: "logo",
                    2: "version",
                }
            },
            library_versions_api: {
                library_versions: [],
                folders_in_version: [],
                library_versions_page: 0,
                library_versions_page_size: versions_page_sizes[0],
                library_versions_count: 0,
                current_directory: {
                    folders: [],
                    files: []
                },
                current_version: {
                    id: 0,
                    library_name: "",
                    version_number: "",
                    library_banner: 0,
                    created_by: 0,
                    metadata_types: []
                },
                path: [],
                modules_in_version: [],
                versions_page_sizes: versions_page_sizes,
                autocomplete_folders: [],
                autocomplete_versions: []
            },
            users_api: {
                users: []
            },
            library_modules_api: {
                library_modules: []
            },
            utils_api: {
                outstanding_requests: new Set(),
                disk_total: 0,
                disk_used: 0,
                disk_free: 0
            }
        }

        this.handle_loader = this.handle_loader.bind(this)
        
        //ContentsAPI
        this.delete_content = this.handle_loader(this.delete_content.bind(this))
        this.load_content_rows = this.handle_loader(this.load_content_rows.bind(this))
        this.debounced_load_rows = debounce(
            this.handle_loader(this.load_content_rows.bind(this)),
            600, {leading: true, trailing: true})
        this.add_content = this.handle_loader(this.add_content.bind(this))
        this.edit_content = this.handle_loader(this.edit_content.bind(this))
        this.update_search_state = this.update_search_state.bind(this)
        this.set_selection = this.set_selection.bind(this)
        this.reset_search = this.reset_search.bind(this)
        this.add_selected_to_folder = this.handle_loader(this.add_selected_to_folder.bind(this))
        this.set_contents_page = this.set_contents_page.bind(this)
        this.set_contents_page_size = this.set_contents_page_size.bind(this)
        this.set_sorting = this.set_sorting.bind(this)
        this.bulk_download = this.bulk_download.bind(this)
        this.delete_selection = this.delete_selection.bind(this)
        this.bulk_edit = this.bulk_edit.bind(this)

        //MetadataAPI
        this.refresh_metadata = this.handle_loader(this.refresh_metadata.bind(this))
        this.add_metadata_type = this.handle_loader(this.add_metadata_type.bind(this))
        this.edit_metadata_type = this.handle_loader(this.edit_metadata_type.bind(this))
        this.delete_metadata_type = this.handle_loader(this.delete_metadata_type.bind(this))
        this.add_metadata = this.handle_loader(this.add_metadata.bind(this))
        this.edit_metadata = this.handle_loader(this.edit_metadata.bind(this))
        this.delete_metadata = this.handle_loader(this.delete_metadata.bind(this))
        this.set_view_metadata_column = this.set_view_metadata_column.bind(this)
        this.set_metadata_page = this.set_metadata_page.bind(this)
        this.set_metadata_page_size = this.set_metadata_page_size.bind(this)
        this.update_autocomplete = this.update_autocomplete.bind(this)

        //Library Assets API
        this.add_library_asset = this.handle_loader(this.add_library_asset.bind(this))
        this.edit_library_asset = this.handle_loader(this.edit_library_asset.bind(this))
        this.delete_library_asset = this.handle_loader(this.delete_library_asset.bind(this))
        this.refresh_assets = this.handle_loader(this.refresh_assets.bind(this))

        //Library Versions API
        this._update_current_directory = this.handle_loader(this._update_current_directory.bind(this))
        this.refresh_current_directory = this.handle_loader(this.refresh_current_directory.bind(this))
        this.refresh_library_versions = this.handle_loader(this.refresh_library_versions.bind(this))
        this.enter_version_root = this.handle_loader(this.enter_version_root.bind(this))
        this.enter_folder = this.handle_loader(this.enter_folder.bind(this))
        this.enter_parent = this.handle_loader(this.enter_parent.bind(this))
        this.add_version = this.handle_loader(this.add_version.bind(this))
        this.set_version_image = this.handle_loader(this.set_version_image.bind(this))
        this.update_version = this.handle_loader(this.update_version.bind(this))
        this.create_child_folder = this.handle_loader(this.create_child_folder.bind(this))
        this.delete_folder = this.handle_loader(this.delete_folder.bind(this))
        this.rename_folder = this.handle_loader(this.rename_folder.bind(this))
        this.set_folder_banner = this.handle_loader(this.set_folder_banner.bind(this))
        this.set_folder_logo = this.handle_loader(this.set_folder_logo.bind(this))
        this.clone_version = this.handle_loader(this.clone_version.bind(this))
        this.remove_content_from_folder = this.handle_loader(this.remove_content_from_folder.bind(this))
        this.refresh_folders_in_current_version = this.handle_loader(this.refresh_folders_in_current_version.bind(this))
        this.add_content_to_folder = this.handle_loader(this.add_content_to_folder.bind(this))
        this.add_module_to_version = this.handle_loader(this.add_module_to_version.bind(this))
        this.remove_module_from_version = this.handle_loader(this.remove_module_from_version.bind(this))
        this.refresh_modules_in_current_version = this.handle_loader(this.refresh_modules_in_current_version.bind(this))
        this.set_versions_page = this.handle_loader(this.set_versions_page.bind(this))
        this.set_versions_page_size = this.handle_loader(this.set_versions_page_size.bind(this))
        this.add_metadata_type_to_version = this.handle_loader(this.add_metadata_type_to_version.bind(this))
        this.remove_metadata_type_to_version = this.handle_loader(this.remove_metadata_type_to_version.bind(this))
        this.reset_to_library_defaults = this.handle_loader(this.reset_to_library_defaults.bind(this))
        this.move_folder = this.handle_loader(this.move_folder.bind(this))
        this.update_folder_autocomplete = this.update_folder_autocomplete.bind(this)
        this.update_version_autocomplete = this.update_version_autocomplete.bind(this)
        this.build_version = this.handle_loader(this.build_version.bind(this))

        
        //Users API
        this.refresh_users = this.handle_loader(this.refresh_users.bind(this))
        this.add_user = this.handle_loader(this.add_user.bind(this))

        //Library Modules API
        this.refresh_library_modules = this.handle_loader(this.refresh_library_modules.bind(this))
        this.set_module_logo = this.handle_loader(this.set_module_logo.bind(this))
        this.add_module = this.handle_loader(this.add_module.bind(this))
        this.edit_module = this.handle_loader(this.edit_module.bind(this))

        //Utils API
        this.get_disk_info = this.handle_loader(this.get_disk_info.bind(this))

        this.update_state = update_state.bind(this)
        this.get_content_filters = this.get_content_filters.bind(this)
    }

    //Loader Decorator
    handle_loader<T>(func: (...args: any[]) => Promise<T>): (...args: any[]) => Promise<T> {
        return async (...args) => {
            const key = {}
            await this.update_state(draft => {
                draft.utils_api.outstanding_requests.add(key)
            })
            try {
                var result: T = await func(...args)
                console.log(result)
            } catch(e) {
                await this.update_state(draft => {
                    draft.utils_api.outstanding_requests.delete(key)
                })
                console.log("Throwing E")
                console.error(e)
                throw e
            }
            await this.update_state(draft => {
                draft.utils_api.outstanding_requests.delete(key)
            })
            return result
        }
    }

    componentDidMount() {
        // Don't present failed or incomplete catalogue requests as empty lists.
        Promise.all([
            Axios.get(APP_URLS.CSRF_TOKEN).then(res => {
                Axios.defaults.headers.common["X-CSRFToken"] = res.data.data
            }),
            this.refresh_metadata().then(this.load_content_rows),
            this.refresh_assets(),
            this.refresh_library_versions(),
            this.refresh_users(),
            this.refresh_library_modules(),
            this.update_version_autocomplete("")
        ]).then(() => this.update_state(draft => { draft.initializing = false }),
            () => this.update_state(draft => {
                draft.initializing = false
                draft.initialization_error = true
            }))
        // Disk information is optional and can be retried in its own tab.
        this.get_disk_info().catch(() => {})
    }

    // CONTENTS ----------------------------------------------------

    //Reset the search back to default
    async reset_search() {
        return this.update_state(draft => {
            draft.contents_api.search = cloneDeep(this.search_defaults)
        }).then(() => this.set_contents_page(0))
    }

    //Setter for selection.
    //Selection indicates the indexes of selected rows in the libraries tab
    async set_selection(selection: number[]) {
        return this.update_state(draft => {
            draft.contents_api.selection = selection
        })
    }   

    //Add the rows indicated by the selection to a given folder
    async add_selected_to_folder(folder: LibraryFolder) {
        await Axios.post(APP_URLS.LIBRARY_FOLDER_ADD_CONTENT(folder.id), {
            content_ids: this.state.contents_api.selection.map(idx =>
                this.state.contents_api.loaded_content[idx]?.id
            ).filter(v => v !== undefined)
        })
        return Promise.all([
            this.load_content_rows(),
            this.refresh_current_directory()
        ])
    }

    get_content_filters(): content_filters {
        
        const search = this.state.contents_api.search
        const active_filter = {
            "all": undefined,
            "active": true,
            "inactive": false
        }[search.active]

        //Converts years_from and years_to to a two array of the integers.
        //Validates that years_from and years_to are valid integers and years_from <= years_to
        //If invalid years will be undefined
        const years: content_filters["years"] = (
            search.years_from !== null && search.years_to !== null && search.years_from >= search.years_to
        ) ? undefined : [search.years_from, search.years_to]
        const file_sizes: content_filters["file_sizes"] = (
            search.file_size_from !== null && search.file_size_to !== null && search.file_size_from >= search.file_size_to
        ) ? undefined : [search.file_size_from, search.file_size_to]
        const reviewed_on: content_filters["reviewed_on"] = (
            search.reviewed_from !== null && search.reviewed_to !== null && search.reviewed_from >= search.reviewed_to
        ) ? undefined : [search.reviewed_from, search.reviewed_to]

        return {
            years,
            file_sizes,
            reviewed_on,
            title: search.title,
            display_title: search.display_title,
            copyright_notes: search.copyright_notes,
            //Turn metadata_dict back to array of integers for search
            metadata: Object.keys(search.metadata).reduce((prev, current) => {
                return prev.concat(search.metadata[current].map(metadata => metadata.id))
            }, [] as number[]),
            active: active_filter,
            filename: search.filename,
            duplicatable: {"all": undefined, "yes": true, "no": false}[search.duplicatable],
            sort: this.state.contents_api.sorting.length > 0 ? `${this.state.contents_api.sorting[0].columnName},${this.state.contents_api.sorting[0].direction}` : undefined
        }
    }

    bulk_download() {
        return window.open(APP_URLS.CONTENT_BULK_DOWNLOAD(this.get_content_filters()))
    }

    //Load content rows by page, with sorting and filters
    load_content_rows = async (): Promise<any> => {

        const req_timestamp = Date.now()

        const exclude_version = this.state.library_versions_api.current_version.id === 0 ?
            undefined : this.state.library_versions_api.current_version

        try {
            // Add one to page because dx-react-grid and django paging start from different places
            const data: any = await get_data(APP_URLS.CONTENT_PAGE(
                this.state.contents_api.page + 1,
                this.state.contents_api.page_size,
                this.get_content_filters(), exclude_version
            ))

            if (req_timestamp >= this.state.contents_api.last_request_timestamp) {
                //Adds the MetadataTypes defined in content_display as a key to each item in row so it can be easily accessed
                //by dx-react-grid later
                //Unfortunately this means we have to store each content twice, once as SerializedContent and again as any
                const rows = data.results as SerializedContent[]
                const display_rows = cloneDeep(rows).map((row: any) => {
                    row.metadata_info.map((info: SerializedMetadata) => {
                        if (this.state.metadata_api.metadata_types.map(type => type.name).includes(info.type_name)) {
                            const new_metadata_entry = get(row, [info.type_name], []).concat([info.name])
                            row[info.type_name] = new_metadata_entry
                        }
                    })
                    this.state.metadata_api.metadata_types.map(type => {
                        row[type.name] = get(row, [type.name], []).join(", ")
                    })
                    return row
                })

                return this.update_state(draft => {
                    draft.contents_api.last_request_timestamp = req_timestamp
                    draft.contents_api.loaded_content = rows
                    draft.contents_api.display_rows = display_rows
                    draft.contents_api.total_count = data.count
                    draft.contents_api.selection = []
                })
            }
        } catch(err) {
            if ((err?.data?.error?.detail || err?.data?.detail || err?.detail) === "Invalid page." && this.state.contents_api.page > 0) {
                return this.update_state(draft => {
                    draft.contents_api.page = draft.contents_api.page - 1
                }).then(this.load_content_rows)
            }
            throw err
        }
        // Only update the state if the request was sent after the most recent received request
    }

    //Creates new content record from content_fields
    async add_content(fields: content_fields) {
        const form_data = new FormData()
        form_data.append('title', fields.title)
        form_data.append('display_title', fields.display_title)
        if (!fields.content_file) {
            Promise.reject("No Content File")
        } else {
            form_data.append('content_file', fields.content_file)
        }

        if (fields.reviewed_on) {
            form_data.append("reviewed_on", format(fields.reviewed_on, "yyyy-MM-dd"))
        }

        form_data.append('description', fields.description)
        form_data.append('published_date', `${fields.year}-01-01`)
        form_data.append('active', "true")

        Object.entries(fields.metadata).map(entry => {
            entry[1].map(metadata => {
                form_data.append("metadata", `${metadata.id}`)
            })
        })

        return Axios.post(APP_URLS.CONTENT, form_data, {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        }).then(this.load_content_rows)
    }
    
    //Update existing content record from content_fields
    async edit_content(fields: content_fields, to_edit: SerializedContent) {
        const form_data = new FormData()
        if (fields.content_file) {
            form_data.append("content_file", fields.content_file)
        }
        form_data.append('title', fields.title)
        form_data.append('display_title', fields.display_title)
        form_data.append('description', fields.description)
        form_data.append('published_date', `${fields.year}-01-01`)
        if (fields.reviewed_on) {
            form_data.append("reviewed_on", format(fields.reviewed_on, "yyyy-MM-dd"))
        }
        
        form_data.append('active', to_edit.active ? "true" : "false")

        Object.entries(fields.metadata).map(entry => {
            entry[1].map(metadata => {
                form_data.append("metadata", `${metadata.id}`)
            })
        })

        return Axios.patch(APP_URLS.CONTENT_ITEM(to_edit.id), form_data, {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        }).then(this.load_content_rows)
    }

    //Delete existing content record
    async delete_content(to_delete: SerializedContent) {
        return Axios.delete(APP_URLS.CONTENT_ITEM(to_delete.id))
            .then(this.load_content_rows)
    }
    
    // Delete content items selected
    async delete_selection() {
        return Promise.all(this.state.contents_api.selection
            .map(selected_idx => this.state.contents_api.loaded_content[selected_idx])
            .map(this.delete_content))
            .then(this.load_content_rows)
    }

    //Exposes the update_state function only for the search state
    //Used to edit search fields in a similar way as update_state
    async update_search_state(update_func: (draft: search_state) => void) {
        return this.update_state(draft => {
            update_func(draft.contents_api.search)
        })
            .then(() => this.set_contents_page(0))
    }

    async set_contents_page(page: number) {
        return this.update_state(draft => {
            draft.contents_api.page = page
        }).then(this.debounced_load_rows)
    }

    async set_contents_page_size(page_size: number) {
        return this.update_state(draft => {
            draft.contents_api.page_size = page_size
        }).then(this.debounced_load_rows)
    }

    async set_sorting(sorting: Sorting[]) {
        await this.update_state(draft => {
            draft.contents_api.sorting = sorting
            draft.contents_api.page = 0
        })
        return this.load_content_rows()
    }

    async bulk_edit(
        to_add: SerializedMetadata[],
        to_remove: SerializedMetadata[]
    ) {
        return Axios.post(APP_URLS.BULK_EDIT, {
            to_edit: this.state.contents_api.selection.map(idx =>
                this.state.contents_api.loaded_content[idx]?.id
            ).filter(v => v !== undefined),
            to_add: to_add.map(meta => meta.id),
            to_remove: to_remove.map(meta => meta.id),
        }).then(this.load_content_rows)
    }

    //METADATA ----------------------------------------------------------

    // Updates the metadata held in state to reflect what is returned by the server
    //First updates metadata_types and then metadata and metadata_by_type
    async refresh_metadata() {
        const metadata_types: SerializedMetadataType[] = await get_data(APP_URLS.METADATA_TYPES)
        metadata_types.forEach(meta_type => this.update_autocomplete(meta_type, ""))
        await this.update_state(draft => {
            draft.metadata_api.metadata_types = metadata_types
        })

        const responses = await Promise.all(
            metadata_types.map(
                type => get_data(APP_URLS.METADATA_BY_TYPE(
                    type.name,
                    this.state.metadata_api.page_by_type[type.name]?.page || 1,
                    this.state.metadata_api.page_by_type[type.name]?.page_size || 10
                ))
                    .then(data => [type.name, data.results, data.count])
            )
        ) as [string, any, number][]



        return this.update_state(draft => {
            draft.metadata_api.metadata_by_type = responses.reduce((acc, current) => {
                acc[current[0]] = current[1]
                return acc
            }, {} as metadata_dict)

            responses.forEach(([type_name, _, count]) => {
                draft.metadata_api.page_by_type[type_name] = {
                    count: count,
                    page: draft.metadata_api.page_by_type[type_name]?.page || 1,
                    page_size: draft.metadata_api.page_by_type[type_name]?.page_size || 10
                }
            })
            //Add metadata_name to show_columns if it doesn't already exist
            //Parse cookies to see if the column should show up from cookies
            const in_cookies = (if_exists => {
                const value = if_exists?.split("=")[1]
                return value?.split(",")?.reduce((set, title) => {
                    set.add(title)
                    return set
                }, new Set() as Set<string>)
            })(document.cookie
                .split("; ")
                .find(row => row.startsWith("show_column")))

            draft.metadata_api.show_columns = metadata_types.reduce((acc, type) => {
                console.log(type.name)
                if (!(type.name in acc)) {
                    acc[type.name] = false
                }
                if (in_cookies?.has(type.name)) {
                    acc[type.name] = true
                }
                return acc
            }, {} as show_metadata_column)
        })
    }

    //Create MetadataType record
    async add_metadata_type(type_name: string) {
        return Axios.post(APP_URLS.METADATA_TYPES, {
            name: type_name
        })
            .then(this.load_content_rows)
            .finally(this.refresh_metadata)
    }

    //Renames existing MetadataType record
    async edit_metadata_type(old_type: SerializedMetadataType, new_name: string) {
        return Axios.patch(APP_URLS.METADATA_TYPE(old_type.id), {
            name: new_name
        })
            .then(this.load_content_rows)
            .finally(this.refresh_metadata)
    }

    //Deletes existing MetadataType record
    async delete_metadata_type(meta_type: SerializedMetadataType) {
        return Axios.delete(APP_URLS.METADATA_TYPE(meta_type.id))
            .then(this.load_content_rows)
            .finally(this.refresh_metadata)
    }
    
    //Add Metadata with MetadataType
    async add_metadata(meta_name: string, meta_type: SerializedMetadataType) {
        const response = await Axios.post(APP_URLS.METADATA, {
            name: meta_name,
            type: meta_type.id
        })
        return Promise.all([
            this.load_content_rows(),
            this.refresh_metadata()
        ]).then(_ => response)
    }
    
    //Edit the name of an existing Met
    async edit_metadata(old_meta: SerializedMetadata, new_name: string) {
        return Axios.patch(APP_URLS.METADATA_ITEM(old_meta.id), {
            name: new_name
        })
            .then(this.load_content_rows)
            .finally(this.refresh_metadata)
    }

    async delete_metadata(meta_type: SerializedMetadata) {
        return Axios.delete(APP_URLS.METADATA_ITEM(meta_type.id))
            .then(this.load_content_rows)
            .finally(this.refresh_metadata)
    }

    async set_view_metadata_column(update_func: (draft: show_metadata_column) => void) {
        await this.update_state(draft => {
            update_func(draft.metadata_api.show_columns)
        })
        
        const x = Object.keys(this.state.metadata_api.show_columns)
            .filter(name => this.state.metadata_api.show_columns[name])
        
        document.cookie = `show_columns=${x.join(',')}`
    }

    async set_metadata_page_size(size: number, type_name: string) {
        return this.update_state(draft => {
        //     draft.library_versions_api.library_versions_page_size = size
        // }).then(this.refresh_library_versions)
        //TODO: make sure this works
            draft.metadata_api.page_by_type[type_name].page_size = size
        })
            .then(this.refresh_metadata)
    }
    
    async set_metadata_page(page: number, type_name: string) {
        return this.update_state(draft => {
            draft.metadata_api.page_by_type[type_name].page = page
        })
            .then(this.refresh_metadata)
    }

    async update_autocomplete(meta_type: SerializedMetadataType, name: string) {
        const data = await get_data(
            APP_URLS.METADATA_BY_TYPE(
                meta_type.name, 
                this.state.metadata_api.page_by_type[meta_type.name]?.page || 1, 
                this.state.metadata_api.page_by_type[meta_type.name]?.page_size || 10, 
                name
            )
        )
        this.update_state(draft => {
            draft.metadata_api.autocomplete_metadata[meta_type.name] = data.results
        })
    }
    
    // LIBRARY ASSETS -------------------------------------------------------

    /**
     *  Updates the assets held in state to reflect the server.
     */
    async refresh_assets() {
        return get_data(APP_URLS.LIBRARY_ASSETS)
        .then((library_assets: LibraryAsset[]) => {
            return this.update_state(draft => {
                draft.library_assets_api.assets = library_assets,
                draft.library_assets_api.assets_by_group = range(1, 4).reduce((acc, group) => {
                    acc[group as AssetGroup] = library_assets.filter(asset => asset.image_group === group)
                    return acc
                }, {} as {[P in AssetGroup]: LibraryAsset[]})
            })
        })
    }

    //Create new library_asset from image file and AssetGroup
    async add_library_asset(image: File, group: AssetGroup) {
        const data = new FormData()
        data.append("image_file", image)
        data.append("image_group", group.toString())

        return Axios.post(APP_URLS.LIBRARY_ASSETS, data, {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        }).finally(this.refresh_assets)
    }

    //Updates the fimage and group of a given asset group
    async edit_library_asset(old_asset: LibraryAsset, new_image: File, new_group: AssetGroup) {
        return Axios.patch(APP_URLS.LIBRARY_ASSET_ITEM(old_asset.id), {
            image_file: new_image,
            image_group: new_group
        }).finally(this.refresh_assets)
    }

    async delete_library_asset(old_asset: LibraryAsset) {
        return Axios.delete(APP_URLS.LIBRARY_ASSET_ITEM(old_asset.id))
        .finally(this.refresh_assets)
    }

    //LibraryVersions ---------------------------------------------------------
    
    //Get all folders in the current version and build the list of all folders in the current version
    //Used to construct the paths used in the Libraries move modal
    async refresh_folders_in_current_version() {
        const folders: LibraryFolder[] = await get_data(APP_URLS.LIBRARY_VERSION_FOLDERS(this.state.library_versions_api.current_version.id))
        return this.update_state(draft => {
            draft.library_versions_api.folders_in_version = folders.map(folder => [
                folder,
                folder.breadcrumb.map(folder => folder.folder_name).join("/")
            ])
        })
    }

    //Load all library versions
    async refresh_library_versions(): Promise<any> {
        try {
            const response: {
                results: LibraryVersion[],
                count: number
            } = await get_data(APP_URLS.LIBRARY_VERSIONS(
                this.state.library_versions_api.library_versions_page + 1,
                this.state.library_versions_api.library_versions_page_size,
            ))
            return this.update_state(draft => {
                draft.library_versions_api.library_versions = response.results
                draft.library_versions_api.library_versions_count = response.count
            })
        } catch (err) {
            if ((err?.data?.error?.detail || err?.data?.detail || err?.detail) === "Invalid page." && this.state.library_versions_api.library_versions_page > 0) {
                return this.update_state(draft => {
                    draft.library_versions_api.library_versions_page -= 1
                }).then(this.refresh_library_versions)
            }
            throw err
        }
    }

    //Set LibraryVersion as current_directory and load the root folders
    async enter_version_root(version: LibraryVersion) {
        const folders = await get_data(APP_URLS.LIBRARY_ROOT_FOLDERS(version.id))
        await this.update_state(draft => {
            draft.library_versions_api.current_directory = {
                folders,
                files: []
            }
            draft.library_versions_api.current_version = cloneDeep(version)
            draft.library_versions_api.path = []
        })
        await this.refresh_folders_in_current_version()
        await this.refresh_modules_in_current_version()
        return this.load_content_rows()
    }

    async refresh_current_directory() {
        const length = this.state.library_versions_api.path.length
        return length > 0 ?
            this._update_current_directory(this.state.library_versions_api.path[length - 1] as LibraryFolder) :
            this.enter_version_root(this.state.library_versions_api.current_version)
    }

    async _update_current_directory(folder: LibraryFolder) {
        const data: [
            {folders: LibraryFolder[], files: SerializedContent[]}, //Current Directory contents
            LibraryFolder //Current Directory Folder
        ] = await Promise.all([
            get_data(APP_URLS.LIBRARY_FOLDER_CONTENTS(folder.id)),
            get_data(APP_URLS.LIBRARY_FOLDER(folder.id))
        ])

        await this.update_state(draft => {
            draft.library_versions_api.current_directory.files = data[0].files
            draft.library_versions_api.current_directory.folders = data[0].folders
        })
        return this.update_state(draft => {
            draft.library_versions_api.path = data[1].breadcrumb
        })
    }

    async enter_folder(folder: LibraryFolder, _back?: number) {
        return this._update_current_directory(folder)
    }

    async enter_parent() {
        if (this.state.library_versions_api.path.length > 0) {
            await this.update_state(draft => {
                draft.library_versions_api.path.pop()
            })
            const path = this.state.library_versions_api.path
            return path.length > 0 ?
                this._update_current_directory( path[path.length - 1] as LibraryFolder) :
                this.enter_version_root(this.state.library_versions_api.current_version)
        }
    }

    async remove_content_from_folder(folder: LibraryFolder, to_remove: SerializedContent[]) {
        return Axios.post(APP_URLS.LIBRARY_FOLDER_REMOVE_CONTENT(folder.id), {
            content_ids: to_remove.map(content => content.id)
        }).then(this.refresh_current_directory)
    }

    async add_version(library_name: string, version_number: string, user: number) {
        return Axios.post(APP_URLS.LIBRARY_VERSIONS(1, 5), {
            library_name,
            version_number,
            created_by: user
        }).then(this.refresh_library_versions)
    }

    async set_version_image(version: LibraryVersion, asset: LibraryAsset) {
        await Axios.patch(APP_URLS.LIBRARY_VERSION(version.id), {
            library_banner: asset.id
        })
        await this.refresh_library_versions()
        const new_version = this.state.library_versions_api.library_versions.find(
            version => this.state.library_versions_api.current_version.id === version.id
        )
        if (new_version !== undefined) {
            this.update_state(draft => {
                draft.library_versions_api.current_version = cloneDeep(new_version)
            })
        }
    }

    async set_folder_banner(folder: LibraryFolder, banner: LibraryAsset) {
        if (folder.parent === null) {
            return Axios.patch(APP_URLS.LIBRARY_FOLDER(folder.id), {
                banner_img: banner.id
            })
        } else {
            return Promise.reject("Folder is not top level")
        }
    }
    async set_folder_logo(folder: LibraryFolder, logo: LibraryAsset) {
        if (folder.parent === null) {
            return Axios.patch(APP_URLS.LIBRARY_FOLDER(folder.id), {
                logo_img: logo.id
            })
        } else {
            return Promise.reject("Folder is not top level")
        }
    }

    async delete_version(version: LibraryVersion) {
        await Axios.delete(APP_URLS.LIBRARY_VERSION(version.id))
        if (this.state.library_versions_api.current_version.id === version.id) {
            await this.reset_to_library_defaults()
        }
        return this.refresh_library_versions()
    }

    async build_version(version: LibraryVersion) {
        return Axios.get(APP_URLS.LIBRARY_BUILD(version.id))
    }

    async update_version(version: LibraryVersion, name?: string, number?: string, user?: User) {
        await Axios.patch(APP_URLS.LIBRARY_VERSION(version.id), {
            library_name: name,
            version_number: number,
            created_by: user?.id
        })
        await this.refresh_library_versions()
        const new_version = this.state.library_versions_api.library_versions.find(version => this.state.library_versions_api.current_version.id === version.id)
        if (new_version !== undefined) {
            return this.update_state(draft => {
                draft.library_versions_api.current_version = cloneDeep(new_version)
            })
        }
    }

    async add_content_to_folder(folder: LibraryFolder, to_add: SerializedContent[]) {
        return Axios.post(APP_URLS.LIBRARY_FOLDER_ADD_CONTENT(folder.id), {
            content_ids: to_add.map(content => content.id)
        }).then(this.refresh_current_directory)
    }

    //create_child_folder creates a new folder
    //if parent is a LibraryFolder it will set the new folder to be the child of the folder
    //if parent is a LibraryVersion the new folder will be a base-level folder without a parent
    async create_child_folder(parent: LibraryFolder | LibraryVersion, name: string) {
        //IIFE that tests the type of parent
        const folder_data = ((test: any): test is LibraryFolder => {
            return 'folder_name' in test //tests if parent is a LibraryFolder
        })(parent) ?
            { //`folder_data` if `parent` is a LibraryFolder
                folder_name: name,
                version: parent.version,
                parent: parent.id
            } : 
            { //`folder_data` if `parent` is a LibraryVersion
                folder_name: name,
                version: parent.id,
                parent: null
            }
        return Axios.post(APP_URLS.LIBRARY_FOLDERS, folder_data)
            .then(this.refresh_current_directory)
            .then(this.refresh_folders_in_current_version)
    }

    async clone_version(version: LibraryVersion) {
        await Axios.get(APP_URLS.LIBRARY_VERSION_CLONE(version.id))
        await this.refresh_library_versions()
        if (this.state.library_versions_api.current_version.id !== 0) {
            await this.refresh_current_directory()
            await this.refresh_folders_in_current_version()
            await this.refresh_modules_in_current_version()
        }
    }
 
    async delete_folder(folder: LibraryFolder) {
        return Axios.delete(APP_URLS.LIBRARY_FOLDER(folder.id))
            .then(this.refresh_current_directory)
            .then(this.refresh_folders_in_current_version)
    }

    async rename_folder(folder: LibraryFolder, new_name: string) {
        return Axios.patch(APP_URLS.LIBRARY_FOLDER(folder.id), {
            folder_name: new_name
        })
            .then(this.refresh_current_directory)
            .then(this.refresh_folders_in_current_version)
    }

    async add_module_to_version(version: LibraryVersion, module_to_add: LibraryModule) {
        return Axios.post(APP_URLS.LIBRARY_VERSION_ADD_MODULE(version.id), {
                library_module_id: module_to_add.id
        }).then(this.refresh_modules_in_current_version)

    }

    async remove_module_from_version(version: LibraryVersion, module_to_remove: LibraryModule) {
        return Axios.post(APP_URLS.LIBRARY_VERSION_REMOVE_MODULE(version.id), {
                library_module_id: module_to_remove.id
        }).then(this.refresh_modules_in_current_version)

    }

    async refresh_modules_in_current_version() {
        return get_data(APP_URLS.LIBRARY_VERSION_MODULES(this.state.library_versions_api.current_version.id))
            .then((modules: LibraryModule[]) => this.update_state(draft => {
                draft.library_versions_api.modules_in_version = modules
            }))
    }

    async set_versions_page_size(size: number) {
        return this.update_state(draft => {
            draft.library_versions_api.library_versions_page_size = size
        }).then(this.refresh_library_versions)
    }

    async set_versions_page(page: number) {
        return this.update_state(draft => {
            draft.library_versions_api.library_versions_page = page
        }).then(this.refresh_library_versions)
    }

    async add_metadata_type_to_version(version: LibraryVersion, metadata_type: SerializedMetadataType) {
        const { data } = await Axios.post(APP_URLS.LIBRARY_VERSION_ADD_METADATA(version.id), {
            metadata_type_id: metadata_type.id
        })
        this.refresh_library_versions()
        return data.data
    }

    async remove_metadata_type_to_version(version: LibraryVersion, metadata_type: SerializedMetadataType) {
        const { data } = await Axios.post(APP_URLS.LIBRARY_VERSION_remove_METADATA(version.id), {
            metadata_type_id: metadata_type.id
        })
        this.refresh_library_versions()
        return data.data
    }

    async reset_to_library_defaults() {
        return this.update_state(draft => {
            draft.library_versions_api.folders_in_version = []
            draft.library_versions_api.current_directory = {
                folders: [],
                files: []
            }
            draft.library_versions_api.current_version = {
                id: 0,
                library_name: "",
                version_number: "",
                library_banner: 0,
                created_by: 0,
                metadata_types: []
            }
            draft.library_versions_api.path = []
            draft.library_versions_api.modules_in_version = []
        })
    }

    async move_folder(
        to_move: number, copy: boolean,
        dest_folder?: number, dest_version?: number
    ) {
        return Axios.post((copy ?
            APP_URLS.COPY_FOLDER :
            APP_URLS.MOVE_FOLDER)(to_move, dest_folder, dest_version)
        )
            .then(this.refresh_current_directory)
            .then(this.refresh_folders_in_current_version)
    }

    async update_version_autocomplete(prefix: string) {
        const versions: LibraryVersion[] = await get_data(
            APP_URLS.LIBRARY_VERSION_PREFIX(prefix)
        )
        return this.update_state(draft => {
            draft.library_versions_api.autocomplete_versions = versions
        })
    }

    async update_folder_autocomplete(version: LibraryVersion) {
        const folders: LibraryFolder[] = await get_data(
            APP_URLS.LIBRARY_VERSION_FOLDERS(version.id)
        )
        this.update_state(draft => {
            draft.library_versions_api.autocomplete_folders = folders
        })
    }

    // USERS API -----------------------------------------------
    async refresh_users() {
        return get_data(APP_URLS.USERS)
            .then((users: User[]) => {
                this.update_state(draft => {
                    draft.users_api.users = users
                })
            })
    }

    async add_user(name: string) {
        return Axios.post(APP_URLS.USERS, {
            name
        }).then(this.refresh_users)
    }

    // LIBRARY MODULES API -----------------------------------------------
    async refresh_library_modules() {
        return get_data(APP_URLS.LIBRARY_MODULES)
            .then((library_modules: LibraryModule[]) => {
                this.update_state(draft => {
                    draft.library_modules_api.library_modules = library_modules
                })
            })
    }

    async add_module(name: string, file: File) {
        const form_data = new FormData()
        form_data.append("module_name", name)
        form_data.append("module_file", file)

        return Axios.post(APP_URLS.LIBRARY_MODULES, form_data, {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        }).then(this.refresh_library_modules)
    }
    
    async edit_module(to_edit: LibraryModule, name: string, file?: File | null) {
        const form_data = new FormData()
        form_data.append("module_name", name)
        if (file != undefined) {
            form_data.append("module_file", file)
        }

        return Axios.patch(APP_URLS.LIBRARY_MODULE(to_edit.id), form_data, {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        }).then(this.refresh_library_modules)
    }

    async set_module_logo(to_change: LibraryModule, logo: LibraryAsset) {
        return Axios.patch(APP_URLS.LIBRARY_MODULE(to_change.id), {
            logo_img: logo.id
        }).then(this.refresh_library_modules)
    }

    async delete_module(to_delete: LibraryModule) {
        return Axios.delete(APP_URLS.LIBRARY_MODULE(to_delete.id))
            .then(this.refresh_library_modules)
    }



    // UTILS API -----------------------------------------------
    async get_disk_info() {
        return get_data(APP_URLS.DISK_INFO)
            .then(data =>
                this.update_state(draft => {
                    draft.utils_api.disk_total = data.total
                    draft.utils_api.disk_used = data.used
                    draft.utils_api.disk_free = data.free
                })
            )
    }

    render() {
        if (this.state.initializing) return <p role="status">{strings.loading}</p>
        if (this.state.initialization_error) return <div className="advanced-empty">
            <p role="alert">{strings.workspace_load_error}</p>
            <button type="button" className="manager-button manager-secondary" onClick={() => window.location.reload()}>{strings.retry_workspace}</button>
        </div>

        const Render = this.props.render
        return <Render
            apis={{
                contents_api: {
                    state: this.state.contents_api,
                    add_content: this.add_content,
                    add_selected_to_folder: this.add_selected_to_folder,
                    delete_content: this.delete_content,
                    edit_content: this.edit_content,
                    load_content_rows: this.load_content_rows,
                    reset_search: this.reset_search,
                    set_selection: this.set_selection,
                    update_search_state: this.update_search_state,
                    set_page: this.set_contents_page,
                    set_page_size: this.set_contents_page_size,
                    set_sorting: this.set_sorting,
                    bulk_download: this.bulk_download,
                    delete_selection: this.delete_selection,
                    bulk_edit: this.bulk_edit,
                },
                lib_assets_api: {
                    state: this.state.library_assets_api,
                    add_library_asset: this.add_library_asset,
                    edit_library_asset: this.edit_library_asset,
                    delete_library_asset: this.delete_library_asset,
                    refresh_assets: this.refresh_assets
                },
                lib_versions_api: {
                    state: this.state.library_versions_api,
                    refresh_library_versions: this.refresh_library_versions,
                    enter_version_root: this.enter_version_root,
                    enter_folder: this.enter_folder,
                    enter_parent: this.enter_parent,
                    add_version: this.add_version,
                    set_version_image: this.set_version_image,
                    delete_version: this.delete_version,
                    update_version: this.update_version,
                    create_child_folder: this.create_child_folder,
                    delete_folder: this.delete_folder,
                    rename_folder: this.rename_folder,
                    set_folder_banner: this.set_folder_banner,
                    set_folder_logo: this.set_folder_logo,
                    clone_version: this.clone_version,
                    refresh_current_directory: this.refresh_current_directory,
                    remove_content_from_folder: this.remove_content_from_folder,
                    refresh_folders_in_current_version: this.refresh_folders_in_current_version,
                    add_content_to_folder: this.add_content_to_folder,
                    add_module_to_version: this.add_module_to_version,
                    remove_module_from_version: this.remove_module_from_version,
                    refresh_modules_in_current_version: this.refresh_modules_in_current_version,
                    set_page: this.set_versions_page,
                    set_page_size: this.set_versions_page_size,
                    add_metadata_type_to_version: this.add_metadata_type_to_version,
                    remove_metadata_type_to_version: this.remove_metadata_type_to_version,
                    reset_to_defaults: this.reset_to_library_defaults,
                    move_folder: this.move_folder,
                    update_version_autocomplete: this.update_version_autocomplete,
                    update_folder_autocomplete: this.update_folder_autocomplete,
                    build_version: this.build_version
                },
                metadata_api: {
                    state: this.state.metadata_api,
                    add_metadata: this.add_metadata,
                    add_metadata_type: this.add_metadata_type,
                    delete_metadata: this.delete_metadata,
                    delete_metadata_type: this.delete_metadata_type,
                    edit_metadata: this.edit_metadata,
                    edit_metadata_type: this.edit_metadata_type,
                    refresh_metadata: this.refresh_metadata,
                    set_view_metadata_column: this.set_view_metadata_column,
                    set_metadata_page: this.set_metadata_page,
                    set_metadata_page_size: this.set_metadata_page_size,
                    update_autocomplete: this.update_autocomplete
                },
                users_api: {
                    state: this.state.users_api,
                    add_user: this.add_user,
                    refresh_users: this.refresh_users
                },
                lib_modules_api: {
                    state: this.state.library_modules_api,
                    refresh_library_modules: this.refresh_library_modules,
                    set_module_logo: this.set_module_logo,
                    add_module: this.add_module,
                    edit_module: this.edit_module,
                    delete_module: this.delete_module
                },
                utils_api: {
                    state: this.state.utils_api,
                    get_disk_info: this.get_disk_info
                }
            }}
        />
    }
}
