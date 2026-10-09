import React, { Component, Fragment, RefObject } from 'react';
import { LibraryAssetsAPI, AssetGroup, LibraryAsset, field_info } from './types';
import { Typography, Grid, Button, TextField } from '@material-ui/core';
import { isUndefined, capitalize, isNull, cloneDeep } from 'lodash';
import ActionDialog from './reusable/action_dialog';
import { update_state, get_field_info_default } from './utils';
import { Delete } from '@material-ui/icons';
import VALIDATORS from './validators';

interface LibraryAssetsProps {
    library_assets_api: LibraryAssetsAPI
}
interface LibraryAssetsState {
    modals: LibraryAssetsModals
}

interface LibraryAssetsModals {
    add_asset: {
        is_open: boolean
        file: File | null
        group: AssetGroup
    }
    delete_asset: {
        is_open: boolean
        to_delete: LibraryAsset
        confirm_filename: field_info<string>
    }
}

export default class LibraryAssets extends Component<LibraryAssetsProps, LibraryAssetsState> {
    modal_defaults: LibraryAssetsModals
    update_state: (update_func: (draft: LibraryAssetsState) => void) => Promise<void>
    file_input_ref: RefObject<HTMLInputElement>

    constructor(props: LibraryAssetsProps) {
        super(props)

        const asset_default: LibraryAsset = {
            id: 0,
            image_file: null,
            image_group: 1,
            file_name: null
        }

        this.modal_defaults = {
            add_asset: {
                is_open: false,
                file: null,
                group: 1
            },
            delete_asset: {
                is_open: false,
                to_delete: asset_default,
                confirm_filename: get_field_info_default("")
            }
        }

        this.state = {
            modals: cloneDeep(this.modal_defaults)
        }

        this.file_input_ref = React.createRef()

        this.close_modals = this.close_modals.bind(this)
        this.update_state = update_state.bind(this)
    }

    close_modals() {
        this.update_state(draft => {
            draft.modals = cloneDeep(this.modal_defaults)
        })
    }

    render() {
        const library_assets_api = this.props.library_assets_api
        return (
            <>
                <Grid style={{marginLeft: "10%", marginRight: "10%"}}>
                    {Object.entries(library_assets_api.state.assets_by_group).map((entry, idx) => {
                        const [group, assets] = entry
                        const asset_group_raw = Number.parseInt(group);
                        if (Number.isNaN(asset_group_raw) || (
                                asset_group_raw !== 1 &&
                                asset_group_raw !== 2
                            ) || isUndefined(assets)) {
                            return <Fragment key={idx}></Fragment>
                        }
                        const asset_group = asset_group_raw as AssetGroup
                        return (
                            <Fragment key={idx}>
                                <Grid container style={{marginBottom: "3%"}}>
                                    <Grid item xs={6}>
                                        <Typography
                                            variant="h3"
                                        >{capitalize(library_assets_api.state.group_name[asset_group] + "s")}</Typography>
                                    </Grid>
                                    <Grid item xs={6} style={{textAlign: "right"}}>
                                        <Button
                                            variant={"outlined"}
                                            onClick={() => {
                                                this.update_state(draft => {
                                                    draft.modals.add_asset.is_open = true
                                                    draft.modals.add_asset.group = asset_group
                                                })
                                            }}
                                            style={{
                                                marginLeft: "1em",
                                                marginBottom: "1em",
                                                backgroundColor: "var(--action)",
                                                color: "#FFFFFF"
                                            }}
                                        >NEW {library_assets_api.state.group_name[asset_group]} ASSET</Button>
                                    </Grid>
                                </Grid>
                                <Grid container style={{marginBottom: "5%"}} spacing={2}>
                                    {assets.map((asset, asset_idx) => {
                                        if (isNull(asset.image_file)) return <Fragment key={asset_idx}></Fragment>
                                        return (
                                            <Grid item xs={3} key={asset_idx}>
                                                <a href={asset.image_file} target="_blank">
                                                    <img
                                                        src={asset.image_file}
                                                        style={{
                                                            objectFit: "cover",
                                                            maxWidth: "100%",
                                                            maxHeight: "100%",
                                                            minWidth: "100%",
                                                            width: "auto",
                                                            height: "auto"
                                                        }}
                                                    />
                                                </a>
                                                <Grid container>
                                                    <Grid item xs={10}>
                                                        <Typography
                                                            variant={"body1"}
                                                        >{asset.file_name}</Typography>
                                                    </Grid>
                                                    <Grid item xs={2} style={{textAlign: "right"}}>
                                                        <Delete
                                                            style={{cursor: "pointer"}}
                                                            onClick={() => {
                                                                this.update_state(draft => {
                                                                    draft.modals.delete_asset.is_open = true
                                                                    draft.modals.delete_asset.to_delete = asset
                                                                })
                                                            }}
                                                        />
                                                    </Grid>
                                                </Grid>
                                            </Grid>
                                        )
                                    })}
                                </Grid>
                            </Fragment>
                        )
                    })}
                </Grid>
                <ActionDialog
                    title={`Add New ${capitalize(library_assets_api.state.group_name[
                        this.state.modals.add_asset.group
                    ])} Asset`}
                    open={this.state.modals.add_asset.is_open}
                    on_close={this.close_modals}
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
                            onClick={()=> {
                                this.update_state(draft => {
                                    draft.modals.add_asset.file = ((file_raw: File | undefined | null) => file_raw === undefined ?
                                        null :
                                        file_raw)(this.file_input_ref.current?.files?.item(0))
                                }).then(() => {
                                    if (this.state.modals.add_asset.file !== null) {
                                        this.props.library_assets_api.add_library_asset(
                                            this.state.modals.add_asset.file,
                                            this.state.modals.add_asset.group
                                        ).then(this.close_modals)
                                    }
                                })
                            }}
                            color="primary"
                        >
                            Confirm
                        </Button>
                    )]}
                >
                    <input
                        accept="image/*"
                        type="file"
                        ref={this.file_input_ref}
                    />
                </ActionDialog>
                <ActionDialog
                    title={`Delete Library Asset ${this.state.modals.delete_asset.to_delete.file_name}`}
                    open={this.state.modals.delete_asset.is_open}
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
                                this.update_state(draft => {
                                    draft.modals.delete_asset.confirm_filename.reason = VALIDATORS.DELETE_IF_EQUALS(
                                        draft.modals.delete_asset.confirm_filename.value, this.state.modals.delete_asset.to_delete.file_name
                                    )
                                }).then(() => {
                                    if (this.state.modals.delete_asset.confirm_filename.reason === "") {
                                        library_assets_api.delete_library_asset(this.state.modals.delete_asset.to_delete)
                                        this.close_modals()
                                    }
                                })
                            }}
                            color="primary"
                            ref={focus_ref}
                        >
                            Confirm
                        </Button>
                    )]}
                >
                    <Typography>
                        Re-enter "{this.state.modals.delete_asset.to_delete.file_name}" to confirm deletion
                    </Typography>
                    <TextField
                        fullWidth
                        error={this.state.modals.delete_asset.confirm_filename.reason !== ""}
                        helperText={this.state.modals.delete_asset.confirm_filename.reason}
                        value={this.state.modals.delete_asset.confirm_filename.value}
                        onChange={(evt) => {
                            evt.persist()
                            this.update_state(draft => {
                                draft.modals.delete_asset.confirm_filename.value = evt.target.value
                            })
                        }}
                    />
                </ActionDialog>
                
            </>
        )
    }
}
