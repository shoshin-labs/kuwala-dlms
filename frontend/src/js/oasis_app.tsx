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
    primary: { main: "#006c67" },
    secondary: { main: "#006c67" },
    text: { primary: "#152536", secondary: "#4a5b6a" },
    background: { default: "#ffffff", paper: "#ffffff" },
  },
  typography: {
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
    fontSize: 16,
  },
  shape: { borderRadius: 8 },
  overrides: {
    MuiButton: {
      root: {
        minHeight: 48,
        textTransform: "none",
        fontWeight: 700,
        padding: "8px 16px",
      },
    },
    MuiIconButton: { root: { minWidth: 48, minHeight: 48 } },
    MuiTab: { root: { minHeight: 48, textTransform: "none", fontWeight: 700 } },
    MuiInputBase: { input: { minHeight: 24 } },
    MuiDialog: {
      paper: {
        maxWidth: "calc(100% - 32px)",
        margin: 16,
        border: "1px solid #d4dde4",
        borderRadius: 16,
        boxShadow: "0 16px 70px #0b283b26",
      },
    },
    MuiBackdrop: { root: { backgroundColor: "#0f243c45" } },
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
            <span className="brand-name">{s("product")}</span>
            <span className="brand-station">{s("station")}</span>
          </a>
          <div className="topbar-actions">
            <nav aria-label={s("product")}>
              <button
                className="nav-button"
                aria-current={view === "catalogue" ? "page" : undefined}
                onClick={() => switchView("catalogue")}
              >
                {s("catalogue")}
              </button>
              <button
                className="nav-button"
                aria-current={view === "about" ? "page" : undefined}
                onClick={() => switchView("about")}
              >
                {s("about")}
              </button>
              {config.curator_enabled && (
                <button
                  className="nav-button"
                  aria-current={view === "curator" ? "page" : undefined}
                  onClick={() => switchView("curator")}
                >
                  {s("curator")}
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
