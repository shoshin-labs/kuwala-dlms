import React from "react";
import { TabDict } from './types';
import strings from './locales/curator.en.json';

interface HomeScreenProps {
    tabs: TabDict,
    change_tab: (tab_name: string) => void
}

const workspaceSections = ["libraries", "metadata", "library_assets", "modules", "images", "system_info"];

export default function HomeScreen({tabs, change_tab}: HomeScreenProps) {
    return <div className="oasis-curator-home">
        <h2>{strings.home_heading}</h2>
        <p>{strings.home_intro}</p>
        <p className="oasis-curator-review-note">{strings.home_review_note}</p>
        <div className="oasis-curator-home-grid">
            {workspaceSections.map(tabName => <button
                key={tabName}
                type="button"
                className="oasis-curator-home-card"
                onClick={() => change_tab(tabName)}
            >
                <strong>{tabs[tabName].display_label}</strong>
                <span>{strings[`${tabName}_description`]}</span>
            </button>)}
        </div>
    </div>
}
