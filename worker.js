const OWNER = 'pansensoyglenn-dev';
const BRANCH = 'main';
const APP_URL = 'https://poetic-codes.pansensoyglenn150.workers.dev/';

const TARGETS = [
  { repo: 'current-situation', site: 'https://pansensoyglenn-dev.github.io/current-situation/' },
  { repo: 'poetic-codes',      site: 'https://pansensoyglenn-dev.github.io/poetic-codes/' },
];
const VERCEL_SITE = 'https://current-situation.vercel.app/';
const ALLOWED_ORIGINS = ['https://current-situation.vercel.app', 'https://pansensoyglenn-dev.github.io'];

const CATS = {
  history: 'History', philosophy: 'Philosophy', economy: 'Economy', programming: 'Programming',
  culture: 'Culture', culinary: 'Culinary', 'local-politics': 'Local Politics',
  'global-politics': 'Global Politics', weather: 'Weather', farming: 'Farming',
  ai: 'AI', 'music-video': 'Music Video',
};

const slugify = s => String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function corsHeaders(req) {
  const o = req.headers.get('Origin');
  if (!ALLOWED_ORIGINS.includes(o)) return {};
  return {
    'Access-Control-Allow-Origin': o,
    'Access-Control-Allow-Headers': 'Authorization, Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    Vary: 'Origin',
  };
}
const json = (req, data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...corsHeaders(req) },
  });

function authed(req, env) {
  const got = (req.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '');
  const want = env.ADMIN_KEY || '';
  if (!want || got.length !== want.length) return false;
  let d = 0;
  for (let i = 0; i < want.length; i++) d |= got.charCodeAt(i) ^ want.charCodeAt(i);
  return d === 0;
}

const out = r => ({
  id: r.id, title: r.title, category: r.category, date: r.date,
  content_type: r.content_type, body: r.body, summary: r.summary,
  tags: JSON.parse(r.tags || '[]'), photo_url: r.photo_url, video_url: r.video_url,
  github_url: r.github_url, page_url: r.page_url,
  deploy_status: JSON.parse(r.deploy_status || '{}'),
});

function clean(p) {
  const tags = (Array.isArray(p.tags) ? p.tags : [])
    .map(t => String(t).toLowerCase().trim().replace(/^#/, '')).filter(Boolean).slice(0, 6);
  return {
    title: String(p.title || '').trim().slice(0, 300),
    category: String(p.category || ''),
    date: /^\d{4}-\d{2}-\d{2}$/.test(p.date) ? p.date : new Date().toISOString().slice(0, 10),
    content_type: p.contentType === 'html' ? 'html' : 'text',
    body: String(p.body || ''),
    summary: String(p.summary || '').slice(0, 500),
    tags: JSON.stringify(tags),
    photo_url: p.photoUrl || null,
    video_url: p.videoUrl || null,
  };
}

const b64 = str => {
  const bytes = new TextEncoder().encode(str);
  let bin = '';
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
};
const ghHeaders = env => ({
  Authorization: `Bearer ${env.GITHUB_TOKEN}`,
  Accept: 'application/vnd.github+json',
  'User-Agent': 'commonplace-worker',
  'X-GitHub-Api-Version': '2022-11-28',
});
const ghUrl = (repo, path) =>
  `https://api.github.com/repos/${OWNER}/${repo}/contents/${path.split('/').map(encodeURIComponent).join('/')}`;

async function ghSha(env, repo, path) {
  const r = await fetch(`${ghUrl(repo, path)}?ref=${BRANCH}`, { headers: ghHeaders(env) });
  return r.ok ? (await r.json()).sha : null;
}
async function ghPut(env, repo, path, content, message) {
  const body = { message, content: b64(content), branch: BRANCH };
  const sha = await ghSha(env, repo, path);
  if (sha) body.sha = sha;
  const r = await fetch(ghUrl(repo, path), {
    method: 'PUT',
    headers: { ...ghHeaders(env), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(((await r.json().catch(() => ({}))).message) || `GitHub ${r.status}`);
}
async function ghDelete(env, repo, path, message) {
  const sha = await ghSha(env, repo, path);
  if (!sha) return;
  await fetch(ghUrl(repo, path), {
    method: 'DELETE',
    headers: { ...ghHeaders(env), 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, sha, branch: BRANCH }),
  });
}

const paths = a => {
  const base = `${a.category}/${a.date}-${slugify(a.title) || 'article-' + a.id}`;
  return { md: base + '.md', html: base + '.html' };
};

function markdown(a) {
  const tags = JSON.parse(a.tags || '[]');
  let md = '---\n';
  md += `title: ${JSON.stringify(a.title)}\ndate: ${a.date}\ncategory: ${a.category}\n`;
  md += `category_name: ${JSON.stringify(CATS[a.category] || 'Uncategorized')}\n`;
  if (a.content_type === 'html') md += 'content_type: html\n';
  if (a.summary) md += `summary: ${JSON.stringify(a.summary.replace(/\s*\n\s*/g, ' '))}\n`;
  if (tags.length) md += `tags: [${tags.map(t => JSON.stringify(t)).join(', ')}]\n`;
  if (a.photo_url) md += `image: ${JSON.stringify(a.photo_url)}\n`;
  if (a.video_url) md += `video_url: ${JSON.stringify(a.video_url)}\n`;
  return md + '---\n\n' + a.body;
}

function snippet(a) {
  if (a.summary) return a.summary;
  const plain = a.body.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  return plain.slice(0, 180) + (plain.length > 180 ? '…' : '');
}

function sharePage(a, site, pagePath) {
  const title = esc(a.title), desc = esc(snippet(a));
  const canonical = site + pagePath;
  const spa = `${APP_URL}index.html#/article/${a.id}`;
  const img = a.photo_url || `${APP_URL}covers/${a.category}.jpg`;
  return `<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${title} — The Commonplace</title>
<meta name="description" content="${desc}">
<link rel="canonical" href="${esc(canonical)}">
<meta property="og:type" content="article"><meta property="og:site_name" content="The Commonplace">
<meta property="og:title" content="${title}"><meta property="og:description" content="${desc}">
<meta property="og:url" content="${esc(canonical)}"><meta property="og:image" content="${esc(img)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${title}"><meta name="twitter:description" content="${desc}"><meta name="twitter:image" content="${esc(img)}">
<link rel="stylesheet" href="${APP_URL}styles.css">
<script>location.replace(${JSON.stringify(spa)});</script>
</head><body>
<div class="legal-page">
<a class="back-link" href="${APP_URL}index.html">← The Commonplace</a>
<h1>${title}</h1>
<p class="updated">${esc(CATS[a.category] || '')} · ${a.date}</p>
<p>${desc}</p>
<p>Redirecting to the full article… <a class="inline-link" href="${esc(spa)}">click here</a> if nothing happens.</p>
</div></body></html>`;
}

async function deploy(env, row) {
  const status = {};
  const p = paths(row);
  for (const t of TARGETS) {
    try {
      await ghPut(env, t.repo, p.md, markdown(row), `Publish: ${row.title}`);
      await ghPut(env, t.repo, p.html, sharePage(row, t.site, p.html), `Share page: ${row.title}`);
      status[t.repo] = 'ok';
    } catch (e) {
      status[t.repo] = 'error: ' + e.message;
    }
  }
  if (env.VERCEL_DEPLOY_HOOK) {
    try {
      const r = await fetch(env.VERCEL_DEPLOY_HOOK, { method: 'POST' });
      status.vercel = r.ok ? 'ok (hook)' : `error ${r.status}`;
    } catch (e) { status.vercel = 'error: ' + e.message; }
  } else {
    status.vercel = 'auto via ' + TARGETS[0].repo + ' repo';
  }
  const pageUrl = TARGETS[0].site + p.html;
  const ghBlob = `https://github.com/${OWNER}/${TARGETS[0].repo}/blob/${BRANCH}/${p.md}`;
  await env.DB.prepare('UPDATE articles SET github_url=?, page_url=?, deploy_status=? WHERE id=?')
    .bind(ghBlob, pageUrl, JSON.stringify(status), row.id).run();
  return status;
}

async function undeploy(env, row) {
  const p = paths(row);
  for (const t of TARGETS) {
    await ghDelete(env, t.repo, p.md, `Remove: ${row.title}`);
    await ghDelete(env, t.repo, p.html, `Remove: ${row.title}`);
  }
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const { pathname } = url;

    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders(req) });

    if (pathname.startsWith('/media/') && req.method === 'GET') {
      const key = decodeURIComponent(pathname.slice(7));
      if (!key.startsWith('photos/')) return new Response('Not found', { status: 404 });
      const obj = await env.MEDIA.get(key);
      if (!obj) return new Response('Not found', { status: 404 });
      return new Response(obj.body, {
        headers: {
          'Content-Type': obj.httpMetadata?.contentType || 'application/octet-stream',
          'Cache-Control': 'public, max-age=31536000, immutable',
          'Access-Control-Allow-Origin': '*',
        },
      });
    }

    if (pathname === '/api/articles' && req.method === 'GET') {
      const { results } = await env.DB.prepare('SELECT * FROM articles ORDER BY date DESC, id DESC').all();
      return json(req, results.map(out));
    }

    if (!pathname.startsWith('/api/')) return env.ASSETS.fetch(req);

    if (!authed(req, env)) return json(req, { error: 'Wrong portal password' }, 401);

    if (pathname === '/api/login') return json(req, { ok: true });

    if (pathname === '/api/upload' && req.method === 'POST') {
      const ct = url.searchParams.get('contentType') || 'image/jpeg';
      if (!/^image\//.test(ct)) return json(req, { error: 'Images only' }, 400);
      const buf = await req.arrayBuffer();
      if (buf.byteLength > 10 * 1024 * 1024) return json(req, { error: 'Photo over 10 MB' }, 413);
      const name = (url.searchParams.get('filename') || 'photo.jpg').replace(/[^a-zA-Z0-9._-]/g, '_');
      const key = `photos/${Date.now()}-${name}`;
      await env.MEDIA.put(key, buf, { httpMetadata: { contentType: ct } });
      return json(req, { url: `${url.origin}/media/${key}` });
    }

    const id = Number(url.searchParams.get('id'));

    if (pathname === '/api/articles' && req.method === 'POST') {
      const p = await req.json();
      const a = clean(p);
      if (!a.title || !a.body || !CATS[a.category]) return json(req, { error: 'Title, body and a valid section are required' }, 400);
      const r = await env.DB.prepare(
        'INSERT INTO articles (title,category,date,content_type,body,summary,tags,photo_url,video_url,github_url,page_url) VALUES (?,?,?,?,?,?,?,?,?,?,?)'
      ).bind(a.title, a.category, a.date, a.content_type, a.body, a.summary, a.tags, a.photo_url, a.video_url, p.githubUrl || null, p.pageUrl || null).run();
      const row = await env.DB.prepare('SELECT * FROM articles WHERE id=?').bind(r.meta.last_row_id).first();
      ctx.waitUntil(deploy(env, row));
      return json(req, out(row), 201);
    }

    if (pathname === '/api/articles' && req.method === 'PUT') {
      const old = await env.DB.prepare('SELECT * FROM articles WHERE id=?').bind(id).first();
      if (!old) return json(req, { error: 'Not found' }, 404);
      const a = clean(await req.json());
      if (!a.title || !a.body || !CATS[a.category]) return json(req, { error: 'Title, body and a valid section are required' }, 400);
      await env.DB.prepare(
        'UPDATE articles SET title=?,category=?,date=?,content_type=?,body=?,summary=?,tags=?,photo_url=?,video_url=? WHERE id=?'
      ).bind(a.title, a.category, a.date, a.content_type, a.body, a.summary, a.tags, a.photo_url, a.video_url, id).run();
      const row = await env.DB.prepare('SELECT * FROM articles WHERE id=?').bind(id).first();
      ctx.waitUntil((async () => {
        if (paths(old).md !== paths(row).md) await undeploy(env, old);
        await deploy(env, row);
      })());
      return json(req, out(row));
    }

    if (pathname === '/api/articles' && req.method === 'DELETE') {
      const old = await env.DB.prepare('SELECT * FROM articles WHERE id=?').bind(id).first();
      if (!old) return json(req, { error: 'Not found' }, 404);
      await env.DB.prepare('DELETE FROM articles WHERE id=?').bind(id).run();
      ctx.waitUntil(undeploy(env, old));
      return json(req, { ok: true });
    }

    if (pathname === '/api/deploy' && req.method === 'POST') {
      const row = await env.DB.prepare('SELECT * FROM articles WHERE id=?').bind(id).first();
      if (!row) return json(req, { error: 'Not found' }, 404);
      return json(req, await deploy(env, row));
    }

    return json(req, { error: 'Not found' }, 404);
  },
};
