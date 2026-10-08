import React from "react"
import { Edit, Delete, CheckCircleOutline, HighlightOff, Visibility, ArrowBack, CropOriginal, FileCopy, LocalOffer, GetApp } from "@material-ui/icons"
import IconButton from "@material-ui/core/IconButton";
import Tooltip from "@material-ui/core/Tooltip";
import strings from '../locales/curator.en.json';

interface ActionPanelProps {
    row?: any,
    editFn?: () => void,
    deleteFn?: () => void,
    setActive?: (is_active: boolean) => void
    viewFn?: () => void
    addFn?: () => void
    imageFn?: () => void
    cloneFn?: () => void
    buildFn?: () => void
    downloadFn?: () => void
    editHint?: string
    deleteHint?: string
    viewHint?: string
    logoHint?: string
    imageHint?: string
    cloneHint?: string
    metadataHint?: string
    downloadHint?: string
}

export default function ActionPanel(props: ActionPanelProps) {
    const action = (key: string, label: string, handler: (() => void) | undefined, icon: JSX.Element) => handler ? (
        <Tooltip title={label} key={key}>
            <IconButton type="button" aria-label={label} onClick={handler} color="primary" style={{minWidth: 48, minHeight: 48}}>
                {icon}
            </IconButton>
        </Tooltip>
    ) : null;
    return <span role="group" aria-label={strings.row_actions} style={{display: 'inline-flex', flexWrap: 'wrap', maxWidth: '100%', gap: 2}}>
        {action('add', strings.action_add, props.addFn, <ArrowBack />)}
        {action('edit', props.editHint || strings.action_edit, props.editFn, <Edit />)}
        {action('delete', props.deleteHint || strings.action_delete, props.deleteFn, <Delete />)}
        {props.setActive && action('active', props.row.active == 0 ? strings.action_activate : strings.action_deactivate,
            () => props.setActive!(props.row.active == 0), props.row.active == 0 ? <CheckCircleOutline /> : <HighlightOff />)}
        {action('view', props.viewHint || strings.action_view, props.viewFn, <Visibility />)}
        {action('image', props.imageHint || props.logoHint || strings.action_image, props.imageFn, <CropOriginal />)}
        {action('clone', props.cloneHint || strings.action_clone, props.cloneFn, <FileCopy />)}
        {action('metadata', props.metadataHint || strings.action_metadata, props.buildFn, <LocalOffer />)}
        {action('download', props.downloadHint || strings.action_download, props.downloadFn, <GetApp />)}
    </span>
}
