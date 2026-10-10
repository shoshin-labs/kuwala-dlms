import React, { lazy, Suspense, useEffect, useState } from "react";
import { createMuiTheme, ThemeProvider } from "@material-ui/core/styles";
import CssBaseline from "@material-ui/core/CssBaseline";
import LibraryCatalogue from "./library_catalogue";
import { get_data } from "./urls";
import { LocaleContext, locales, useStrings } from "./i18n";
import "../css/style.css";

const CuratorWorkspace = lazy(
  () => import(/* webpackChunkName: "curator" */ "./curator_workspace"),
);

const theme = createMuiTheme({
  palette: {
    primary: { main: "#45462a", contrastText: "#ffffff" },
    secondary: { main: "#ffa737", contrastText: "#343330" },
    text: { primary: "#343330", secondary: "#45462a" },
    background: { default: "#ffffff", paper: "#ffffff" },
  },
  typography: {
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
    fontSize: 16,
  },
  shape: { borderRadius: 9 },
  overrides: {
    MuiButton: {
      root: {
        minHeight: 48,
        textTransform: "none",
        fontWeight: 600,
        padding: "8px 16px",
      },
    },
    MuiIconButton: { root: { minWidth: 48, minHeight: 48 } },
    MuiTab: { root: { minHeight: 48, textTransform: "none", fontWeight: 600 } },
    MuiInputBase: { input: { minHeight: 24 } },
    MuiDialog: {
      paper: {
        maxWidth: "calc(100% - 32px)",
        margin: 16,
        border: "1px solid rgba(52, 51, 48, .2)",
        borderRadius: 16,
        boxShadow: "0 16px 70px #34333026",
      },
    },
    MuiBackdrop: { root: { backgroundColor: "#34333045" } },
  },
});
export default function OasisApp() {
  const [locale, setLocale] = useState("en");
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <LocaleContext.Provider value={locale}>
        <Shell locale={locale} setLocale={setLocale} />
      </LocaleContext.Provider>
    </ThemeProvider>
  );
}
function Shell({
  locale,
  setLocale,
}: {
  locale: string;
  setLocale: (value: string) => void;
}) {
  const s = useStrings();
  const initial = new URL(window.location.href).searchParams;
  const [view, setView] = useState(
    initial.get("workspace") === "curator"
      ? "curator"
      : initial.get("tab") === "about"
        ? "about"
        : "catalogue",
  );
  const [config, setConfig] = useState({
    curator_enabled: false,
    synthetic_fixtures: false,
  });
  const [configState, setConfigState] = useState("loading");
  useEffect(() => {
    get_data("/api/oasis/config/")
      .then((result) => {
        setConfig(result);
        setConfigState("ready");
      })
      .catch(() => setConfigState("error"));
  }, []);
  useEffect(() => {
    document.documentElement.lang = locale;
    document.title = s("product");
  }, [locale]);
  useEffect(() => {
    const update = () => {
      const params = new URL(window.location.href).searchParams;
      setView(
        params.get("workspace") === "curator"
          ? "curator"
          : params.get("tab") === "about"
            ? "about"
            : "catalogue",
      );
    };
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);
  function switchView(next: string) {
    const url = new URL(window.location.href);
    if (next === "curator") {
      url.searchParams.set("workspace", "curator");
      url.searchParams.set("tab", "home");
    } else {
      url.searchParams.delete("workspace");
      url.searchParams.set("tab", next === "about" ? "about" : "contents");
    }
    ["document", "library", "section", "q", "page"].forEach((key) =>
      url.searchParams.delete(key),
    );
    history.pushState({}, "", url.toString());
    setView(next);
    window.dispatchEvent(new PopStateEvent("popstate"));
    requestAnimationFrame(() =>
      document.getElementById("main-content")?.focus(),
    );
  }
  return (
    <div className="oasis-library">
      <a href="#main-content" className="skip-link">
        {s("skip")}
      </a>
      <header className="topbar">
        <div className="topbar-inner">
          <a
            className="brand"
            href="/?tab=contents"
            onClick={(event) => {
              event.preventDefault();
              switchView("catalogue");
            }}
          >
            <img
              className="brand-logo"
              src="/static/images/kuwala-oasis.svg"
              alt=""
              aria-hidden="true"
              width="40"
              height="40"
            />
            <span className="brand-copy">
              <span className="brand-name">{s("product")}</span>
              <span className="brand-station">{s("station")}</span>
            </span>
          </a>
          <div className="topbar-actions">
            <nav aria-label={s("product")}>
              {config.curator_enabled && (
                <a
                  className="nav-button"
                  href="https://oasis.kuwala.space/"
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={s("open_oasis_help")}
                  title={s("open_oasis_help")}
                >
                  <NavIcon kind="oasis" />
                  <span className="nav-label">{s("open_oasis")}</span>
                </a>
              )}
              <button
                className="nav-button"
                aria-label={s("catalogue")}
                title={s("catalogue")}
                aria-current={view === "catalogue" ? "page" : undefined}
                onClick={() => switchView("catalogue")}
              >
                <NavIcon kind="catalogue" />
                <span className="nav-label">{s("catalogue")}</span>
              </button>
              <button
                className="nav-button"
                aria-label={s("about")}
                title={s("about")}
                aria-current={view === "about" ? "page" : undefined}
                onClick={() => switchView("about")}
              >
                <NavIcon kind="about" />
                <span className="nav-label">{s("about")}</span>
              </button>
              {config.curator_enabled && (
                <button
                  className="nav-button"
                  aria-label={s("curator")}
                  title={s("curator")}
                  aria-current={view === "curator" ? "page" : undefined}
                  onClick={() => switchView("curator")}
                >
                  <NavIcon kind="curator" />
                  <span className="nav-label">{s("curator")}</span>
                </button>
              )}
            </nav>
            <label className="language-picker">
              <span className="sr-only">{s("language")}</span>
              <select
                value={locale}
                onChange={(event) => setLocale(event.target.value)}
              >
                {locales.map((pack) => (
                  <option value={pack.code} key={pack.code}>
                    {pack.nativeName}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
      </header>
      {config.synthetic_fixtures && (
        <div className="fixture-notice" role="note">
          <strong>{s("synthetic_title")}</strong>
          <span>{s("synthetic_text")}</span>
        </div>
      )}
      <main
        id="main-content"
        tabIndex={-1}
        className={
          view === "curator" ? "workspace curator-workspace" : "workspace"
        }
      >
        {view === "about" ? (
          <About />
        ) : view === "curator" ? (
          <>
            <h1 className="curator-heading">{s("curator")}</h1>
            {configState === "loading" ? (
              <p role="status">{s("loading_workspace")}</p>
            ) : configState === "error" ? (
              <p role="alert">{s("config_error")}</p>
            ) : config.curator_enabled ? (
              <Suspense
                fallback={<p role="status">{s("loading_workspace")}</p>}
              >
                <CuratorWorkspace />
              </Suspense>
            ) : (
              <p className="empty-state">{s("curator_disabled")}</p>
            )}
          </>
        ) : (
          <LibraryCatalogue />
        )}
      </main>
      <footer className="footer">{s("footer")}</footer>
    </div>
  );
}
function NavIcon({ kind }: { kind: string }) {
  return (
    <svg className="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {kind === "oasis" ? (
        <><path d="M14 4h6v6M20 4l-9 9M10 4H4v16h16v-6" /></>
      ) : kind === "catalogue" ? (
        <><path d="M12 5v15M3 4.5c3-1 6-.5 9 1 3-1.5 6-2 9-1V19c-3-1-6-.5-9 1-3-1.5-6-2-9-1z" /></>
      ) : kind === "about" ? (
        <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10v.01" /></>
      ) : (
        <><path d="M4 7h16M4 12h16M4 17h16" /><circle cx="9" cy="7" r="2" fill="var(--paper)" /><circle cx="15" cy="12" r="2" fill="var(--paper)" /><circle cx="9" cy="17" r="2" fill="var(--paper)" /></>
      )}
    </svg>
  );
}
function About() {
  const s = useStrings();
  return (
    <article className="about-view">
      <h1>{s("about_heading")}</h1>
      <p>{s("about_purpose")}</p>
      <p>{s("about_oasis")}</p>
      <p>{s("about_offline")}</p>
      <h2>{s("acknowledgement_heading")}</h2>
      <p>{s("acknowledgement")}</p>
      <h2>{s("software_licence")}</h2>
      <p>{s("licence_distinction")}</p>
      <details>
        <summary>{s("mit_title")}</summary>
        <div className="licence-text">{s("mit_text")}</div>
      </details>
    </article>
  );
}
export class AppBoundary extends React.Component<{}, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? <ErrorView /> : this.props.children;
  }
}
function ErrorView() {
  const s = useStrings();
  return (
    <main className="workspace">
      <h1>{s("product")}</h1>
      <p role="alert">{s("app_error")}</p>
      <button className="quiet-button" onClick={() => window.location.reload()}>
        {s("reload")}
      </button>
    </main>
  );
}
