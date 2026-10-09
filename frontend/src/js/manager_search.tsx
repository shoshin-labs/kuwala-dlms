import React, { useEffect, useRef, useState } from "react";
import { catalogueQuery } from "./catalogue_tree";
import { request } from "./manager_api";
import { useIndexSearchState } from "./manager_indexing";
import { useManagerStrings } from "./manager_strings";

type Profile = "metadata" | "lexical" | "semantic";
type Passage = {
  document_id: number;
  title: string;
  filename: string;
  original_sha256: string;
  page: number;
  text: string;
  publisher?: string;
  authors?: string[] | string;
  source_url?: string;
  licence?: string;
  licence_url?: string;
  original_page_url?: string;
};
type SearchData = {
  private_draft: boolean;
  catalogue_version: number;
  folder_id: number | null;
  snapshot: string | null;
  profile_used: "lexical" | "semantic";
  lexical_available: boolean;
  semantic_available: boolean;
  semantic_reason?: string;
  blocked_reason?: string;
  indexed_document_count: number;
  eligible_document_count: number;
  stale_document_count: number;
  unindexed_document_count: number;
  results: Passage[];
};
type Props = {
  versionId: number;
  folderId?: number;
  revision: number;
  metadataQuery: string;
  onMetadataChange: (query: string) => void;
  onMetadataSubmit: () => void;
  disabled: boolean;
  children: React.ReactNode;
};
function safeLink(value: string | undefined, local = false) {
  if (!value) return "";
  try {
    const url = new URL(value, window.location.origin);
    return ["http:", "https:"].includes(url.protocol) &&
      (!local || url.origin === window.location.origin)
      ? url.toString()
      : "";
  } catch {
    return "";
  }
}
export default function ManagerSearch({
  versionId,
  folderId,
  revision,
  metadataQuery,
  onMetadataChange,
  onMetadataSubmit,
  disabled,
  children,
}: Props) {
  const s = useManagerStrings();
  const { revision: indexRevision, error: indexError, refresh: refreshIndexing } = useIndexSearchState();
  const [profile, setProfile] = useState<Profile>("metadata");
  const [query, setQuery] = useState("");
  const [capabilities, setCapabilities] = useState<SearchData | null>(null);
  const [checking, setChecking] = useState(true);
  const [capabilityError, setCapabilityError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<SearchData | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const currentRequest = useRef(0);
  const resultsHeading = useRef<HTMLHeadingElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const endpoint = (query = "", selectedProfile: Profile = "lexical") =>
    catalogueQuery("/api/oasis/index-search/", {
      catalogue_version: versionId,
      folder_id: folderId,
      q: query,
      profile: selectedProfile,
    });
  function validate(data: SearchData) {
    if (
      data?.private_draft !== true ||
      data.catalogue_version !== versionId ||
      data.folder_id !== (folderId || null) ||
      !Array.isArray(data.results) ||
      data.results.length > 10 ||
      !["lexical", "semantic"].includes(data.profile_used)
    )
      throw new Error(s("invalid_response"));
    return data;
  }
  useEffect(() => {
    let current = true;
    currentRequest.current++;
    setCapabilities(null);
    setChecking(true);
    setCapabilityError("");
    setResult(null);
    setError("");
    setBusy(false);
    // Metadata browsing never waits for draft verification. Passage search
    // waits for the status check so the two initial requests cannot perform
    // the same cold artifact validation in separate server workers.
    if (!indexRevision || indexError) {
      setChecking(!indexError);
      setCapabilityError(indexError);
      return () => {
        current = false;
        currentRequest.current++;
      };
    }
    request(endpoint())
      .then((data) => {
        if (current) {
          setCapabilities(validate(data));
          setChecking(false);
        }
      })
      .catch((failure) => {
        if (current) {
          setCapabilityError(failure instanceof Error ? failure.message : "");
          setChecking(false);
        }
      });
    return () => {
      current = false;
      currentRequest.current++;
    };
  }, [versionId, folderId, revision, attempt, indexRevision, indexError]);
  const available =
    profile === "metadata" ||
    Boolean(
      capabilities &&
      (profile === "lexical"
        ? capabilities.lexical_available
        : capabilities.semantic_available),
    );
  function chooseProfile(next: Profile) {
    currentRequest.current++;
    setBusy(false);
    setResult(null);
    setError("");
    if (next === "metadata") onMetadataChange(query);
    else if (profile === "metadata") {
      setQuery(metadataQuery);
      onMetadataChange("");
    }
    setProfile(next);
  }
  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (profile === "metadata") {
      onMetadataSubmit();
      return;
    }
    if (!available || !query.trim() || disabled) return;
    const id = ++currentRequest.current;
    setBusy(true);
    setResult(null);
    setError("");
    try {
      const data: SearchData = validate(
        await request(endpoint(query.trim(), profile)),
      );
      if (id !== currentRequest.current) return;
      setResult(data);
      setCapabilities(data);
      setBusy(false);
      requestAnimationFrame(() => resultsHeading.current?.focus());
    } catch (failure) {
      if (id === currentRequest.current) {
        setError(failure instanceof Error ? failure.message : "");
        setBusy(false);
      }
    }
  }
  const summary = result || capabilities;
  return (
    <>
      <div className="manager-document-toolbar manager-search-toolbar">
        <form ref={form} className="manager-search-form" onSubmit={search}>
          <div className="manager-search-controls">
            <label className="manager-search-mode">
              {s("search_mode")}
              <select
                value={profile}
                disabled={disabled || busy}
                onChange={(event) =>
                  chooseProfile(event.target.value as Profile)
                }
              >
                <option value="metadata">{s("search_metadata")}</option>
                <option
                  value="lexical"
                  disabled={!capabilities?.lexical_available}
                >
                  {s("search_pdf_text")}
                </option>
                <option
                  value="semantic"
                  disabled={!capabilities?.semantic_available}
                >
                  {s("search_ai_semantic")}
                </option>
              </select>
            </label>
            <label className="manager-search">
              {s("search")}
              <input
                type="search"
                value={profile === "metadata" ? metadataQuery : query}
                disabled={disabled || busy}
                maxLength={profile === "metadata" ? undefined : 160}
                placeholder={s(
                  profile === "metadata"
                    ? "search_placeholder"
                    : "indexed_search_placeholder",
                )}
                onChange={(event) =>
                  profile === "metadata"
                    ? onMetadataChange(event.target.value)
                    : setQuery(event.target.value)
                }
                aria-describedby="manager-search-help"
              />
            </label>
            {profile !== "metadata" && (
              <button
                type="submit"
                className="manager-button"
                disabled={
                  disabled || busy || checking || !available || !query.trim()
                }
              >
                {busy
                  ? s("indexed_search_searching")
                  : s("indexed_search_submit")}
              </button>
            )}
          </div>
          <p
            id="manager-search-help"
            className={profile === "metadata" ? "sr-only" : "manager-help manager-search-help"}
          >
            {s(
              profile === "metadata"
                ? "search_metadata_help"
                : profile === "lexical"
                  ? "search_pdf_text_help"
                  : "search_ai_semantic_help",
            )}
          </p>
          <details className="manager-search-availability">
            <summary>{s("indexed_search_availability")}</summary>
            {checking ? (
              <p role="status">{s("indexed_search_checking")}</p>
            ) : capabilityError ? (
              <p className="manager-error" role="alert">
                {s("indexed_search_capability_error")} {capabilityError}
              </p>
            ) : (
              capabilities && (
                <>
                  <p>
                    {capabilities.lexical_available
                      ? s("indexed_search_text_available")
                      : capabilities.blocked_reason ||
                        s("indexed_search_text_unavailable")}
                  </p>
                  <p>
                    {capabilities.semantic_available
                      ? s("indexed_search_semantic_available")
                      : capabilities.semantic_reason ||
                        s("index_vectors_unavailable")}
                  </p>
                  {capabilities.snapshot && (
                    <p className="manager-search-snapshot">
                      {s("indexed_search_snapshot")}: {capabilities.snapshot}
                    </p>
                  )}
                </>
              )
            )}
            <button
              type="button"
              className="manager-text-button"
              disabled={checking || busy}
              onClick={() => {
                if (indexError) refreshIndexing();
                else setAttempt((value) => value + 1);
              }}
            >
              {s("indexed_search_refresh")}
            </button>
          </details>
        </form>
        {children}
      </div>
      {profile !== "metadata" && (
        <section
          className="manager-passage-results"
          aria-labelledby="manager-passage-title"
        >
          <h3 id="manager-passage-title" ref={resultsHeading} tabIndex={-1}>
            {s("indexed_search_results")}
          </h3>
          <p className="manager-help">{s("indexed_search_draft_help")}</p>
          {summary && (
            <p className="manager-search-coverage">
              {s("indexed_search_coverage", {
                eligible: summary.eligible_document_count,
                indexed: summary.indexed_document_count,
                stale: summary.stale_document_count,
                unindexed: summary.unindexed_document_count,
              })}
            </p>
          )}
          {!available && (
            <p className="manager-search-unavailable">
              {profile === "semantic"
                ? capabilities?.semantic_reason ||
                  capabilityError ||
                  s("index_vectors_unavailable")
                : capabilities?.blocked_reason ||
                  capabilityError ||
                  s("indexed_search_text_unavailable")}
            </p>
          )}
          {busy ? (
            <p role="status">{s("indexed_search_searching")}</p>
          ) : error ? (
            <div className="manager-error" role="alert">
              <p>
                {s("indexed_search_error")} {error}
              </p>
              <button
                className="manager-button"
                disabled={!available}
                onClick={() => form.current?.requestSubmit()}
              >
                {s("retry")}
              </button>
            </div>
          ) : result ? (
            result.results.length ? (
              <>
                <p className="manager-help">
                  {s(
                    result.profile_used === "semantic"
                      ? "indexed_search_semantic_results"
                      : "indexed_search_text_results",
                    { count: result.results.length },
                  )}
                </p>
                <ol className="manager-passage-list">
                  {result.results.map((passage, index) => {
                    const original = safeLink(passage.original_page_url, true);
                    const source = safeLink(passage.source_url);
                    const licence = safeLink(passage.licence_url);
                    const authors = Array.isArray(passage.authors)
                      ? passage.authors.join(", ")
                      : passage.authors;
                    return (
                      <li
                        key={`${passage.document_id}-${passage.page}-${index}`}
                      >
                        <h4>
                          {original ? (
                            <a href={original} target="_blank" rel="noopener">
                              {passage.title || passage.filename} ·{" "}
                              {s("indexed_search_page", { page: passage.page })}{" "}
                              ↗
                            </a>
                          ) : (
                            <>
                              {passage.title || passage.filename} ·{" "}
                              {s("indexed_search_page", { page: passage.page })}
                            </>
                          )}
                        </h4>
                        <blockquote>{passage.text}</blockquote>
                        <p className="manager-passage-attribution">
                          {[authors, passage.publisher, passage.licence]
                            .filter(Boolean)
                            .join(" · ") || s("indexed_search_no_attribution")}
                        </p>
                        <div className="manager-passage-links">
                          {original && (
                            <a href={original} target="_blank" rel="noopener">
                              {s("indexed_search_open_page")} ↗
                            </a>
                          )}
                          {source && (
                            <a
                              href={source}
                              target="_blank"
                              rel="noopener"
                              title={s("search_external_link")}
                            >
                              {s("indexed_search_source")} ↗
                            </a>
                          )}
                          {licence && (
                            <a
                              href={licence}
                              target="_blank"
                              rel="noopener"
                              title={s("search_external_link")}
                            >
                              {s("indexed_search_licence")} ↗
                            </a>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </>
            ) : (
              <p>{s("indexed_search_no_results")}</p>
            )
          ) : (
            <p className="manager-help">{s("indexed_search_prompt")}</p>
          )}
        </section>
      )}
      {profile !== "metadata" && (
        <h3 className="manager-managed-list-label">
          {s("search_managed_documents")}
        </h3>
      )}
    </>
  );
}
