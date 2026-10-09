import React, { Component } from "react"
import { ExpandMore } from '@material-ui/icons'
import { Button, Menu, MenuItem } from '@material-ui/core'
import { update_state } from '../utils'
import strings from '../locales/advanced.en.json'

let menu_sequence = 0

//items: Array of tuples containing a menu action function and then a string to represent that action in the menu
interface KebabMenuProps {
    items: [() => void, string][]
    label?: string
}
interface KebabMenuState {
    anchor_el: null | HTMLButtonElement
}

export default class KebabMenu extends Component<KebabMenuProps, KebabMenuState> {

    update_state: (update_func: (draft: KebabMenuState) => void) => Promise<void>
    menu_id = 'oasis-advanced-actions-' + (++menu_sequence)
    constructor(props: Readonly<KebabMenuProps>) {
        super(props)

        this.state = {
            anchor_el: null
        }

        this.on_close = this.on_close.bind(this)
        this.update_state = update_state.bind(this)
    }

    on_close() {
        return this.update_state(draft => {
            draft.anchor_el = null
        })
    }

    render() {
        if (!this.props.items.length) return null
        const open = Boolean(this.state.anchor_el)
        return (
            <>
                <Button
                    id={this.menu_id + '-trigger'}
                    type="button"
                    variant="outlined"
                    className="oasis-advanced-action-trigger"
                    aria-haspopup="menu"
                    aria-expanded={open}
                    aria-controls={open ? this.menu_id : undefined}
                    endIcon={<ExpandMore aria-hidden="true" />}
                    style={{ minHeight: 48, fontFamily: 'inherit' }}
                    onClick={evt => {
                        evt.stopPropagation()
                        evt.preventDefault()
                        this.setState({
                            anchor_el: evt.currentTarget
                        })
                    }}
                >
                    {this.props.label || strings.actions}
                </Button>
                <Menu
                    id={this.menu_id}
                    anchorEl={this.state.anchor_el}
                    open={open}
                    getContentAnchorEl={null}
                    anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
                    transformOrigin={{ vertical: 'top', horizontal: 'right' }}
                    classes={{ paper: 'oasis-advanced-action-menu', list: 'oasis-advanced-action-list' }}
                    PaperProps={{ style: { maxWidth: 'calc(100vw - 32px)' } }}
                    MenuListProps={{ 'aria-label': strings.actions_menu }}
                    onClose={evt => {
                        //evt is actually a click evt, this is a bug with MUI
                        (evt as MouseEvent).stopPropagation()
                        this.on_close()
                    }}
                >
                    {this.props.items.map((item, idx) => {
                        const [func, element] = item
                        return (
                            <MenuItem
                                className="oasis-advanced-action-menu-item"
                                style={{ minHeight: 48, fontFamily: 'inherit', whiteSpace: 'normal' }}
                                onClick={evt => {
                                    evt.stopPropagation()
                                    evt.preventDefault()
                                    this.on_close().then(func)
                                }}
                                key={idx}
                            >
                                {element}
                            </MenuItem>
                        )
                    })}
                </Menu>
            </>
        )
    }
}
