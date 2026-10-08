import React from 'react';

import HomeScreen from "./home_screen"
import Metadata from "./metadata"
import Content from "./content"

import '../css/style.css';
import strings from './locales/curator.en.json';

import {Snackbar, CircularProgress, Box, IconButton} from '@material-ui/core';
import {Close} from "@material-ui/icons"
import { Alert } from '@material-ui/lab';
import { update_state } from './utils';
import { APIs, TabDict } from './types';
import LibraryAssets from './library_assets';
import Libraries from './libraries';
import LibraryImages from './library_images';
import SystemInfo from './system_info';
import LibraryModules from "./library_modules";

interface MainScreenProps {
    apis: APIs
}

interface MainScreenState {
    url: URL,
    current_tab: string
    toast_state: {
        message: string
        is_open: boolean
        is_success: boolean
        last_open: number
    }
    loader_state: {
        loading: boolean
    }
    has_error: boolean
}

class MainScreen extends React.Component<MainScreenProps, MainScreenState> {
    tabs: TabDict
    update_state: (update_func: (draft: MainScreenState) => void) => Promise<void>
    constructor(props: MainScreenProps) {
        super(props)
        
        this.change_tab = this.change_tab.bind(this)

        this.tabs = {
            "home": {
                display_label: strings.home,
                component: (tabs, _apis) => <HomeScreen change_tab={this.change_tab} tabs={tabs}/>,
                icon: null
            },
            "metadata": {
                display_label: strings.metadata,
                component: (_tabs, apis) => (
                    <Metadata
                        metadata_api={apis.metadata_api}
                        show_toast_message={this.show_toast_message}
                    />
                ),
                icon: null
            },
            "contents": {
                display_label: strings.contents,
                component: (_tabs, apis) => (
                    <Content
                        metadata_api={apis.metadata_api}
                        show_toast_message={this.show_toast_message}
                        close_toast={this.close_toast}
                        contents_api={apis.contents_api}
                        show_loader={this.show_loader}
                        remove_loader={this.remove_loader}
                    />
                ),
                icon: null
            },
            "library_assets": {
            display_label: strings.library_assets,
                component: (_tabs, apis) => (
                    <LibraryAssets
                        library_assets_api={apis.lib_assets_api}
                    />
                ),
                icon: null
            },
            "modules": {
            display_label: strings.modules,
                component: (_tabs, apis) => (
                    <LibraryModules
                        library_modules_api={apis.lib_modules_api}
                        library_assets_api={apis.lib_assets_api}
                    />
                ),
                icon: null
            },
            "libraries": {
                display_label: strings.libraries,
                component: (_tabs, apis) => (
                    <Libraries 
                        library_versions_api={apis.lib_versions_api}
                        library_assets_api={apis.lib_assets_api}
                        users_api={apis.users_api}
                        metadata_api={apis.metadata_api}
                        contents_api={apis.contents_api}
                        library_modules_api={apis.lib_modules_api}
                        show_toast_message={this.show_toast_message}
                    />
                ),
                icon: null
            },
            "images": {
                display_label: strings.images,
                component: (_tabs, apis) => (
                    <LibraryImages
                        library_versions_api={apis.lib_versions_api}
                        show_toast_message={this.show_toast_message}
                    />
                ),
                icon: null
            },
            "system_info": {
                display_label: strings.system_info,
                component: (_tabs, apis) => <SystemInfo utils_api={apis.utils_api} />,
                icon: null
            }
        }


        const url = new URL(window.location.href)

        const default_tab = Object.keys(this.tabs)[0]
        const tab_value = url.searchParams.get("tab")

        this.state = {
            //Makes sure current_tab exists and is actually a key in this.tabs otherwise set to default
            url,
            current_tab: tab_value === null ?
                default_tab :
                (tab_value in this.tabs ? tab_value : default_tab),
            toast_state: {
                message: "",
                is_open: false,
                is_success: false,
                last_open: Date.now()
            },
            loader_state:{
                loading:false
            },
            has_error: false,
        }

        this.close_toast = this.close_toast.bind(this)
        this.show_toast_message = this.show_toast_message.bind(this)
        this.show_loader = this.show_loader.bind(this)
        this.remove_loader = this.remove_loader.bind(this)
        this.update_state = update_state.bind(this)
    }

    //Closes the toast message window
    close_toast() {
        this.update_state(draft => {
            draft.toast_state.is_open = false
            draft.toast_state.message = ""
        })
    }

    //Opens the toast message and shows the window
    show_toast_message(message: string, is_success: boolean) {
        this.update_state(draft => {
            draft.toast_state.is_open = true
            draft.toast_state.message = message
            draft.toast_state.is_success = is_success
        })
    }

    change_tab(new_tab: string) {
        this.update_state(draft => {
            const new_url = new URL(draft.url.toString())
            new_url.searchParams.set("tab", new_tab)
            draft.url = new_url
            draft.current_tab = new_tab
        }).then(() => {
            history.replaceState({}, strings.product_name, this.state.url.toString())
        })
            .then(this.props.apis.contents_api.reset_search)
            .then(this.props.apis.lib_versions_api.reset_to_defaults)
            .then(this.props.apis.contents_api.load_content_rows)
    }
    show_loader(){
        this.update_state(draft => {
            draft.loader_state.loading = true
        })
    }
    remove_loader(){
        this.update_state(draft => {
            draft.loader_state.loading = false
        })
    }

    render() {
        const tabs_jsx = Object.entries(this.tabs).map(([tab_name, tab_data]) => {
            return <button
                key={tab_name}
                type="button"
                className="oasis-curator-nav-button"
                aria-current={this.state.current_tab === tab_name ? "page" : undefined}
                onClick={() => this.change_tab(tab_name)}
            >{tab_data.display_label}</button>
        })
        
        if (this.state.has_error) {
            return <p role="alert">{strings.workspace_error}</p>
        }

        return (
            <section className="oasis-curator">
                <p className="oasis-curator-notice" role="note">{strings.private_notice}</p>
                <nav className="oasis-curator-nav" aria-label={strings.navigation_label}>
                    {tabs_jsx}
                </nav>
                <div className="oasis-curator-content">
                    {this.tabs[this.state.current_tab].component(this.tabs, this.props.apis)}  
                </div>
                <Snackbar
                    anchorOrigin={{
                        vertical: 'bottom',
                        horizontal: 'left'
                    }}
                    
                    open={this.state.toast_state.is_open}
                    onClose={this.close_toast}
                >
                    <Alert severity={this.state.toast_state.is_success ? "success" : "error"}>
                        {this.state.toast_state.message}
                        <IconButton aria-label={strings.close_notification} onClick={this.close_toast} color="inherit">
                            <Close />
                        </IconButton>
                    </Alert>
                </Snackbar>
                <Box
                    position="absolute"
                    display="flex"
                    alignItems="center"
                    justifyContent="center"
                    top = "50%"
                    right = "50%"
                    zIndex = "10001"
                >
                    {(this.state.loader_state.loading || this.props.apis.utils_api.state.outstanding_requests.size > 0)
                        && <CircularProgress color="primary" aria-label={strings.loading}/>}
                </Box>
            </section>
        )
    }
}

export default MainScreen;
