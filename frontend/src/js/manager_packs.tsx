import React, { useEffect, useRef, useState } from "react";
import { request } from "./manager_api";
import { useManagerStrings } from "./manager_strings";

type Pack = { pack_id: string; title: string; release_id: string; document_count: number; bytes: number };
type Job = { phase: string; error?: string; download_bytes?: number };
type Snapshot = { configured: boolean; blocked_reason?: string; packs: Pack[]; has_more?: boolean;
  job?: Job; free_bytes?: number; received_bytes?: number; publication_sha256?: string;
  current?: string; rollback_available?: boolean };
type Detail = { pack_id: string; page: number; has_more: boolean; documents: {
  id: string; title: string; authors: string; publisher: string; licence: string; licence_url: string;
  source_url: string; rights_notes: string; review: { subject: { scope: string } };
}[] };
const busyPhases = new Set(["queued", "downloading", "indexing", "activating", "rolling_back"]);
const bytes = (value = 0) => value >= 1024 ** 3 ? `${(value / 1024 ** 3).toFixed(1)} GB` : `${(value / 1024 ** 2).toFixed(1)} MB`;

export default function PackInstallation() {
  const s = useManagerStrings();
  const [open, setOpen] = useState(false), [working, setWorking] = useState(false), [accepted, setAccepted] = useState(false);
  const [snapshot, setSnapshot] = useState<Snapshot>(), [detail, setDetail] = useState<Detail>();
  const [selected, setSelected] = useState<Set<string>>(new Set()), [page, setPage] = useState(1), [error, setError] = useState("");
  const sequence = useRef(0), detailSequence = useRef(0), mounted = useRef(true);
  const busy = !!snapshot?.job && busyPhases.has(snapshot.job.phase);
  useEffect(() => () => { mounted.current = false; sequence.current++; detailSequence.current++; }, []);
  async function load(nextPage = page) {
    const id = ++sequence.current;
    try {
      const value = await request(`/api/oasis/packs/?page=${nextPage}`);
      if (mounted.current && id === sequence.current) { setSnapshot(value); setError(""); }
    } catch (failure) { if (mounted.current && id === sequence.current) setError(String(failure.message || failure)); }
  }
  useEffect(() => {
    if (!open) return;
    load(page);
    if (!busy) return;
    const timer = window.setInterval(() => load(page), 5000);
    return () => window.clearInterval(timer);
  }, [open, page, busy]);
  async function action(command: object) {
    setWorking(true); setError(""); sequence.current++;
    try {
      const value = await request("/api/oasis/packs/", "POST", command);
      if (!mounted.current) return;
      if (snapshot?.publication_sha256 !== value.publication_sha256) {
        setSelected(new Set()); setAccepted(false); setDetail(undefined); detailSequence.current++;
      }
      setSnapshot(value); setPage(1);
    } catch (failure) { if (mounted.current) { await load(); setError(String(failure.message || failure)); } }
    finally { if (mounted.current) setWorking(false); }
  }
  async function showDetail(id: string, nextPage = 1) {
    const number = ++detailSequence.current;
    try {
      const value = await request(`/api/oasis/packs/?pack_id=${encodeURIComponent(id)}&page=${nextPage}`);
      if (mounted.current && number === detailSequence.current) setDetail(value);
    } catch (failure) { if (mounted.current && number === detailSequence.current) setError(String(failure.message || failure)); }
  }
  const phase = snapshot?.job?.phase;
  const labels: Record<string, string> = { queued: s("packs_queued"), downloading: s("packs_downloading"), indexing: s("packs_indexing"),
    activating: s("packs_activating"), active: s("packs_active"), rolling_back: s("packs_rolling_back"), rolled_back: s("packs_rolled_back"),
    failed: s("packs_failed"), recovery_required: s("packs_recovery") };
  return <details className="manager-packs" open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>{s("packs_heading")}</summary>
    {open && <section aria-label={s("packs_heading")}>
      <p>{s("packs_intro")}</p>
      <button className="manager-button" disabled={working || busy} onClick={() => action({action: "refresh"})}>{working ? s("packs_checking") : s("packs_refresh")}</button>
      {error && <p role="alert">{error}</p>}
      {snapshot?.configured === false && <p>{snapshot.blocked_reason}</p>}
      {snapshot?.configured && <>
        <p>{s("packs_space")}: {bytes(snapshot.free_bytes)}</p>
        {phase && <div role="status" aria-live="polite"><p>{labels[phase] || phase}</p>
          {phase === "downloading" && <p>{bytes(snapshot.received_bytes)} / {bytes(snapshot.job?.download_bytes)}</p>}
          {snapshot.job?.error && <p>{snapshot.job.error}</p>}
        </div>}
        {!snapshot.packs.length && <p>{s("packs_no_results")}</p>}
        <ul className="manager-pack-list">{snapshot.packs.map(pack => <li key={pack.pack_id}>
          <label><input type="checkbox" checked={selected.has(pack.pack_id)} disabled={working || busy || (!selected.has(pack.pack_id) && selected.size >= 32)} onChange={event => {
            const next = new Set(selected); if (event.target.checked) next.add(pack.pack_id); else next.delete(pack.pack_id); setSelected(next); setAccepted(false);
          }} /> <strong>{pack.title}</strong></label>
          <p>{pack.release_id} · {pack.document_count} {s("packs_documents")} · {bytes(pack.bytes)}</p>
          <button className="manager-text-button" onClick={() => showDetail(pack.pack_id)}>{s("packs_review")}</button>
        </li>)}</ul>
        {(page > 1 || snapshot.has_more) && <div className="manager-pack-pagination">
          <button className="manager-button" disabled={page === 1 || working} onClick={() => setPage(page - 1)}>{s("previous_page")}</button><span>{page}</span>
          <button className="manager-button" disabled={!snapshot.has_more || working} onClick={() => setPage(page + 1)}>{s("next_page")}</button>
        </div>}
        {detail && <aside className="manager-pack-review" aria-label={s("packs_review")}>
          <button className="manager-text-button" onClick={() => { detailSequence.current++; setDetail(undefined); }}>{s("packs_close_review")}</button>
          {detail.documents.map(document => <article key={document.id}><h3>{document.title}</h3><p>{document.authors} · {document.publisher}</p>
            <p><a href={document.licence_url} target="_blank" rel="noopener noreferrer">{document.licence}</a> · <a href={document.source_url} target="_blank" rel="noopener noreferrer">{s("packs_source")}</a></p>
            <p>{document.rights_notes}</p><h4>{s("packs_subject_review")}</h4><p>{document.review.subject.scope}</p>
          </article>)}
          {(detail.page > 1 || detail.has_more) && <div className="manager-pack-pagination">
            <button className="manager-button" disabled={detail.page === 1} onClick={() => showDetail(detail.pack_id, detail.page - 1)}>{s("previous_page")}</button><span>{detail.page}</span>
            <button className="manager-button" disabled={!detail.has_more} onClick={() => showDetail(detail.pack_id, detail.page + 1)}>{s("next_page")}</button>
          </div>}
        </aside>}
        {selected.size > 0 && <p><label><input type="checkbox" checked={accepted} disabled={working || busy} onChange={event => setAccepted(event.target.checked)} /> {s("packs_install_notice")}</label></p>}
        <div className="manager-pack-actions">
          <button className="manager-button manager-button-primary" disabled={working || busy || !accepted || !selected.size || selected.size > 32 || !snapshot.publication_sha256}
            onClick={() => action({action: "install", pack_ids: [...selected], publication_sha256: snapshot.publication_sha256, request_id: "install-" + crypto.randomUUID()})}>{s("packs_install")}</button>
          <button className="manager-button" disabled={working || busy || !snapshot.rollback_available}
            onClick={() => action({action: "rollback", expected_current: snapshot.current, request_id: "rollback-" + crypto.randomUUID()})}>{s("packs_rollback")}</button>
          <a href="https://oasis.kuwala.space/" target="_blank" rel="noopener noreferrer">{s("packs_open_oasis")}</a>
        </div>
      </>}
    </section>}
  </details>;
}
