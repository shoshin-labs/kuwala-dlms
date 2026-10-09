import { Button, Grid, LinearProgress } from "@material-ui/core";
import prettyBytes from "pretty-bytes";
import React from "react";
import { UtilsAPI } from "./types";
import s from "./locales/advanced-tabs.en.json";

type SystemInfoProps = { utils_api: UtilsAPI };
type SystemInfoState = { refreshing: boolean; error: string };

export default class SystemInfo extends React.Component<SystemInfoProps, SystemInfoState> {
    constructor(props: SystemInfoProps) {
        super(props);
        this.state = { refreshing: false, error: "" };
    }

    async refresh() {
        if (this.state.refreshing) return;
        this.setState({ refreshing: true, error: "" });
        try {
            await this.props.utils_api.get_disk_info();
        } catch (_) {
            this.setState({ error: s.system_failed });
        } finally {
            this.setState({ refreshing: false });
        }
    }

    render() {
        const { disk_used, disk_free, disk_total } = this.props.utils_api.state;
        const available = [disk_used, disk_free, disk_total].every(value => Number.isFinite(value) && value >= 0) && disk_total > 0;
        const percent = available ? Math.min(100, Math.max(0, 100 * disk_used / disk_total)) : 0;
        return <section className="advanced-page">
            <div className="advanced-page-heading">
                <div><h2>{s.system_heading}</h2><p>{s.system_intro}</p></div>
                <Button variant="outlined" color="primary" disabled={this.state.refreshing} onClick={() => this.refresh()}>{s.system_refresh}</Button>
            </div>
            {this.state.error && <p className="advanced-form-error" role="alert">{this.state.error}</p>}
            {this.state.refreshing && <p className="advanced-help" role="status">{s.system_refreshing}</p>}
            {!available ? <p className="advanced-empty">{s.system_unavailable}</p> : <>
                <Grid container spacing={2} component="dl" className="advanced-storage-values">
                    <Grid item xs={12} sm={4} component="div"><dt>{s.system_used}</dt><dd>{prettyBytes(disk_used)}</dd></Grid>
                    <Grid item xs={12} sm={4} component="div"><dt>{s.system_free}</dt><dd>{prettyBytes(disk_free)}</dd></Grid>
                    <Grid item xs={12} sm={4} component="div"><dt>{s.system_total}</dt><dd>{prettyBytes(disk_total)}</dd></Grid>
                </Grid>
                <LinearProgress variant="determinate" value={percent} aria-label={s.system_usage} />
            </>}
        </section>;
    }
}
