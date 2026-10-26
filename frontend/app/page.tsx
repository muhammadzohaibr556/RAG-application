"use client";

import { useEffect, useState, type FormEvent } from "react";

type DocumentItem = {
  id: number; filename: string; file_type: string; size_bytes: number; chunk_count: number;
};
type Location = {
  filename: string; page?: number; paragraph_start?: number; paragraph_end?: number;
  line_start?: number; line_end?: number;
};
type Source = Location & {
  chunk_id: number; document_id: number; score: number; excerpt: string; citation: number;
};
type SearchHit = Location & { chunk_id: number; document_id: number; text: string; score: number };
type ChatResponse = { answer: string; sources: Source[] };
type SearchResponse = { query: string; results: SearchHit[] };
type Entry = { question: string; scope: string; mode: "chat"; response: ChatResponse }
  | { question: string; scope: string; mode: "search"; response: SearchResponse };

/** Decode the backend's shared error envelope rather than showing raw server responses. */
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/${path}`, init);
  if (response.status === 204) return undefined as T;
  const body = await response.json();
  if (!response.ok) throw new Error(body.error?.message || "Request failed. Please try again.");
  return body as T;
}

/** Location labels use only source metadata returned by the application. */
function location(source: Location): string {
  if (source.page != null) return `Page ${source.page}`;
  if (source.paragraph_start != null) return `Paragraphs ${source.paragraph_start}–${source.paragraph_end}`;
  return `Lines ${source.line_start}–${source.line_end}`;
}

function SourceDetails({ source }: { source: Source }) {
  return <details className="source">
    <summary><span className="source-number">[{source.citation}]</span> {source.filename}
      <span className="location">{location(source)}</span></summary>
    <p className="excerpt">{source.excerpt}</p>
    <small>Chunk {source.chunk_id} · cosine similarity {source.score.toFixed(3)}</small>
  </details>;
}

export default function Home() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<"chat" | "search">("chat");
  const [entries, setEntries] = useState<Entry[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    api<DocumentItem[]>("documents", { signal: controller.signal })
      .then(items => { setDocuments(items); setSelected(items.map(item => item.id)); })
      .catch(reason => { if (!controller.signal.aborted) setError(reason.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  async function refresh() {
    setError(""); setBusy("Refreshing documents…");
    try {
      const items = await api<DocumentItem[]>("documents");
      setDocuments(items);
      setSelected(ids => ids.filter(id => items.some(item => item.id === id)));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Refresh failed."); }
    finally { setBusy(""); }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const file = data.get("file");
    if (!(file instanceof File) || !file.size) { setError("Choose a nonempty document first."); return; }
    setError(""); setNotice(""); setBusy("Extracting, chunking, and embedding your document…");
    try {
      const document = await api<DocumentItem>("documents/upload", { method: "POST", body: data });
      setDocuments(items => [document, ...items]);
      setSelected(ids => [...ids, document.id]);
      setNotice(`${document.filename} is ready: ${document.chunk_count} chunks indexed.`);
      form.reset();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Upload failed."); }
    finally { setBusy(""); }
  }

  async function remove(document: DocumentItem) {
    setError(""); setNotice(""); setBusy(`Deleting ${document.filename}…`);
    try {
      await api<void>(`documents/${document.id}`, { method: "DELETE" });
      setDocuments(items => items.filter(item => item.id !== document.id));
      setSelected(ids => ids.filter(id => id !== document.id));
      setNotice(`${document.filename} deleted.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Deletion failed."); }
    finally { setBusy(""); }
  }

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = question.trim();
    if (!text || !selected.length) return;
    setError(""); setNotice("");
    setBusy(mode === "chat" ? "Retrieving context and generating an answer…" : "Embedding your query and searching FAISS…");
    const scope = documents.filter(item => selected.includes(item.id)).map(item => item.filename).join(", ");
    const body = { document_ids: selected, ...(mode === "chat" ? { question: text } : { query: text }) };
    const init = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    try {
      const entry: Entry = mode === "chat"
        ? { question: text, scope, mode, response: await api<ChatResponse>("chat/query", init) }
        : { question: text, scope, mode, response: await api<SearchResponse>("search", init) };
      setEntries(items => [entry, ...items]);
      setQuestion("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Query failed."); }
    finally { setBusy(""); }
  }

  const disabled = loading || !!busy;
  return <div className="shell">
    <header className="header">
      <div className="brand"><span className="brand-mark" aria-hidden="true">R</span><span>RAG / LEARNING LAB</span></div>
      <span className="local-badge">Local workspace</span>
    </header>
    <main>
      <div className="intro"><p className="eyebrow">FROM DOCUMENTS TO UNDERSTANDING</p>
        <h1>Ask. Retrieve. Verify.</h1>
        <p>Explore what your documents say, and see the passages behind every answer.</p>
      </div>
      <p className="pipeline">Upload <span>→</span> Extract <span>→</span> Chunk <span>→</span> Embed <span>→</span> Retrieve <span>→</span> Answer + sources</p>
      {error && <div className="error" role="alert">{error}</div>}
      <div className="status" role="status" aria-live="polite">{busy || notice}</div>
      <div className="workspace">
        <aside className="panel library" aria-label="Document library">
          <div className="section-heading"><h2>Your documents</h2><span className="count">{documents.length}</span></div>
          <p className="muted">Select the files to use as context.</p>
          <form className="upload" onSubmit={upload}>
            <label htmlFor="document-file">Add a document</label>
            <input id="document-file" type="file" name="file" accept=".pdf,.docx,.txt" required disabled={disabled} />
            <small>PDF, DOCX, or UTF-8 TXT. Text-based PDFs only.</small>
            <button type="submit" disabled={disabled}>Upload & index</button>
          </form>
          <div className="library-actions">
            <button className="text-button" disabled={disabled || !documents.length} onClick={() => setSelected(documents.map(item => item.id))}>Select all</button>
            <button className="text-button" disabled={disabled || !selected.length} onClick={() => setSelected([])}>Clear</button>
            <button className="text-button" disabled={disabled} onClick={refresh}>Refresh</button>
          </div>
          {loading ? <p className="muted">Loading documents…</p> : !documents.length ? <div className="empty-library">No documents yet.<br /><small>Upload a file to start exploring.</small></div> :
            <ul className="document-list">{documents.map(document => <li key={document.id}>
              <label className="document">
                <input type="checkbox" checked={selected.includes(document.id)} disabled={disabled}
                  onChange={event => setSelected(ids => event.target.checked ? [...ids, document.id] : ids.filter(id => id !== document.id))} />
                <span><strong>{document.filename}</strong><small>{document.file_type.toUpperCase()} · {document.chunk_count} chunks · {Math.ceil(document.size_bytes / 1024)} KB</small></span>
              </label>
              <button className="delete text-button" disabled={disabled} onClick={() => remove(document)} aria-label={`Delete ${document.filename}`}>Delete</button>
            </li>)}</ul>}
          <p className="privacy-note">Document text and questions are sent to OpenAI for embeddings and answers. Metadata and vectors are stored locally.</p>
        </aside>
        <section className="panel conversation" aria-label="Query workspace">
          <div className="section-heading"><h2>Explore your context</h2><span className="muted">{selected.length} selected</span></div>
          <div className="mode-switch" aria-label="Query mode">
            <button aria-pressed={mode === "chat"} disabled={disabled} onClick={() => setMode("chat")}>Ask documents</button>
            <button aria-pressed={mode === "search"} disabled={disabled} onClick={() => setMode("search")}>Inspect retrieval</button>
          </div>
          <p className="mode-help">{mode === "chat" ? "A grounded answer with expandable source citations." : "Raw matching passages and cosine scores. No LLM generation."}</p>
          <form onSubmit={ask} className="question-form">
            <label htmlFor="question">{mode === "chat" ? "Your question" : "Search query"}</label>
            <textarea id="question" value={question} onChange={event => setQuestion(event.target.value)} maxLength={2000}
              placeholder="When does inspection need to happen?" rows={3} required disabled={disabled} />
            <div className="question-footer"><small>{selected.length ? "Each question is independent." : "Select a document to begin."}</small>
              <button type="submit" disabled={disabled || !selected.length || !question.trim()}>{mode === "chat" ? "Ask question →" : "Search passages →"}</button></div>
          </form>
          <div className="results" aria-busy={!!busy}>
            {!entries.length && <div className="welcome"><span aria-hidden="true">↗</span><h3>Follow the evidence.</h3><p>Ask a question, then open its sources.<br />Switch to retrieval to see what FAISS found.</p></div>}
            {entries.map((entry, index) => <article className="entry" key={`${entries.length - index}`}>
              <p className="eyebrow">{entry.mode === "chat" ? "ANSWER" : "SEMANTIC SEARCH"}</p><h3>{entry.question}</h3>
              <p className="scope">Context: {entry.scope}</p>
              {entry.mode === "chat" ? <><p className="answer">{entry.response.answer}</p>
                {!!entry.response.sources.length && <div className="sources"><h4>Verify the sources</h4>{entry.response.sources.map(source => <SourceDetails key={source.chunk_id} source={source} />)}</div>}</>
                : <>{!entry.response.results.length && <p>No matching passages found in the selected documents.</p>}
                  {entry.response.results.map((hit, rank) => <div className="search-hit" key={hit.chunk_id}>
                    <div className="hit-heading"><strong>{rank + 1}. {hit.filename}</strong><code>{hit.score.toFixed(3)}</code></div>
                    <small>{location(hit)} · Chunk {hit.chunk_id}</small><p className="excerpt">{hit.text}</p>
                  </div>)}<p className="score-note">Cosine similarity measures vector closeness; it is not answer confidence.</p></>}
            </article>)}
          </div>
        </section>
      </div>
      <footer>Built for learning · Explicit pipeline · No high-level RAG framework</footer>
    </main>
  </div>;
}
