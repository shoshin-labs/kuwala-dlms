import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
} from "@material-ui/core";
import { request } from "./manager_api";
import { useManagerStrings } from "./manager_strings";

type ArtifactState =
  "indexed" | "stale" | "not_indexed" | "not_applicable" | "unavailable";
type Artifact = { state: ArtifactState; reason?: string };
type IndexJob = {
  id: string;
  state: "queued" | "running" | "succeeded" | "failed";
  profile?: string;
  diagnostics?: unknown;
  created_on?: string;
  started_on?: string | null;
  finished_on?: string | null;
  affected_document_ids?: number[];
  affected_document_count?: number;
  affected_document_ids_truncated?: boolean;
};
type DocumentIndex = {
  document_id: number;
  filename: string;
  sha256: string | null;
  lexical: Artifact;
  vectors: Artifact;
  can_reindex: boolean;
  blocked_reason?: string;
  latest_job?: IndexJob | null;
};
type IndexSnapshot = {
  catalogue_version: number;
  configuration: {
    configured: boolean;
    blocked_reason?: string;
    lexical_available: boolean;
    vector_available: boolean;
    vector_blocked_reason?: string;
    worker_active: boolean;
  };
  documents: DocumentIndex[];
  jobs: IndexJob[];
  scope: "catalogue";
  snapshot_document_count: number;
  library?: {
    folder_id: number;
    eligible_document_count: number;
    can_reindex: boolean;
    blocked_reason?: string;
  } | null;
};
type IndexTarget = {
  name: string;
  documentId?: number;
  folderId?: number;
  isSection?: boolean;
};
type ContextValue = {
  snapshot: IndexSnapshot | null;
  checking: boolean;
  error: string;
  notice: string;
  refresh: () => void;
  open: (target: IndexTarget) => void;
};
const IndexContext = createContext<ContextValue | null>(null);
const activeJob = (job: IndexJob) =>
  job.state === "queued" || job.state === "running";
function diagnostics(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value))
    return value.map(diagnostics).filter(Boolean).join("\n");
  return value ? JSON.stringify(value, null, 2) : "";
}
function useIndexing() {
  return useContext(IndexContext)!;
}
export function useIndexSearchState() {
  const { snapshot, error, refresh } = useIndexing();
  const completedJob = snapshot?.jobs.find((job) => job.state === "succeeded");
  return {
    revision: snapshot
      ? `${completedJob?.id || ""}|${snapshot.configuration.vector_available}|${snapshot.configuration.vector_blocked_reason || ""}`
      : "",
    error,
    refresh,
  };
}
function eligible(snapshot: IndexSnapshot | null, target: IndexTarget) {
  if (
    !snapshot?.configuration.configured ||
    !snapshot.configuration.lexical_available ||
    snapshot.jobs.some(activeJob)
  )
    return false;
  return target.documentId !== undefined
    ? snapshot.documents.some(
        (document) =>
          document.can_reindex && document.document_id === target.documentId,
      )
    : snapshot.library?.folder_id === target.folderId &&
        snapshot.library.can_reindex;
}
export function IndexingProvider({
  versionId,
  revision,
  enabled = true,
  documentIds,
  folderId,
  children,
}: {
  versionId: number;
  revision: number;
  enabled?: boolean;
  documentIds: number[];
  folderId?: number;
  children: React.ReactNode;
}) {
  const s = useManagerStrings();
  const [snapshot, setSnapshot] = useState<IndexSnapshot | null>(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState("");
  const [sequence, setSequence] = useState(0);
  const [target, setTarget] = useState<IndexTarget | null>(null);
  const [profile, setProfile] = useState<"lexical" | "hybrid">("lexical");
  const [submitting, setSubmitting] = useState(false);
  const [jobError, setJobError] = useState("");
  const [notice, setNotice] = useState("");
  const sourceRevision = useRef(revision);
  const documentQuery = documentIds.join(",");
  useEffect(() => {
    let current = true;
    setChecking(true);
    setError("");
    if (sourceRevision.current !== revision) {
      sourceRevision.current = revision;
      setSnapshot(null);
    }
    // Catalogue navigation and the first document page load independently.
    // Avoid validating the same draft for an empty scope and again for each
    // intermediate folder/page state during the initial render.
    if (!enabled) {
      setSnapshot(null);
      return () => { current = false; };
    }
    request(
      `/api/oasis/indexing/?catalogue_version=${versionId}&document_ids=${encodeURIComponent(documentQuery)}${folderId ? `&folder_id=${folderId}` : ""}`,
    )
      .then((result) => {
        if (!current) return;
        if (
          result?.catalogue_version !== versionId ||
          !result.configuration ||
          !Array.isArray(result.documents) ||
          !Array.isArray(result.jobs)
        )
          throw new Error(s("invalid_response"));
        setSnapshot(result);
        setChecking(false);
      })
      .catch((failure) => {
        if (current) {
          setError(failure instanceof Error ? failure.message : "");
          setChecking(false);
        }
      });
    return () => {
      current = false;
    };
  }, [versionId, revision, sequence, documentQuery, folderId, enabled]);
  useEffect(() => {
    if (checking || !snapshot?.jobs.some(activeJob)) return;
    const timer = window.setTimeout(
      () => setSequence((value) => value + 1),
      4000,
    );
    return () => window.clearTimeout(timer);
  }, [snapshot, checking]);
  const refresh = () => setSequence((value) => value + 1);
  const open = (next: IndexTarget) => {
    setTarget(next);
    setProfile("lexical");
    setJobError("");
    setNotice("");
  };
  async function queue(event: React.FormEvent) {
    event.preventDefault();
    if (!target || !eligible(snapshot, target)) return;
    setSubmitting(true);
    setJobError("");
    try {
      await request("/api/oasis/index-jobs/", "POST", {
        catalogue_version: versionId,
        profile,
        ...(target.documentId !== undefined
          ? { document_id: target.documentId }
          : { folder_id: target.folderId }),
      });
      setTarget(null);
      setNotice(s("index_queued_notice"));
      refresh();
    } catch (failure) {
      setJobError(
        `${s("index_queue_error")} ${failure instanceof Error ? failure.message : ""}`,
      );
    } finally {
      setSubmitting(false);
    }
  }
  return (
    <IndexContext.Provider
      value={{ snapshot, checking, error, notice, refresh, open }}
    >
      {children}
      {target && (
        <Dialog
          open
          fullWidth
          maxWidth="sm"
          className="manager-dialog"
          aria-labelledby="manager-index-title"
          onClose={() => {
            if (!submitting) setTarget(null);
          }}
        >
          <DialogTitle id="manager-index-title">
            {s(
              target.documentId !== undefined
                ? "reindex_document_title"
                : target.isSection
                  ? "reindex_section_title"
                  : "reindex_library_title",
              { name: target.name },
            )}
          </DialogTitle>
          <DialogContent>
            <form
              id="manager-index-form"
              className="manager-form"
              onSubmit={queue}
            >
              {jobError && (
                <p className="manager-error" role="alert">
                  {jobError}
                </p>
              )}
              <p className="manager-index-confirmation">
                {s("index_scope_help", {
                  count: snapshot?.snapshot_document_count || 0,
                })}
              </p>
              <p>{s("index_draft_help")}</p>
              <fieldset className="manager-fieldset">
                <legend>{s("index_profile")}</legend>
                <label className="manager-checkbox">
                  <input
                    type="radio"
                    name="index-profile"
                    value="lexical"
                    checked={profile === "lexical"}
                    disabled={submitting}
                    onChange={() => setProfile("lexical")}
                  />
                  <span>
                    {s("index_text_profile")}
                    <small>{s("index_text_profile_help")}</small>
                  </span>
                </label>
                <label className="manager-checkbox">
                  <input
                    type="radio"
                    name="index-profile"
                    value="hybrid"
                    checked={profile === "hybrid"}
                    disabled={
                      submitting || !snapshot?.configuration.vector_available
                    }
                    onChange={() => setProfile("hybrid")}
                  />
                  <span>
                    {s("index_hybrid_profile")}
                    <small>
                      {snapshot?.configuration.vector_available
                        ? s("index_hybrid_profile_help")
                        : snapshot?.configuration.vector_blocked_reason ||
                          s("index_vectors_unavailable")}
                    </small>
                  </span>
                </label>
              </fieldset>
              {!snapshot?.configuration.worker_active && (
                <p className="manager-help">{s("index_worker_inactive")}</p>
              )}
            </form>
          </DialogContent>
          <DialogActions>
            <button
              autoFocus
              className="manager-button"
              disabled={submitting}
              onClick={() => setTarget(null)}
            >
              {s("cancel")}
            </button>
            <button
              type="submit"
              form="manager-index-form"
              className="manager-button manager-button-primary"
              disabled={
                submitting ||
                checking ||
                !eligible(snapshot, target) ||
                (profile === "hybrid" &&
                  !snapshot?.configuration.vector_available)
              }
            >
              {submitting ? s("index_queueing") : s("index_confirm")}
            </button>
          </DialogActions>
        </Dialog>
      )}
    </IndexContext.Provider>
  );
}
export function IndexingSummary() {
  const s = useManagerStrings();
  const { snapshot, checking, error, notice, refresh } = useIndexing();
  const job = snapshot?.jobs.find(activeJob) || snapshot?.jobs[0];
  const config = snapshot?.configuration;
  let compactStatus = "";
  if (error) compactStatus = s("index_status_unavailable");
  else if (!checking && snapshot) {
    if (job && (activeJob(job) || job.state === "failed"))
      compactStatus = s("index_job_" + job.state);
    else if (!config!.configured || !config!.lexical_available)
      compactStatus = s("index_unconfigured");
    else if (!config!.worker_active) compactStatus = s("index_worker_inactive_short");
  }
  return (
    <section
      className="manager-index-overview manager-index-compact"
      aria-labelledby="manager-index-overview-title"
    >
      {notice && (
        <p className="manager-notice" role="status">
          {notice}
        </p>
      )}
      <details className="manager-index-disclosure">
        <summary>
          <h2 id="manager-index-overview-title">{s("index_draft_title")}</h2>
          {compactStatus && <span className="manager-index-disclosure-state"
            role={error || job?.state === "failed" ? "alert" : "status"}>{compactStatus}</span>}
        </summary>
        <div className="manager-index-disclosure-content">
          <div className="manager-index-overview-heading">
            <button className="manager-text-button" disabled={checking} onClick={refresh}>
              {checking ? s("index_checking") : s("index_refresh")}
            </button>
          </div>
          <p>{s("index_draft_help")}</p>
      {error ? (
        <div className="manager-error" role="alert">
          <p>
            {s("index_status_error")} {error}
          </p>
          <button className="manager-button" onClick={refresh}>
            {s("retry")}
          </button>
        </div>
      ) : !snapshot ? (
        <p role="status">{s("index_checking")}</p>
      ) : (
        <>
          {!config!.configured || !config!.lexical_available ? (
            <p className="manager-index-config">
              {s("index_unconfigured")} {config!.blocked_reason}
            </p>
          ) : (
            <p className="manager-index-config">
              {config!.worker_active
                ? s("index_worker_ready")
                : s("index_worker_inactive")}
            </p>
          )}
          {job && (
            <div
              className={"manager-index-job is-" + job.state}
              role={job.state === "failed" ? "alert" : "status"}
            >
              <strong>{s("index_job_" + job.state)}</strong>
              {job.started_on && (
                <span>
                  {s("index_started", {
                    time: new Date(job.started_on).toLocaleString(),
                  })}
                </span>
              )}
              {job.finished_on && (
                <span>
                  {s("index_finished", {
                    time: new Date(job.finished_on).toLocaleString(),
                  })}
                </span>
              )}
              <details className="manager-index-details">
                <summary>{s("index_job_details")}</summary>
                <dl>
                  <dt>{s("index_job_identifier")}</dt>
                  <dd>{job.id}</dd>
                  <dt>{s("index_profile")}</dt>
                  <dd>
                    {job.profile === "hybrid"
                      ? s("index_hybrid_profile")
                      : s("index_text_profile")}
                  </dd>
                  {job.affected_document_ids && (
                    <>
                      <dt>{s("index_affected_documents")}</dt>
                      <dd>
                        {job.affected_document_ids.join(", ")}
                        {job.affected_document_ids_truncated && (
                          <p>
                            {s("index_truncated_ids", {
                              count: job.affected_document_count || 0,
                            })}
                          </p>
                        )}
                      </dd>
                    </>
                  )}
                </dl>
                {diagnostics(job.diagnostics) && (
                  <>
                    <strong>{s("index_diagnostics")}</strong>
                    <pre>{diagnostics(job.diagnostics)}</pre>
                  </>
                )}
              </details>
            </div>
          )}
        </>
      )}
        </div>
      </details>
    </section>
  );
}
export function DocumentIndexStatus({ documentId }: { documentId: number }) {
  const s = useManagerStrings();
  const { snapshot, checking, error } = useIndexing();
  const document = snapshot?.documents.find(
    (item) => item.document_id === documentId,
  );
  if (error)
    return (
      <p className="manager-index-missing">{s("index_status_unavailable")}</p>
    );
  if (!document)
    return (
      <p className="manager-index-missing">
        {checking
          ? s("index_checking")
          : error
            ? s("index_status_unavailable")
            : s("index_outside_catalogue")}
      </p>
    );
  const stateLabel = (artifact: Artifact) => s("index_state_" + artifact.state);
  const job = document.latest_job;
  return (
    <div className="manager-document-index">
      <div className="manager-index-states">
        <span className={"is-" + document.lexical.state}>
          {s("index_text")}: <strong>{stateLabel(document.lexical)}</strong>
        </span>
        <span className={"is-" + document.vectors.state}>
          {s("index_vectors")}: <strong>{stateLabel(document.vectors)}</strong>
        </span>
        {job && (activeJob(job) || job.state === "failed") && (
          <span>{s("index_job_" + job.state)}</span>
        )}
      </div>
      <details className="manager-index-details">
        <summary>{s("index_details")}</summary>
        <dl>
          <dt>{s("index_filename")}</dt>
          <dd>{document.filename}</dd>
          <dt>{s("index_sha")}</dt>
          <dd className="manager-index-hash">
            {document.sha256 || s("index_hash_unavailable")}
          </dd>
          <dt>{s("index_text")}</dt>
          <dd>{document.lexical.reason || stateLabel(document.lexical)}</dd>
          <dt>{s("index_vectors")}</dt>
          <dd>{document.vectors.reason || stateLabel(document.vectors)}</dd>
          {document.blocked_reason && (
            <>
              <dt>{s("index_reindex_availability")}</dt>
              <dd>{document.blocked_reason}</dd>
            </>
          )}
          {job && (
            <>
              <dt>{s("index_latest_job")}</dt>
              <dd>{s("index_job_" + job.state)}</dd>
            </>
          )}
        </dl>
      </details>
    </div>
  );
}
export function ReindexAction({
  target,
  disabled = false,
  menuItem = false,
  onChoose,
}: {
  target: IndexTarget;
  disabled?: boolean;
  menuItem?: boolean;
  onChoose?: () => void;
}) {
  const s = useManagerStrings();
  const { snapshot, checking, error, open } = useIndexing();
  const label = s(target.documentId !== undefined ? "reindex_document" :
    target.isSection ? "reindex_section" : "reindex_library");
  const unavailable = disabled || checking || Boolean(error) || !eligible(snapshot, target);
  const choose = () => { onChoose?.(); open(target); };
  if (menuItem) return <MenuItem disabled={unavailable} onClick={choose}>{label}</MenuItem>;
  return (
    <button
      className="manager-text-button"
      aria-label={s(
        target.documentId !== undefined
          ? "reindex_document_named"
          : target.isSection
            ? "reindex_section_named"
            : "reindex_library_named",
        { name: target.name },
      )}
      disabled={unavailable}
      onClick={choose}
    >
      {label}
    </button>
  );
}
