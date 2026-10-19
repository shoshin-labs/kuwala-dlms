import React from "react";
import { appBase } from "./app_paths";
import { useStrings } from "./i18n";

export default function CuratorLinks() {
  const s = useStrings();
  return <>
    <a className="nav-button"
      href={appBase() === "/manage/" ? "/" : "https://oasis.kuwala.space/"}
      target="_blank" rel="noopener noreferrer"
      aria-label={s("open_oasis_help")} title={s("open_oasis_help")}>
      <ExternalIcon />
      <span className="nav-label">{s("open_oasis")}</span>
    </a>
    <a className="nav-button" href="https://library.kuwala.space/"
      target="_blank" rel="noopener noreferrer"
      aria-label={s("central_library_help")} title={s("central_library_help")}>
      <ExternalIcon />
      <span className="nav-label">{s("central_library")}</span>
    </a>
  </>;
}

function ExternalIcon() {
  return <svg className="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M14 4h6v6M20 4l-9 9M10 4H4v16h16v-6" />
  </svg>;
}
