import Axios from "axios"
import { isUndefined } from 'lodash'
import { format } from 'date-fns'
import { content_filters, LibraryVersion, SerializedContent, SerializedMetadata } from './types'
import { appUrl } from './app_paths'

const api_path = "api"

function url_with_params(urlstr: string, params:[string, any][]=[]) {
    const url = new URL(appUrl(urlstr))
    params.map(([key, value]) => {
        url.searchParams.append(key, value)
    })
    return url.toString()
}

function get_filters_arr(page?: number, size?: number, filters?: content_filters, exclude_if_in_version?: LibraryVersion): [string, any][] {
    const content_filter = filters || {}
    const {
        title, display_title, years, filename, copyright_notes, active, metadata, sort, file_sizes, reviewed_on, duplicatable
    } = content_filter
    const filters_arr: [string, any][] = page !== undefined ?
        [["page", `${page}`], ["size", `${size}`]] :
        []
    
    if (!isUndefined(title) && title !== "") filters_arr.push(["title", title])
    if (!isUndefined(display_title) && display_title !== "") filters_arr.push(["display_title", display_title])
    if (!isUndefined(years)) {
        if(years[0] !== null) filters_arr.push(["published_year_from", `${years[0]}`])
        if(years[1] !== null) filters_arr.push(["published_year_to", `${years[1]}`])
    }
    if (!isUndefined(file_sizes)) {
        if(file_sizes[0] !== null) filters_arr.push(["filesize_from", `${file_sizes[0]}`])
        if(file_sizes[1] !== null) filters_arr.push(["filesize_to", `${file_sizes[1]}`])
    }
    if (!isUndefined(reviewed_on)) {
        if(reviewed_on[0] !== null) filters_arr.push(["reviewed_from", `${format(reviewed_on[0], "yyyy-MM-dd")}`])
        if(reviewed_on[1] !== null) filters_arr.push(["reviewed_to", `${format(reviewed_on[1], "yyyy-MM-dd")}`])
    }
    if (!isUndefined(filename) && filename !== "") filters_arr.push(["file_name", filename])
    if (!isUndefined(copyright_notes) && copyright_notes !== "") filters_arr.push(["copyright_notes", copyright_notes])
    if (!isUndefined(active)) filters_arr.push(["active", active ? "true" : "false"])
    if (!isUndefined(metadata) && metadata.length > 0) filters_arr.push(["metadata", metadata.join(",")])
    if (!isUndefined(sort)) filters_arr.push(["sort", sort])
    if (!isUndefined(duplicatable)) filters_arr.push(["duplicatable", duplicatable])
    if (!isUndefined(exclude_if_in_version)) filters_arr.push(["exclude_in_version", exclude_if_in_version.id])
    return filters_arr
}

const APP_URLS = {
    API: url_with_params(api_path),
    BULK_EDIT: url_with_params(`${api_path}/bulk_edit/`),
    CONTENT: url_with_params(`${api_path}/contents/`),
    CONTENT_PAGE: (page: number, size: number, filters?: content_filters, exclude_if_in_version?: LibraryVersion) =>
        url_with_params(`${api_path}/contents/`, get_filters_arr(page, size, filters, exclude_if_in_version)),
    CONTENT_ITEM: (id: number) => url_with_params(`${api_path}/contents/${id}/`),
    CONTENT_BULK: url_with_params(`${api_path}/content_bulk_add/`),
    CONTENT_BULK_DOWNLOAD: (filters?: content_filters) =>
        url_with_params(`${api_path}/contents/get_spreadsheet/`, get_filters_arr(undefined, undefined, filters)),
    CONTENT_FOLDER: url_with_params("media/contents/"),
    COPY_FOLDER: (to_copy: number, dest_folder?: number, dest_version?: number) =>
        url_with_params(
            `${api_path}/library_folders/${to_copy}/copy_to/`,
            dest_folder ?
                [["dest_folder", dest_folder]] :
                [["dest_version", dest_version]]
        ),
    CSRF_TOKEN: url_with_params(`${api_path}/get_csrf/`),
    MODULE_FOLDER: url_with_params("media/modules/"),
    DISK_INFO: url_with_params(`${api_path}/disk_info/`),
    LIBRARY_ASSETS: url_with_params(`${api_path}/lib_layout_images/`),
    LIBRARY_ASSET_ITEM: (id: number) =>
        url_with_params(`${api_path}/lib_layout_images/${id}/`),
    LIBRARY_FOLDER: (id: number) =>
        url_with_params(`${api_path}/library_folders/${id}/`),
    LIBRARY_FOLDERS: url_with_params(`${api_path}/library_folders/`),
    LIBRARY_FOLDER_ADD_CONTENT: (folder_id: number) =>
        url_with_params(`${api_path}/library_folders/${folder_id}/addcontent/`),
    LIBRARY_FOLDER_REMOVE_CONTENT: (folder_id: number) =>
        url_with_params(`${api_path}/library_folders/${folder_id}/removecontent/`),
    LIBRARY_FOLDER_CONTENTS: (id: number) =>
        url_with_params(`${api_path}/library_folders/${id}/contents/`),
    LIBRARY_ROOT_FOLDERS: (id:number) =>
        url_with_params(`${api_path}/library_versions/${id}/root/`),
    LIBRARY_VERSION: (id: number) =>
        url_with_params(`${api_path}/library_versions/${id}/`),
    LIBRARY_VERSION_CLONE: (id: number) =>
        url_with_params(`${api_path}/library_versions/${id}/clone/`),
    LIBRARY_VERSION_FOLDERS: (id: number) =>
        url_with_params(`${api_path}/library_versions/${id}/folders/`),
    LIBRARY_VERSION_MODULES: (id: number) =>
        url_with_params(`${api_path}/library_versions/${id}/modules/`),
    LIBRARY_VERSION_ADD_MODULE: (id: number) =>
        url_with_params(`${api_path}/library_versions/${id}/addmodule/`),
    LIBRARY_VERSION_ADD_METADATA: (id: number) =>
        url_with_params(`${api_path}/library_versions/${id}/add_metadata_type/`),
    LIBRARY_VERSION_remove_METADATA: (id: number) =>
        url_with_params(`${api_path}/library_versions/${id}/remove_metadata_type/`),
    LIBRARY_VERSION_REMOVE_MODULE: (id: number) =>
        url_with_params(`${api_path}/library_versions/${id}/remove/`),
    LIBRARY_VERSION_PREFIX: (prefix: string) => url_with_params(
        `${api_path}/library_versions/filter_prefix/`, [["prefix", prefix]]
    ),
    LIBRARY_VERSIONS: (page: number, size: number) => url_with_params(
        `${api_path}/library_versions/`, [["page", page], ["size", size]]
    ),
    LIBRARY_BUILD: (id: number) =>
        url_with_params(`${api_path}/create_build/${id}/`),
    METADATA: url_with_params(`${api_path}/metadata/`),
    METADATA_ITEM: (id: number) => url_with_params(`${api_path}/metadata/${id}/`),
    METADATA_TYPE: (id: number) => url_with_params(`${api_path}/metadata_types/${id}/`),
    METADATA_TYPES: url_with_params(`${api_path}/metadata_types/`),
    METADATA_BY_TYPE: (type: string, page: number, size: number, name?: string) => url_with_params(
        `${api_path}/metadata/${type}/get/`,
        name ? [["page", page], ["size", size], ["name", name]] : [["page", page], ["size", size]]
    ),
    METADATA_SHEET: (metadata_type: string) => url_with_params(`${api_path}/spreadsheet/metadata/${metadata_type}`),
    MOVE_FOLDER: (to_move: number, dest_folder?: number, dest_version?: number) =>
        url_with_params(
            `${api_path}/library_folders/${to_move}/move_to/`,
            dest_folder ?
                [["dest_folder", dest_folder]] :
                [["dest_version", dest_version]]
        ),
    USERS: url_with_params(`${api_path}/users/`),
    LIBRARY_MODULE: (id: number) => url_with_params(`${api_path}/library_modules/${id}/`),
    LIBRARY_MODULES: url_with_params(`${api_path}/library_modules/`),
    
}

//Transforms url into a promise containing the data or error from that api call
//Provide url argument from AP_URLS
async function get_data(url: string) {
    return Axios.get(appUrl(url), {responseType: 'json'}).catch((err) => {
        return Promise.reject(err.response)
    }).then((response) => {
        const data = response.data
        return data.success ? Promise.resolve(data.data) : Promise.reject(data.error)
    })
}

export {
    APP_URLS,
    get_data
}
