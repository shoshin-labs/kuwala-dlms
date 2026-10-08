import ActionDialog from './action_dialog'
import React from 'react'
import { Button, Typography, Paper, Grid } from '@material-ui/core'
import { APP_URLS } from '../urls'
import prettyBytes from 'pretty-bytes'
import { SerializedMetadataType, SerializedContent, MetadataAPI } from '../types'
import strings from '../locales/curator.en.json'

type ViewContentProps = {
    metadata_api: MetadataAPI
    on_close: () => void
    is_open: boolean
    row: SerializedContent
}

export const ViewContentModal = ({
    metadata_api,
    on_close,
    is_open,
    row
}: ViewContentProps) => {
    const original = row.file_name ? new URL(encodeURIComponent(row.file_name), APP_URLS.CONTENT_FOLDER).href : '';
    return (
    <ActionDialog
        title={strings.view_document}
        open={is_open}
        get_actions={focus_ref => [(
            <Button
                key={1}
                onClick={on_close}
                color="secondary"
                ref={focus_ref}
            >
                {strings.close}
            </Button>
        )]}
    >
        <p>{strings.review_notice}</p>
        <Grid container spacing={3} style={{maxWidth: 1100}}>
            <Grid item xs={12} md={5} style={{minWidth: 0, overflowWrap: 'anywhere'}}>
                {[
                    [strings.title, row.title],
                    [strings.display_title, row.display_title],
                    [strings.description, row.description],
                    [strings.filename, original ? <a href={original} target="_blank" rel="noopener">{row.file_name}</a> : null],
                    [strings.year, row.published_year],
                    [strings.review_date, row.reviewed_on],
                    [strings.copyright, row.copyright_notes],
                    [strings.rights, row.rights_statement],
                    [strings.file_size, Number.isFinite(row.filesize) ? prettyBytes(row.filesize) : null],
                    [strings.notes, row.additional_notes],
                    [strings.duplicatable, row.duplicatable ? strings.yes : strings.no]
                ].map(([title, value], idx) => {
                    return (
                        <div style={{marginBottom: "1em"}} key={idx}>
                            <Typography variant={"h6"}>{title}</Typography>
                            <Typography>{(value === null || value === undefined || value === '') ? <i>{strings.not_recorded}</i> : value}</Typography>
                        </div>
                    )
                })}
                {metadata_api.state.metadata_types.map((metadata_type: SerializedMetadataType) => {
                    return (
                        <div key={metadata_type.id} style={{marginBottom: "1em"}}>
                            <Typography variant={"h6"}>{metadata_type.name}</Typography>
                            <Paper>
                                {
                                    ((metadata) => metadata.length > 0 ?
                                            metadata :
                                            <Typography>{strings.no_metadata}</Typography>
                                        )((row.metadata_info || []).filter(value => value.type_name == metadata_type.name).map((metadata, idx) => (
                                        <div key={idx}>
                                            <Typography style={{overflowWrap: 'anywhere'}}>
                                                {/^https?:\/\/\S+$/i.test(metadata.name) ? <a href={metadata.name} target="_blank" rel="noopener">{metadata.name} ↗</a> : metadata.name}
                                            </Typography>
                                        </div>
                                    )))
                                }
                            </Paper>
                        </div>
                    )
                })}
            </Grid>
            <Grid item xs={12} md={7} style={{minWidth: 0}}>
                {original ? <p><a className="primary-button" href={original} target="_blank" rel="noopener">{strings.original} ↗</a></p> : <p>{strings.original_unavailable}</p>}
                {is_open && original ? (
                    <object
                        style={{
                            display: 'block',
                            minHeight: 440,
                            height: '70vh',
                            maxHeight: 800,
                        }}
                        width="100%"
                        data={original}
                        aria-label={strings.reader_label}
                    ><a href={original} target="_blank" rel="noopener">{strings.original}</a></object>
                ) : null}
            </Grid>
        </Grid>
    </ActionDialog>
    )
}
