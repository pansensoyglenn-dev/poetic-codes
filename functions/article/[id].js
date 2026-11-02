// Serves https://poetic-codes.pages.dev/article/30-some-title  (real, crawlable article pages)
import { loadArticles, isPublic, canonicalPath, page } from "../_lib/articles.js";

export async function onRequestGet({ params, env, request }) {
  const id = parseInt(String(params.id), 10); // "30-some-title" -> 30
  if (!Number.isFinite(id)) return notFound();

  let rows;
  try {
    rows = await loadArticles(env);
  } catch (e) {
    return new Response("Temporarily unavailable. Please try again shortly.", {
      status: 503,
      headers: { "Retry-After": "300", "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const a = rows.find((r) => String(r.id) === String(id));
  if (!a || !isPublic(a)) return notFound();

  // /article/30 or a stale slug -> redirect to the one canonical address
  const url = new URL(request.url);
  const canon = canonicalPath(a);
  if (url.pathname !== canon) return Response.redirect(url.origin + canon, 301);

  return new Response(page(a), {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "public, max-age=300, s-maxage=3600",
    },
  });
}

function notFound() {
  return new Response("Article not found", {
    status: 404,
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
