export const SITE = "https://poetic-codes.pages.dev";
export const API = "https://poetic-codes.vercel.app/api/articles";
export const AUTHOR = "Glenn Junsay Pansensoy";

export const ADSENSE_CLIENT = "ca-pub-6428799122405621";

export const ADSENSE_SLOT = "3735753880";

export function slugify(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80)
    .replace(/-+$/, "") || "article";
}

// The one public address for an article: /article/30-ilonggo-cuisine-...
export function canonicalPath(a) {
  return `/article/${a.id}-${slugify(a.title)}`;
}

export async function loadArticles(env) {
  const url = (env && env.ARTICLES_API) || API;
  const r = await fetch(url, {
    headers: { Accept: "application/json" },
    cf: { cacheTtl: 300, cacheEverything: true },
  });
  if (!r.ok) throw new Error("articles api " + r.status);
  let data = await r.json();
  if (!Array.isArray(data)) data = data.articles || data.results || data.data || [];
  return data;
}

export function isPublic(a) {
  return a && a.id != null && a.title && !(a.draft || a.published === false || a.status === "draft");
}

export function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function validDate(d) {
  const s = String(d || "").slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : "";
}

const bodyOf = (a) => (a.content != null ? a.content : a.body != null ? a.body : "");

// Turn the stored article body (a full HTML page, an HTML fragment or plain text)
// into safe article-only HTML: no head, no header/footer, no scripts.
export function renderBody(a) {
  let s = String(bodyOf(a));
  const type = String(a.content_type || a.contentType || "html").toLowerCase();
  s = s.replace(/^\s*```[a-z]*\s*$/gim, "");
  const looksHtml = /<\/?(p|h[1-6]|div|main|body|section|article|ul|ol|li|em|strong|br)\b/i.test(s);

  if (!looksHtml || type === "text" || type === "markdown") {
    return s
      .split(/\n{2,}/)
      .map((chunk) => chunk.trim())
      .filter(Boolean)
      .map((chunk) => {
        const h = chunk.match(/^(#{1,3})\s+(.*)$/);
        if (h) return `<h${h[1].length + 1}>${esc(h[2])}</h${h[1].length + 1}>`;
        return `<p>${esc(chunk).replace(/\n/g, "<br>")}</p>`;
      })
      .join("\n");
  }

  const main = s.match(/<main\b[^>]*>([\s\S]*)<\/main\s*>/i);
  if (main) {
    s = main[1];
  } else {
    const body = s.match(/<body\b[^>]*>([\s\S]*)<\/body\s*>/i);
    if (body) s = body[1];
    s = s
      .replace(/<head\b[\s\S]*?<\/head>/gi, "")
      .replace(/<(header|footer|nav|aside)\b[\s\S]*?<\/\1>/gi, "");
  }
  s = s
    .replace(/<(script|style|iframe|noscript|object|embed|form)\b[\s\S]*?<\/\1>/gi, "")
    .replace(/<(script|style|iframe|object|embed|link|meta)\b[^>]*\/?>/gi, "")
    .replace(/\son[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, "")
    .replace(/(href|src)\s*=\s*(["'])\s*javascript:[^"']*\2/gi, "$1=$2#$2");
  if (!ADSENSE_CLIENT) s = s.replace(/<ins\b[\s\S]*?<\/ins>/gi, "");
  return s;
}

function plain(html) {
  return html
    .replace(/<ins\b[\s\S]*?<\/ins>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z#0-9]+;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function description(a) {
  const given = a.excerpt || a.summary;
  if (given) return plain(String(given)).slice(0, 300);
  const t = plain(renderBody(a));
  return t.length > 155 ? t.slice(0, 155).replace(/\s+\S*$/, "") + "…" : t;
}

export function page(a) {
  const url = SITE + canonicalPath(a);
  const desc = description(a);
  const date = validDate(a.date);
  const photo = a.photo_url || a.photoUrl || "";
  const author = a.author || AUTHOR;
  const ld = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: a.title,
    description: desc,
    author: { "@type": "Person", name: author },
    publisher: { "@type": "Organization", name: "Poetic Codes", url: SITE },
    mainEntityOfPage: { "@type": "WebPage", "@id": url },
  };
  if (date) {
    ld.datePublished = date;
    ld.dateModified = date;
  }
  if (photo) ld.image = photo;
  const ads = !!ADSENSE_CLIENT;
  let bodyHtml = renderBody(a);
  if (ads && !/<ins\b/i.test(bodyHtml)) {
    bodyHtml += `\n<div class="ad-slot"><ins class="adsbygoogle" style="display:block" data-ad-client="${ADSENSE_CLIENT}" data-ad-slot="${ADSENSE_SLOT}" data-ad-format="auto" data-full-width-responsive="true"></ins></div>`;
  }
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(a.title)} | Poetic Codes</title>
<meta name="description" content="${esc(desc)}">
<meta name="author" content="${esc(author)}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="${url}">
<meta property="og:type" content="article">
<meta property="og:title" content="${esc(a.title)}">
<meta property="og:description" content="${esc(desc)}">
<meta property="og:url" content="${url}">
<meta property="og:site_name" content="Poetic Codes">
${photo ? `<meta property="og:image" content="${esc(photo)}">\n` : ""}<meta name="twitter:card" content="${photo ? "summary_large_image" : "summary"}">
<script type="application/ld+json">${JSON.stringify(ld).replace(/</g, "\\u003c")}</script>
${ads ? `<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${ADSENSE_CLIENT}" crossorigin="anonymous"></script>\n` : ""}<style>
:root{--bg:#fcf9f4;--text:#1e1e1e;--muted:#4a4a4a;--accent:#0b5e7a;--rule:#d9d2c7;--card:#fff}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Georgia,'Times New Roman',serif;line-height:1.75;background:var(--bg);color:var(--text);padding:1.5rem}
.container{max-width:820px;margin:0 auto;background:var(--card);padding:2.2rem 2.2rem 2.8rem;border-radius:8px;box-shadow:0 2px 16px rgba(0,0,0,.04)}
header{border-bottom:2px solid var(--accent);margin-bottom:1.8rem;padding-bottom:1rem}
.kicker,.byline,footer{font-family:'Helvetica Neue',Arial,sans-serif;font-size:.9rem;color:var(--muted)}
.kicker a,footer a{color:var(--accent);text-decoration:none}
h1{font-size:2.1rem;line-height:1.25;margin:.4rem 0 .6rem;color:#111}
h2{font-size:1.5rem;margin:2rem 0 .7rem;color:var(--accent);border-bottom:1px solid var(--rule);padding-bottom:.3rem}
h3{font-size:1.2rem;margin:1.6rem 0 .4rem}
p{margin-bottom:1.15rem}
ol,ul{margin:0 0 1.2rem 1.8rem}
img{max-width:100%;height:auto;border-radius:6px;margin-bottom:1.4rem}
.ad-slot{margin:2rem 0;text-align:center;min-height:90px}
footer{margin-top:2.5rem;padding-top:1.2rem;border-top:1px solid var(--rule)}
@media(max-width:600px){body{padding:.8rem}.container{padding:1.4rem 1.1rem 2rem}h1{font-size:1.6rem}h2{font-size:1.25rem}}
</style>
</head>
<body>
<article class="container">
<header>
<p class="kicker"><a href="/">Poetic Codes</a>${a.category ? " · " + esc(a.category) : ""}</p>
<h1>${esc(a.title)}</h1>
<p class="byline">By ${esc(author)}${date ? " · " + date : ""}</p>
</header>
${photo ? `<img src="${esc(photo)}" alt="${esc(a.title)}">\n` : ""}<div class="body">
${bodyHtml}
</div>
<footer><a href="/">More essays on Poetic Codes</a></footer>
</article>
${ads ? `<script>document.querySelectorAll("ins.adsbygoogle").forEach(function(){try{(window.adsbygoogle=window.adsbygoogle||[]).push({})}catch(e){}})</script>\n` : ""}</body>
</html>`;
}
