/* Poetic Bytes: adds the lesson video to a page, by itself.
   Put this file in the root of the Poetic Bytes site and add ONE line to a lesson page (best: in the shared layout/footer):
       <script src="/lesson-video.js" defer></script>
   It finds the Poetic Codes article whose title equals this page's <title>. If that article has a video, a player is
   inserted right under the page's first heading. If there is no video yet, nothing is added and the page is unchanged. */
(function () {
  "use strict";
  var API = "https://poetic-codes.vercel.app/api/articles";
  function norm(s) { return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim(); }
  function show(url) {
    if (document.getElementById("lesson-video")) return;
    var box = document.createElement("section");
    box.id = "lesson-video";
    box.style.cssText = "max-width:900px;margin:1.5rem auto;padding:0 1rem;";
    box.innerHTML = '<h2 style="margin:0 0 .6rem;font-size:1.15rem;">Watch the video lesson</h2>' +
      '<video controls playsinline preload="metadata" style="width:100%;border-radius:12px;background:#000;"></video>';
    box.querySelector("video").src = url;
    var h1 = document.querySelector("h1");
    var anchor = h1 && (h1.closest("header") || h1);
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(box, anchor.nextSibling);
    else (document.querySelector("main") || document.body).insertBefore(box, (document.querySelector("main") || document.body).firstChild);
  }
  function run() {
    fetch(API, { headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var rows = Array.isArray(d) ? d : (d.articles || d.results || d.data || []);
        var me = norm(document.title);
        for (var i = 0; i < rows.length; i++) {
          var v = rows[i].video_url || rows[i].videoUrl;
          if (v && norm(rows[i].title) === me) { show(v); return; }
        }
      })
      .catch(function () { /* no video available: the page stays as it is */ });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
})();
