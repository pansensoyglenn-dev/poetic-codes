(function () {
  'use strict';

  var CSS = [
    '.pr-controls{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1rem;align-items:center;}',
    '.pr-controls .field-select{width:auto;min-width:150px;padding:.45rem .7rem;font-size:.8rem;}',
    '.pr-controls .webhook-input{flex:1;min-width:160px;padding:.55rem .8rem;}',
    '.pr-count{font-family:"JetBrains Mono",monospace;font-size:.6rem;color:var(--dim);margin-left:.4rem;}',
    '.pr-row-main{flex:1;min-width:0;}',
    '.pr-snippet{font-size:.8rem;color:var(--muted);line-height:1.5;margin-top:3px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}',
    '.pr-btns{display:flex;gap:.4rem;flex-shrink:0;}',
    '#pr-modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.78);z-index:1700;overflow-y:auto;padding:1.5rem .8rem;}',
    '.pr-paper{max-width:780px;margin:0 auto;background:#faf6ee;color:#2a1a0f;border-radius:16px;padding:2rem 1.6rem 1.6rem;position:relative;}',
    '.pr-paper .preview-close{background:#faf6ee;color:#5a4a3a;border-color:#c8bdb0;}',
    '.pr-paper h1{font-family:Georgia,serif;font-size:1.6rem;line-height:1.2;color:#1a0f08;margin:1.6rem 0 .4rem;}',
    '.pr-meta{font-family:"JetBrains Mono",monospace;font-size:.7rem;color:#7a6a58;margin-bottom:.8rem;}',
    '.pr-sum{font-style:italic;color:#5a4a3a;border-left:3px solid #8B5E34;padding-left:.8rem;margin:.6rem 0 1.2rem;}',
    '.pr-tags span{display:inline-block;font-family:"JetBrains Mono",monospace;font-size:.65rem;color:#7a3e1a;background:rgba(139,94,52,.12);border-radius:20px;padding:.1rem .6rem;margin:0 .3rem .3rem 0;}',
    '.pr-body{font-family:Georgia,serif;font-size:1.05rem;line-height:1.85;color:#2a1a0f;}',
    '.pr-body p{margin:0 0 1.3rem;text-align:justify;}',
    '.pr-body h2,.pr-body h3{color:#1a0f08;margin:1.8rem 0 .8rem;}',
    '.pr-body img,.pr-body video{max-width:100%;border-radius:8px;}',
    '.pr-body a{color:#7a3e1a;}',
    '.pr-video{position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:10px;margin:1rem 0;background:#000;}',
    '.pr-video iframe{position:absolute;inset:0;width:100%;height:100%;border:0;}',
    '.pr-actions{display:flex;gap:.6rem;flex-wrap:wrap;margin-top:1.6rem;padding-top:1rem;border-top:1px solid #d8cdbb;}'
  ].join('\n');

  var BAD_TAGS = { SCRIPT:1, STYLE:1, IFRAME:1, OBJECT:1, EMBED:1, LINK:1, META:1, FORM:1, BASE:1, FRAME:1, FRAMESET:1, APPLET:1, NOSCRIPT:1 };

  function clean(html) {
    var t = document.createElement('template');
    t.innerHTML = html || '';
    (function walk(node) {
      Array.prototype.slice.call(node.childNodes).forEach(function (c) {
        if (c.nodeType !== 1) return;
        if (BAD_TAGS[c.tagName.toUpperCase()]) { c.remove(); return; }
        Array.prototype.slice.call(c.attributes).forEach(function (a) {
          var name = a.name.toLowerCase();
          var val  = a.value.replace(/[\u0000-\u0020\u007f-\u009f]+/g, '').toLowerCase();
          if (name.indexOf('on') === 0 || name === 'srcdoc' || name === 'formaction') {
            c.removeAttribute(a.name);
          } else if (name === 'href' || name === 'src' || name === 'xlink:href' || name === 'action' || name === 'data') {
            var badScheme = /^(javascript|vbscript):/.test(val);
            var badData   = /^data:/.test(val) && !(name === 'src' && /^data:image\/(png|jpe?g|gif|webp|avif);/.test(val));
            if (badScheme || badData) c.removeAttribute(a.name);
          } else if (name === 'style' && /expression|javascript:|url\(/.test(val)) {
            c.removeAttribute(a.name);
          }
        });
        walk(c);
      });
    })(t.content);
    return t.innerHTML;
  }

  function plainText(html) {
    return String(html || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  }

  function bodyHtml(a) {
    var b = a.body || '';
    if (a.contentType === 'html' || looksLikeHTML(b)) return clean(b);
    return b.split(/\n\s*\n/).map(function (p) { return p.trim(); }).filter(Boolean)
      .map(function (p) { return '<p>' + esc(p).replace(/\n/g, '<br>') + '</p>'; }).join('');
  }

  function videoBlock(url) {
    if (!url) return '';
    var yt = getYouTubeId(url);
    if (yt) {
      return '<div class="pr-video"><iframe src="https://www.youtube-nocookie.com/embed/' + yt +
        '" title="Video" loading="lazy" allowfullscreen></iframe></div>';
    }
    return '<video controls playsinline preload="metadata" src="' + esc(url) + '"></video>';
  }

  window.fetchCommonplaceArticles = async function () {
    var settled = await Promise.allSettled(CS_SOURCES.map(csFetchSource));
    var merged = new Map();
    var notes = [];
    var okCount = 0;
    settled.forEach(function (r, i) {
      var src = CS_SOURCES[i];
      if (r.status === 'fulfilled') {
        okCount++;
        notes.push(src.label + ': ' + r.value.length);
        r.value.forEach(function (a) {
          var k = a.title.toLowerCase() + '|' + a.date.slice(0, 10);
          var ex = merged.get(k);
          if (!ex) { a._ids = {}; a._ids[a._source] = a.id; merged.set(k, a); return; }
          ex._ids[a._source] = a.id;
          if (!ex.body && a.body) ex.body = a.body;
          if (!ex.summary && a.summary) ex.summary = a.summary;
          if (!ex.videoUrl && a.videoUrl) ex.videoUrl = a.videoUrl;
          if (!ex.photoUrl && a.photoUrl) ex.photoUrl = a.photoUrl;
          if (!ex.tags.length && a.tags.length) ex.tags = a.tags;
        });
      } else {
        notes.push(src.label + ': failed (' + ((r.reason && r.reason.message) || r.reason) + ')');
      }
    });
    if (okCount === 0) throw new Error(notes.join(' · '));
    return { articles: Array.from(merged.values()), notes: notes };
  };

  var origLoad = window.loadCsArticleIntoForm;
  window.loadCsArticleIntoForm = function (article) {
    origLoad(article);
    var ids = article._ids || {};
    if (article.id != null && ids[article._source] == null) ids[article._source] = article.id;
    var main = ids.worker != null ? ids.worker : ids.vercel;
    if (main != null) {
      csEditing = {
        id: main, ids: ids, date: article.date, category: article.category,
        photoUrl: article.photoUrl || '', title: article.title
      };
    }
    updateEditUI(article);
  };

  window.updateEditUI = function () {
    var banner = document.getElementById('edit-banner');
    var btn = document.getElementById('update-btn');
    if (!banner || !btn) return;
    if (csEditing) {
      var where = [];
      if (csEditing.ids && csEditing.ids.worker != null) where.push('Worker');
      if (csEditing.ids && csEditing.ids.vercel != null) where.push('Vercel');
      banner.style.display = 'block';
      banner.textContent = 'Editing entry #' + csEditing.id + (where.length ? ' · Update entry saves to: ' + where.join(' + ') : '');
      btn.style.display = 'inline-flex';
    } else {
      banner.style.display = 'none';
      btn.style.display = 'none';
    }
  };

  async function saveWorker(id, body) {
    var r = await fetch(COMMONPLACE_API + 'articles/' + encodeURIComponent(id), {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    });
    if (!r.ok) {
      var j = await r.json().catch(function () { return {}; });
      if (r.status === 404 || r.status === 405) {
        throw new Error('the Worker needs a PUT /api/articles/:id route (HTTP ' + r.status + ')');
      }
      throw new Error(j.error || 'HTTP ' + r.status);
    }
  }

  async function saveVercel(id, base) {
    var cur = null;
    try {
      var lr = await fetch(CS_SOURCE_API, { cache: 'no-store', headers: { Accept: 'application/json' } });
      if (lr.ok) {
        var rows = await lr.json();
        if (Array.isArray(rows)) {
          cur = rows.find(function (x) { return String(x.id) === String(id); }) || null;
        }
      }
    } catch (e) { }
    if (!cur) throw new Error('could not read the current record first, so nothing was changed');

    function pick(a, b) { return cur[a] != null ? cur[a] : (cur[b] != null ? cur[b] : null); }
    var body = Object.assign({}, base, {
      photoUrl:   pick('photo_url', 'photoUrl') || base.photoUrl,
      githubUrl:  pick('github_url', 'githubUrl'),
      pageUrl:    pick('page_url', 'pageUrl'),
      bloggerUrl: pick('blogger_url', 'bloggerUrl')
    });
    var r = await fetch(CS_SOURCE_API + '?id=' + encodeURIComponent(id), {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    });
    if (!r.ok) {
      var j = await r.json().catch(function () { return {}; });
      throw new Error(j.error || 'HTTP ' + r.status);
    }
  }

  async function updateEntry() {
    if (!csEditing) { showToast('Nothing to update — tap Edit on an article first.', 'error'); return; }
    var title    = document.getElementById('f-title').value.trim();
    var category = document.getElementById('f-category').value;
    var excerpt  = document.getElementById('f-excerpt').value.trim();
    var tags     = document.getElementById('f-tags').value.split(',').map(function (t) { return t.trim(); }).filter(Boolean);
    var errorBox = document.getElementById('publish-error-box');
    var btn      = document.getElementById('update-btn');
    errorBox.style.display = 'none';

    if (!title)    { showToast('Title is required.', 'error'); return; }
    if (!category) { showToast('Select a section.', 'error'); return; }
    if (!excerpt)  { showToast('Excerpt is required.', 'error'); return; }
    var content = getContentHTML();
    if (!content)  { showToast('Content is empty.', 'error'); return; }
    var payload = commonplacePayload(content, title, '');
    if (payload.skip) { showToast('Video: ' + payload.skip, 'error', 4000); return; }

    var ids = csEditing.ids || { worker: csEditing.id };
    var base = {
      title: title,
      category: CP_CATEGORY[category] || csEditing.category || 'culture',
      date: (csEditing.date || '').slice(0, 10) || new Date().toLocaleDateString('en-CA'),
      contentType: 'html',
      body: payload.body,
      summary: excerpt,
      tags: tags,
      photoUrl: csEditing.photoUrl || null,
      videoUrl: payload.videoUrl
    };

    var original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Saving…';

    var done = [], failed = [];
    if (ids.worker != null) {
      try { await saveWorker(ids.worker, base); done.push('Worker'); }
      catch (e) { failed.push('Worker: ' + e.message); }
    }
    if (ids.vercel != null) {
      try { await saveVercel(ids.vercel, base); done.push('Vercel'); }
      catch (e) { failed.push('Vercel: ' + e.message); }
    }

    btn.disabled = false;
    btn.innerHTML = original;

    if (failed.length) {
      errorBox.textContent = (done.length ? 'Saved to: ' + done.join(', ') + '\n' : '') + 'Failed → ' + failed.join('\n');
      errorBox.style.display = 'block';
      showToast(done.length ? 'Partly updated — see error below.' : 'Update failed — see error below.', 'error', 6000);
    } else {
      showToast('Entry #' + csEditing.id + ' updated (' + done.join(' + ') + ').', 'success', 4000);
    }
    if (done.length) loadList(true);
  }

  var hashHandled = false;

  function injectUi() {
    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    var navRight = document.querySelector('#navbar div');
    if (navRight) {
      var link = document.createElement('a');
      link.className = 'nav-link';
      link.href = '#articles-reader';
      link.innerHTML = '<i class="fas fa-book-open" aria-hidden="true"></i> All Articles';
      navRight.insertBefore(link, navRight.firstChild);
    }

    var sec = document.createElement('section');
    sec.id = 'articles-reader';
    sec.className = 'submit-box';
    sec.style.marginTop = '2rem';
    sec.setAttribute('aria-labelledby', 'pr-heading');
    sec.innerHTML =
      '<h2 id="pr-heading" class="section-title"><i class="fas fa-book-open" aria-hidden="true"></i> All Articles' +
      '<span class="pr-count" id="pr-count"></span></h2>' +
      '<div class="pr-controls">' +
        '<select id="pr-section" class="field-select" aria-label="Filter by section"><option value="">All sections</option></select>' +
        '<input type="text" id="pr-search" class="webhook-input" placeholder="Search title, tags or text…" aria-label="Search articles">' +
        '<button class="btn-save-hook" id="pr-refresh" type="button">Refresh</button>' +
      '</div>' +
      '<ul id="pr-list" class="cs-picker-list" style="max-height:none;"></ul>' +
      '<div id="pr-status" style="font-family:\'JetBrains Mono\',monospace;font-size:.6rem;color:var(--muted);margin-top:.8rem;min-height:1rem;"></div>';
    var anchor = document.getElementById('success-state');
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(sec, anchor.nextSibling);
    else document.querySelector('#main .container').appendChild(sec);

    var sel = document.getElementById('pr-section');
    Object.keys(CS_SLUG_TO_SECTION).forEach(function (slug) {
      var o = document.createElement('option');
      o.value = CS_SLUG_TO_SECTION[slug];
      o.textContent = CS_SLUG_TO_SECTION[slug];
      sel.appendChild(o);
    });

    var modal = document.createElement('div');
    modal.id = 'pr-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.innerHTML = '<div class="pr-paper"><button class="preview-close" id="pr-close" type="button" aria-label="Close">✕ Close</button><div id="pr-article"></div></div>';
    document.body.appendChild(modal);
  }

  function filtered() {
    var sec = document.getElementById('pr-section').value;
    var q = document.getElementById('pr-search').value.trim().toLowerCase();
    return csArticlesCache.filter(function (a) {
      var section = csSectionFor(a.category) || a.category;
      if (sec && section !== sec) return false;
      if (!q) return true;
      return a.title.toLowerCase().indexOf(q) !== -1 ||
        (a.tags || []).some(function (t) { return String(t).toLowerCase().indexOf(q) !== -1; }) ||
        plainText(a.body).toLowerCase().indexOf(q) !== -1;
    }).sort(function (a, b) { return b.date.localeCompare(a.date); });
  }

  function renderList() {
    var list = document.getElementById('pr-list');
    var items = filtered();
    document.getElementById('pr-count').textContent = '(' + items.length + ' of ' + csArticlesCache.length + ')';
    if (!items.length) {
      list.innerHTML = '<li style="padding:1rem;text-align:center;color:var(--dim);font-family:\'JetBrains Mono\',monospace;font-size:.65rem;">No articles found.</li>';
      return;
    }
    list.innerHTML = items.map(function (a) {
      var section = csSectionFor(a.category) || a.category || 'Uncategorised';
      var snippet = a.summary || plainText(a.body).slice(0, 180);
      var where = Object.keys(a._ids || {}).map(function (k) { return k === 'worker' ? 'Worker' : 'Vercel'; }).join(' + ');
      return '<li class="cs-picker-row" data-key="' + esc(a._key) + '">' +
        '<div class="pr-row-main">' +
          '<div class="cs-picker-title">' + esc(a.title || '(untitled)') + '</div>' +
          '<div class="cs-picker-meta">' + esc(section) + ' · ' + esc(a.date.slice(0, 10)) + '<span class="cs-src-badge">' + esc(where) + '</span></div>' +
          (snippet ? '<div class="pr-snippet">' + esc(snippet) + '</div>' : '') +
        '</div>' +
        '<div class="pr-btns">' +
          '<button type="button" class="cs-edit-btn" data-act="read">Read</button>' +
          '<button type="button" class="cs-edit-btn" data-act="edit"><i class="fas fa-pen" aria-hidden="true"></i> Edit</button>' +
        '</div></li>';
    }).join('');
  }

  function openReader(a) {
    var section = csSectionFor(a.category) || a.category || '';
    var tags = (a.tags || []).map(function (t) { return '<span>#' + esc(t) + '</span>'; }).join('');
    document.getElementById('pr-article').innerHTML =
      '<h1>' + esc(a.title) + '</h1>' +
      '<div class="pr-meta">' + esc(section) + (section ? ' · ' : '') + esc(a.date.slice(0, 10)) + '</div>' +
      (a.summary ? '<p class="pr-sum">' + esc(a.summary) + '</p>' : '') +
      (tags ? '<div class="pr-tags">' + tags + '</div>' : '') +
      videoBlock(a.videoUrl) +
      '<div class="pr-body">' + bodyHtml(a) + '</div>' +
      '<div class="pr-actions">' +
        '<button class="btn-primary" id="pr-edit-btn" type="button"><i class="fas fa-pen" aria-hidden="true"></i> Edit this entry</button>' +
        '<button class="btn-outline" id="pr-close2" type="button">Close</button>' +
      '</div>';
    document.getElementById('pr-edit-btn').addEventListener('click', function () { closeReader(); startEdit(a); });
    document.getElementById('pr-close2').addEventListener('click', closeReader);
    var m = document.getElementById('pr-modal');
    m.style.display = 'block';
    m.scrollTop = 0;
    document.body.style.overflow = 'hidden';
  }

  function closeReader() {
    document.getElementById('pr-modal').style.display = 'none';
    document.body.style.overflow = '';
  }

  function startEdit(a) {
    csImportQueue = [];
    loadCsArticleIntoForm(a);
  }

  function byKey(k) {
    return csArticlesCache.find(function (a) { return a._key === k; });
  }

  async function loadList(quiet) {
    var status = document.getElementById('pr-status');
    if (!quiet) {
      status.textContent = 'Loading articles from the Worker and Vercel…';
      document.getElementById('pr-list').innerHTML =
        '<li style="padding:1rem;text-align:center;color:var(--dim);font-family:\'JetBrains Mono\',monospace;font-size:.65rem;">Loading…</li>';
    }
    try {
      var res = await fetchCommonplaceArticles();
      csArticlesCache = res.articles;
      status.textContent = '✅ ' + res.articles.length + ' article(s) — ' + res.notes.join(' · ');
      renderList();
      handleEditHash();
    } catch (e) {
      status.textContent = '⚠️ ' + e.message;
      document.getElementById('pr-list').innerHTML =
        '<li style="padding:1rem;color:var(--rose);font-family:\'JetBrains Mono\',monospace;font-size:.65rem;">Failed to load: ' + esc(e.message) + '</li>';
    }
  }

  function handleEditHash() {
    if (hashHandled) return;
    var m = location.hash.match(/^#edit=([\w-]+)$/);
    if (!m) return;
    hashHandled = true;
    var id = m[1];
    var a = csArticlesCache.find(function (x) {
      return x._ids && (String(x._ids.vercel) === id || String(x._ids.worker) === id);
    });
    try { history.replaceState(null, '', location.pathname + location.search); } catch (e) {}
    if (a) startEdit(a);
    else showToast('Could not find entry #' + id + ' to edit.', 'error', 5000);
  }

  function init() {
    injectUi();

    var oldBtn = document.getElementById('update-btn');
    var newBtn = oldBtn.cloneNode(true);
    newBtn.innerHTML = '<i class="fas fa-save" aria-hidden="true"></i> Update entry';
    oldBtn.parentNode.replaceChild(newBtn, oldBtn);
    newBtn.addEventListener('click', updateEntry);

    document.getElementById('pr-refresh').addEventListener('click', function () { loadList(false); });
    document.getElementById('pr-section').addEventListener('change', renderList);
    document.getElementById('pr-search').addEventListener('input', renderList);
    document.getElementById('pr-close').addEventListener('click', closeReader);
    document.getElementById('pr-modal').addEventListener('click', function (e) {
      if (e.target === this) closeReader();
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeReader(); });
    document.getElementById('pr-list').addEventListener('click', function (e) {
      var li = e.target.closest('.cs-picker-row');
      if (!li) return;
      var a = byKey(li.getAttribute('data-key'));
      if (!a) return;
      var btn = e.target.closest('[data-act]');
      if (btn && btn.getAttribute('data-act') === 'edit') startEdit(a);
      else openReader(a);
    });

    loadList(false);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
