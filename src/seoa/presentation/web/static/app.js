/* Small progressive-enhancement script. All dynamic text is written through textContent only. */
(function () {
  "use strict";
  var TERMINAL = ["completed", "partial", "failed", "canceled"];

  function postJSON(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body || {}),
    });
  }

  // ---- progress page: a counter, a ring, changing messages and a checklist
  var box = document.querySelector("[data-progress]");
  if (box) {
    var id = box.getAttribute("data-audit-id");
    var lang = box.getAttribute("data-lang") || "tr";
    var ringEl = document.getElementById("pring");
    var barEl = document.getElementById("pbar");
    var pctEl = document.getElementById("ppct");
    var labelEl = document.getElementById("plabel");
    var msgEl = document.getElementById("pmsg");
    var nowEl = document.getElementById("pnow");
    var headEl = document.getElementById("pheadline");
    var openEl = document.getElementById("popen");
    var steps = [].slice.call(document.querySelectorAll("#plist li"));
    var groups = [].slice.call(document.querySelectorAll("#pmsgs ul")).map(function (ul) {
      return {
        id: ul.getAttribute("data-group"),
        stages: (ul.getAttribute("data-stages") || "").split(" "),
        msgs: [].slice.call(ul.querySelectorAll("li")).map(function (li) { return li.textContent; })
      };
    });
    var starts = steps.map(function (li) { return parseInt(li.getAttribute("data-from"), 10) || 0; });
    var CIRC = 653.45;
    var current = 0;          // index of the step that is running
    var shown = 0;            // the number on screen; it never runs ahead of the real step
    var tick = 0;
    var finished = false;
    var redirectAt = 0;
    var render = function () {
      pctEl.textContent = String(shown);
      barEl.setAttribute("aria-valuenow", String(shown));
      ringEl.style.strokeDashoffset = String(CIRC * (1 - shown / 100));
      steps.forEach(function (li, i) {
        li.className = finished || i < current ? "done" : (i === current ? "current" : "");
      });
    };
    var message = function () {
      var list = (groups[current] && groups[current].msgs) || [];
      if (finished) return box.getAttribute("data-msg-ready");
      return list.length ? list[Math.floor(tick / 13) % list.length] : "";
    };
    var timer = setInterval(function () {
      tick += 1;
      var target = finished ? 100 : starts[current] || 0;
      var ceiling = finished ? 100 : (current + 1 < starts.length ? starts[current + 1] - 1 : 99);
      if (shown < target) shown = Math.min(target, shown + (target - shown > 12 ? 2 : 1));
      else if (shown < ceiling && tick % 7 === 0) shown += 1;
      // the text fades out for two ticks every time it changes
      var phase = tick % 13;
      var text = message();
      if (phase <= 1 && !finished) msgEl.classList.add("out");
      else { msgEl.classList.remove("out"); if (msgEl.textContent !== text) msgEl.textContent = text; }
      render();
      if (finished && shown >= 100) {
        msgEl.classList.remove("out");
        msgEl.textContent = box.getAttribute("data-msg-ready");
        barEl.classList.add("done");
        labelEl.textContent = box.getAttribute("data-msg-ring-done");
        nowEl.textContent = box.getAttribute("data-msg-finished");
        headEl.textContent = box.getAttribute("data-msg-headline-done");
        openEl.hidden = false;
        clearInterval(timer);
        setTimeout(function () { window.location.href = openEl.getAttribute("href"); }, 1400);
      }
    }, 140);
    render();
    var finish = function () { finished = true; };
    var onEvent = function (ev) {
      var d;
      try { d = JSON.parse(ev.data); } catch (e) { return; }
      if (d.stage) {
        for (var i = 0; i < groups.length; i++) {
          if (groups[i].stages.indexOf(d.stage) !== -1) { if (i > current) { current = i; tick = 0; } break; }
        }
      }
      if (d.status && TERMINAL.indexOf(d.status) !== -1 && !d.stage) finish();
    };
    if (window.EventSource) {
      var es = new EventSource("/v1/audits/" + encodeURIComponent(id) + "/events");
      es.onmessage = onEvent;
      ["stage", "audit"].forEach(function (n) { es.addEventListener(n, onEvent); });
      es.onerror = function () { es.close(); };
    }
    // Fallback / safety net: poll the status.
    var poll = function () {
      if (finished) return;
      fetch("/v1/audits/" + encodeURIComponent(id), { headers: { Accept: "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (j) { if (TERMINAL.indexOf(j.status) !== -1) finish(); else setTimeout(poll, 2000); })
        .catch(function () { setTimeout(poll, 3000); });
    };
    setTimeout(poll, 2500);
  }

  // ---- cancel
  document.querySelectorAll("[data-cancel]").forEach(function (b) {
    b.addEventListener("click", function () {
      postJSON(b.getAttribute("data-cancel")).then(function () { window.location.reload(); });
    });
  });

  // ---- rerun buttons
  document.querySelectorAll("[data-action-post]").forEach(function (b) {
    b.addEventListener("click", function () {
      var modules = (b.getAttribute("data-modules") || "").split(",").filter(Boolean);
      b.disabled = true;
      postJSON(b.getAttribute("data-action-post"), { modules: modules })
        .then(function (r) { return r.json(); })
        .then(function (j) { if (j && j.id) window.location.href = "/audits/" + encodeURIComponent(j.id); else b.disabled = false; })
        .catch(function () { b.disabled = false; });
    });
  });

  // ---- Q&A
  var form = document.querySelector("[data-qa-form]");
  if (form) {
    var out = document.getElementById("qa-out");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var input = form.querySelector("input[type=text]");
      var q = input.value.trim();
      if (!q) return;
      out.textContent = form.getAttribute("data-msg-thinking");
      postJSON("/v1/audits/" + encodeURIComponent(form.getAttribute("data-audit-id")) + "/qa", { question: q })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          out.textContent = "";
          if (!res.ok) { out.textContent = form.getAttribute("data-msg-error"); return; }
          var box2 = document.createElement("div");
          box2.className = "qa-answer";
          var p = document.createElement("p");
          p.textContent = res.j.out_of_scope ? form.getAttribute("data-msg-oos") : res.j.answer;
          box2.appendChild(p);
          if (res.j.citations && res.j.citations.length) {
            var h = document.createElement("p");
            h.className = "muted small";
            h.textContent = form.getAttribute("data-msg-citations") + ": ";
            res.j.citations.forEach(function (c, i) {
              var s = document.createElement("code");
              s.textContent = c.finding_id || c.score_ref || c.url || "";
              if (i) h.appendChild(document.createTextNode(", "));
              h.appendChild(s);
            });
            box2.appendChild(h);
          }
          out.appendChild(box2);
        })
        .catch(function () { out.textContent = form.getAttribute("data-msg-error"); });
    });
  }

  // ---- chat page: messages are built with textContent only
  var chat = document.querySelector("[data-chat-form]");
  if (chat) {
    var log = document.getElementById("chat-log");
    var empty = document.getElementById("chat-empty");
    var suggest = document.getElementById("chat-suggest");
    var box = chat.querySelector("textarea");
    var auditId = chat.getAttribute("data-audit-id");
    var chatLang = chat.getAttribute("data-lang") || "tr";
    var busy = false;
    var el = function (tag, cls, text) {
      var n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text !== undefined) n.textContent = text;
      return n;
    };
    var scrollDown = function () { window.scrollTo(0, document.body.scrollHeight); };
    var cites = {};
    try { cites = JSON.parse(chat.getAttribute("data-cites") || "{}"); } catch (e) { cites = {}; }
    var addSources = function (parent, citations) {
      var seen = {};
      var items = [];
      (citations || []).forEach(function (c) {
        var cm = c.finding_id ? cites[c.finding_id] : null;
        var key = cm ? "cat:" + cm.label : (c.finding_id || c.score_ref || c.url || "");
        if (!key || seen[key] || items.length >= 8) return;
        seen[key] = true;
        items.push({ c: c, cm: cm });
      });
      if (!items.length) return;
      var row = el("div", "src");
      row.appendChild(el("span", "", chat.getAttribute("data-msg-sources")));
      items.forEach(function (it) {
        var base = "/audits/" + encodeURIComponent(auditId);
        if (it.cm) {
          var a1 = el("a", "", chat.getAttribute("data-msg-analysis") + " › " + it.cm.label);
          a1.href = base + "/analysis?tab=" + encodeURIComponent(it.cm.tab) + "&lang=" + chatLang + "#" + encodeURIComponent(it.c.finding_id);
          row.appendChild(a1);
        } else if (it.c.finding_id) {
          var a2 = el("a", "", it.c.finding_id);
          a2.href = base + "/report?lang=" + chatLang + "#" + encodeURIComponent(it.c.finding_id);
          row.appendChild(a2);
        } else {
          row.appendChild(el("code", "", it.c.score_ref || it.c.url));
        }
      });
      parent.appendChild(row);
    };
    var ask = function (q) {
      if (busy || !q) return;
      busy = true;
      if (empty) { empty.remove(); empty = null; }
      if (suggest) suggest.hidden = true;
      log.appendChild(el("div", "msg-u", q));
      var wrap = el("div", "msg-a");
      var av = el("span", "avatar");
      av.setAttribute("aria-hidden", "true");
      av.textContent = "✓";
      var content = el("div", "content");
      var txt = el("div", "txt", chat.getAttribute("data-msg-thinking"));
      content.appendChild(txt);
      wrap.appendChild(av);
      wrap.appendChild(content);
      log.appendChild(wrap);
      box.value = "";
      scrollDown();
      postJSON("/v1/audits/" + encodeURIComponent(auditId) + "/qa", { question: q })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          if (!res.ok) { txt.textContent = chat.getAttribute("data-msg-error"); return; }
          txt.textContent = res.j.out_of_scope ? chat.getAttribute("data-msg-oos") : res.j.answer;
          addSources(content, res.j.citations);
          content.appendChild(el("div", "note", chat.getAttribute("data-msg-note")));
        })
        .catch(function () { txt.textContent = chat.getAttribute("data-msg-error"); })
        .then(function () { busy = false; scrollDown(); box.focus(); });
    };
    chat.addEventListener("submit", function (e) { e.preventDefault(); ask(box.value.trim()); });
    box.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(box.value.trim()); }
    });
    document.querySelectorAll("#chat-suggest [data-q]").forEach(function (b) {
      b.addEventListener("click", function () { ask(b.getAttribute("data-q")); });
    });
  }

  // ---- settings page: try a saved key with one harmless request
  document.querySelectorAll("[data-test]").forEach(function (b) {
    b.addEventListener("click", function () {
      var row = b.closest(".conn > div");
      var pill = row && row.querySelector(".pill");
      var out = row && row.querySelector(".tout");
      b.disabled = true;
      b.textContent = b.getAttribute("data-msg-testing");
      fetch("/v1/integrations/" + encodeURIComponent(b.getAttribute("data-test")) + "/test?lang=" + encodeURIComponent(b.getAttribute("data-lang") || "tr"), {
        method: "POST",
        headers: { Accept: "application/json" },
      })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (out) { out.hidden = false; out.textContent = j.message || ""; out.classList.toggle("bad", !j.ok); }
          if (row) row.classList.toggle("bad", !j.ok);
          if (pill) {
            pill.className = "pill " + (j.ok ? "pill-good" : "pill-poor");
            pill.textContent = b.getAttribute(j.ok ? "data-msg-ready" : "data-msg-error");
          }
        })
        .catch(function () {
          if (out) { out.hidden = false; out.classList.add("bad"); out.textContent = b.getAttribute("data-msg-error"); }
        })
        .then(function () { b.disabled = false; b.textContent = b.getAttribute("data-msg-label"); });
    });
  });

  // ---- home form: offer the site's own Search Console queries as keywords
  var sugBtn = document.getElementById("suggest-btn");
  var sugUrl = document.getElementById("url");
  var sugKw = document.getElementById("keywords");
  if (sugBtn && sugUrl && sugKw) {
    var sugMsg = document.getElementById("suggest-msg");
    var sugChips = document.getElementById("suggest-chips");
    var addKeyword = function (word) {
      var list = sugKw.value.split(/[,\n;]/).map(function (x) { return x.trim(); }).filter(Boolean);
      if (list.some(function (x) { return x.toLowerCase() === word.toLowerCase(); }) || list.length >= 10) return;
      list.push(word);
      sugKw.value = list.join(", ");
    };
    sugBtn.addEventListener("click", function () {
      sugBtn.disabled = true;
      sugChips.textContent = "";
      var impr = sugChips.getAttribute("data-msg-impr") || "{n}";
      fetch("/ui/suggest-keywords?lang=" + encodeURIComponent(sugBtn.getAttribute("data-lang") || "tr") + "&url=" + encodeURIComponent(sugUrl.value.trim()), { headers: { Accept: "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          sugMsg.hidden = false;
          sugMsg.textContent = j.message || "";
          (j.keywords || []).forEach(function (k) {
            var b = document.createElement("button");
            b.type = "button";
            b.className = "chipbtn";
            b.textContent = k.query;
            b.title = impr.replace("{n}", k.impressions);
            b.addEventListener("click", function () { addKeyword(k.query); });
            sugChips.appendChild(b);
          });
        })
        .catch(function () { sugMsg.hidden = false; sugMsg.textContent = ""; })
        .then(function () { sugBtn.disabled = false; });
    });
  }

  // ---- sortable tables (progressive enhancement; tables stay readable without JS)
  // ---- home form: fill in the keywords and competitors saved for the typed site
  var urlInput = document.getElementById("url");
  var kwInput = document.getElementById("keywords");
  var compInput = document.getElementById("competitors");
  if (urlInput && kwInput && compInput) {
    var lastAsked = "";
    var loadProfile = function () {
      var v = urlInput.value.trim();
      if (!v || v === lastAsked) return;
      lastAsked = v;
      fetch("/ui/profile?url=" + encodeURIComponent(v), { headers: { Accept: "application/json" } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (p) {
          if (!p || (!p.keywords && !p.competitors)) return;
          if (kwInput.value.trim() || compInput.value.trim()) return; // never overwrite typing
          kwInput.value = p.keywords || "";
          compInput.value = p.competitors || "";
          var details = kwInput.closest("details");
          if (details) details.open = true;
          var note = document.getElementById("profile-note");
          if (note) note.hidden = false;
        })
        .catch(function () {});
    };
    urlInput.addEventListener("change", loadProfile);
    urlInput.addEventListener("blur", loadProfile);
  }

  document.querySelectorAll("table[data-sortable]").forEach(function (table) {
    var heads = table.querySelectorAll("thead th[data-sort]");
    heads.forEach(function (th) {
      var idx = Array.prototype.indexOf.call(th.parentNode.children, th);
      th.setAttribute("tabindex", "0");
      th.setAttribute("role", "columnheader button");
      var sort = function () {
        var asc = th.getAttribute("aria-sort") !== "ascending";
        heads.forEach(function (h) { h.removeAttribute("aria-sort"); });
        th.setAttribute("aria-sort", asc ? "ascending" : "descending");
        var num = th.getAttribute("data-sort") === "num";
        var body = table.tBodies[0];
        var rows = Array.prototype.slice.call(body.rows);
        var key = function (row) {
          var cell = row.cells[idx];
          var v = cell.hasAttribute("data-v") ? cell.getAttribute("data-v") : cell.textContent.trim();
          return num ? parseFloat(v) : v.toLowerCase();
        };
        rows.sort(function (a, b) {
          var x = key(a), y = key(b);
          if (num) { x = isNaN(x) ? -1 : x; y = isNaN(y) ? -1 : y; return asc ? x - y : y - x; }
          return asc ? (x < y ? -1 : x > y ? 1 : 0) : (x < y ? 1 : x > y ? -1 : 0);
        });
        rows.forEach(function (r) { body.appendChild(r); });
      };
      th.addEventListener("click", sort);
      th.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); } });
    });
  });
})();
