import React from "react";
import { TabDict } from "./types";
import curator from "./locales/curator.en.json";
import s from "./locales/advanced-tabs.en.json";

interface HomeScreenProps {
    tabs: TabDict;
    change_tab: (tab_name: string) => void;
}

const workspaceSections = ["libraries", "metadata", "library_assets", "modules", "images", "system_info"];

export default function HomeScreen({ tabs, change_tab }: HomeScreenProps) {
    return <section className="oasis-curator-home advanced-page">
        <div className="advanced-page-heading"><div><h2>{s.home_heading}</h2><p>{s.home_intro}</p></div></div>
        <p className="oasis-curator-review-note">{curator.home_review_note}</p>
        <div className="oasis-curator-home-grid">
            {workspaceSections.filter(tabName => !!tabs[tabName]).map(tabName => <button
                key={tabName}
                type="button"
                className="oasis-curator-home-card"
                onClick={() => change_tab(tabName)}
            >
                <strong>{tabs[tabName].display_label}</strong>
                <span>{s[`home_${tabName}_description`]}</span>
            </button>)}
        </div>
    </section>;
}
