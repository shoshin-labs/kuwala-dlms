import { DialogActions, DialogContent, Dialog, DialogTitle } from "@material-ui/core"
import React, { useRef, ForwardRefExoticComponent, RefAttributes} from 'react'

let dialog_sequence = 0

interface ActionDialogProps {
    title: string,
    open: boolean,
    get_actions: ((focus_ref: React.RefObject<HTMLButtonElement>) => JSX.Element[]) | ForwardRefExoticComponent<RefAttributes<HTMLButtonElement>>
    on_close?: () => void
}

const ActionDialog: React.FunctionComponent<ActionDialogProps> = (props) => {
    const focus_ref = useRef<HTMLButtonElement>(null)
    const title_id = useRef('')
    if (!title_id.current) title_id.current = 'oasis-advanced-dialog-title-' + (++dialog_sequence)
    // Labels and handlers must follow the current dialog state (for example,
    // switching between Move and Copy), rather than the first rendered actions.
    const actions = props.get_actions(focus_ref)
    
    return (
        <Dialog
            open={props.open}
            onClose={props.on_close || (() => {})}
            onEntered={() => focus_ref.current?.focus()}
            fullWidth
            maxWidth="md"
            aria-labelledby={title_id.current}
            className="oasis-advanced-dialog"
            PaperProps={{ className: 'oasis-advanced-dialog-paper',
                          style: { margin: 16, width: 'calc(100% - 32px)' } }}
        >
            <DialogTitle id={title_id.current} className="oasis-advanced-dialog-title">
                {props.title}
            </DialogTitle>
            <DialogContent className="oasis-advanced-dialog-content">
                {props.children}
            </DialogContent>
            <DialogActions className="oasis-advanced-dialog-actions">
                {actions}
            </DialogActions>
        </Dialog>
    )
}

export default ActionDialog
