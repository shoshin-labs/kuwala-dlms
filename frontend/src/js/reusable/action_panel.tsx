import React from "react"
import KebabMenu from './kebab_menu';
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
    const items: [() => void, string][] = [];
    const action = (label: string, handler?: () => void) => {
        if (handler) items.push([handler, label]);
    };
    action(strings.action_add, props.addFn);
    action(props.editHint || strings.action_edit, props.editFn);
    action(props.deleteHint || strings.action_delete, props.deleteFn);
    if (props.setActive) {
        action(props.row.active == 0 ? strings.action_activate : strings.action_deactivate,
            () => props.setActive!(props.row.active == 0));
    }
    action(props.viewHint || strings.action_view, props.viewFn);
    action(props.imageHint || props.logoHint || strings.action_image, props.imageFn);
    action(props.cloneHint || strings.action_clone, props.cloneFn);
    action(props.metadataHint || strings.action_metadata, props.buildFn);
    action(props.downloadHint || strings.action_download, props.downloadFn);
    if (!items.length) return null;

    return <span className="oasis-advanced-actions" role="group" aria-label={strings.row_actions}>
        <KebabMenu items={items} />
    </span>
}
