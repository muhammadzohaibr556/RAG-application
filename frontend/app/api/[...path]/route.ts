/** Stream same-origin UI requests to FastAPI; the API key stays exclusively in Python. */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: Context) {
  const path = (await context.params).path.join("/");
  const allowed =
    (path === "documents" && request.method === "GET") ||
    (path === "documents/upload" && request.method === "POST") ||
    (/^documents\/\d+$/.test(path) && request.method === "DELETE") ||
    (["search", "chat/query"].includes(path) && request.method === "POST");
  if (!allowed) return Response.json({ error: { message: "Route not found." } }, { status: 404 });
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const init: RequestInit & { duplex?: "half" } = {
    method: request.method, headers, cache: "no-store", signal: AbortSignal.timeout(600_000),
  };
  if (request.method === "POST") {
    init.body = request.body;
    init.duplex = "half";
  }
  try {
    const base = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";
    const upstream = await fetch(`${base}/api/${path}`, init);
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
    });
  } catch {
    return Response.json({ error: { message: "Cannot reach FastAPI. Check that the backend is running. If an upload timed out, refresh the document list before retrying." } }, { status: 502 });
  }
}

export { proxy as GET, proxy as POST, proxy as DELETE };
