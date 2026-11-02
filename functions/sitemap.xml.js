
import { loadArticles, isPublic, canonicalPath, validDate, esc, SITE } from "./_lib/articles.js";

const PAGES = ["/", "/history.html", "/philosophy.html", "/culinary.html", "/local-politics.html"];

export async function onRequestGet({ env }) {
  let rows;
  try {
    rows = await loadArticles(env);
  } catch (e) {
    // Better an error Google retries than an empty sitemap it believes.
    return new Response("Sitemap temporarily unavailable", {
      status: 503,
      headers: { "Retry-After": "600", "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const articles = rows
    .filter(isPublic)
    .sort((x, y) => Number(y.id) - Number(x.id))
    .map((a) => {
      const d = validDate(a.date);
      return `  <url><loc>${esc(SITE + canonicalPath(a))}</loc>${d ? `<lastmod>${d}</lastmod>` : ""}</url>`;
    });
  const pages = PAGES.map((p) => `  <url><loc>${SITE}${p}</loc></url>`);

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${[...pages, ...articles].join("\n")}
</urlset>
`;
  return new Response(xml, {
    headers: {
      "Content-Type": "application/xml; charset=utf-8",
      "Cache-Control": "public, max-age=600, s-maxage=3600",
    },
  });
}
