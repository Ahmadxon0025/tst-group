/* CORE: reusable — Todoist-style behaviour: click a task → edit window; drag a card to another day → new date.
   Everything still works without this file (links open the task page). */
(function () {
  var dlg = document.getElementById("task"), body = document.getElementById("task-body");
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  function toast(text) {
    var t = document.getElementById("toast"), m = document.getElementById("toast-msg");
    if (!t) return;
    m.textContent = window.toCyrillic && document.documentElement.dataset.script === "cyrl" ? window.toCyrillic(text) : text;
    t.hidden = false; clearTimeout(toast._t); toast._t = setTimeout(function () { t.hidden = true; }, 3500);
  }
  function cyr(el) {
    if (document.documentElement.dataset.script !== "cyrl" || !window.toCyrillic) return;
    var w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
    var n; while ((n = w.nextNode())) {
      var p = n.parentNode;
      if (p && !p.closest("textarea,input,select,script,.keep") && /[A-Za-z]/.test(n.nodeValue)) n.nodeValue = window.toCyrillic(n.nodeValue);
    }
  }

  // ---- one-line quick add bar: live preview of what was understood -----------------------
  var qb = document.getElementById("qbar"), qc = document.getElementById("qbar-chips");
  if (qb && qc) {
    var qt;
    // paste several lines at once → one task per line (after a confirm)
    qb.addEventListener("paste", function (e) {
      var text = (e.clipboardData || window.clipboardData).getData("text");
      var lines = text.split(/\r?\n/).map(function (l) { return l.trim(); }).filter(Boolean);
      if (lines.length < 2) return;
      e.preventDefault();
      var msg = lines.length + " ta vazifa qo'shilsinmi? (har qator — bitta vazifa)";
      if (window.toCyrillic && document.documentElement.dataset.script === "cyrl") msg = window.toCyrillic(msg);
      if (!confirm(msg)) return;
      var fd = new FormData(); fd.append("lines", lines.join("\n"));
      fetch("/vazifa/kop/", {method: "POST", body: fd, credentials: "same-origin", headers: {"X-CSRFToken": csrf}})
        .then(function () { location.reload(); })
        .catch(function () { toast("Qo'shilmadi. Qayta urinib ko'ring."); });
    });
    function chip(t, cls) { return '<span class="qa-chip ' + (cls || '') + '">' + t.replace(/</g, "&lt;") + "</span>"; }
    qb.addEventListener("input", function () {
      clearTimeout(qt);
      if (!qb.value.trim()) { qc.innerHTML = ""; return; }
      qt = setTimeout(function () {
        fetch("/vazifa/tahlil/?q=" + encodeURIComponent(qb.value), {credentials: "same-origin"})
          .then(function (r) { return r.json(); }).then(function (j) {
            var h = chip(j.due_label ? "📅 " + j.due_label : "📥 Rejasiz");
            h += chip("👤 " + (j.who_name || "Men"));
            if (j.company) h += chip("#" + j.company_label, "keep");
            if (j.category) h += chip("/" + j.category_label);
            if (j.important) h += chip("❗ Muhim", "imp");
            if (j.private) h += chip("🔒 Maxfiy");
            if (j.repeat) h += chip("🔁 " + j.repeat_label);
            qc.innerHTML = h; cyr(qc);
          }).catch(function () {});
      }, 200);
    });
  }

  // ---- press and drag the board sideways; ‹ › glide a week ------------------------------------
  var board = document.querySelector("main.board");
  if (board && window.matchMedia("(min-width: 761px)").matches) {
    var down = false, startX = 0, startLeft = 0, lastX = 0, lastT = 0, vel = 0, raf = 0, moved = false;
    function blocked(t) { return t.closest("a,button,input,textarea,select,label,.card,form,dialog"); }
    board.addEventListener("mousedown", function (e) {
      if (e.button !== 0 || blocked(e.target)) return;
      down = true; moved = false; startX = lastX = e.clientX; startLeft = board.scrollLeft; lastT = performance.now();
      vel = 0; cancelAnimationFrame(raf); board.classList.add("panning"); e.preventDefault();
    });
    window.addEventListener("mousemove", function (e) {
      if (!down) return;
      var now = performance.now(), dx = e.clientX - startX;
      if (Math.abs(dx) > 3) moved = true;
      board.scrollLeft = startLeft - dx;
      vel = (e.clientX - lastX) / Math.max(1, now - lastT); lastX = e.clientX; lastT = now;
    });
    window.addEventListener("mouseup", function () {
      if (!down) return;
      down = false; board.classList.remove("panning");
      var v = vel * 16;                                   // px per frame, eases out
      (function glide() {
        if (Math.abs(v) < 0.5) return;
        board.scrollLeft -= v; v *= 0.92; raf = requestAnimationFrame(glide);
      })();
    });
    function dayWidth() { var c = board.querySelector(".col[data-date]:not(.inbox)"); return c ? c.getBoundingClientRect().width + 22 : 300; }
    function glideBy(px) { board.scrollBy({left: px, behavior: "smooth"}); }
    var prev = document.querySelector(".js-prev"), next = document.querySelector(".js-next"), tod = document.querySelector(".js-today");
    if (next) next.addEventListener("click", function (e) {
      if (board.scrollLeft + board.clientWidth < board.scrollWidth - 4) { e.preventDefault(); glideBy(dayWidth() * 7); }
    });
    if (prev) prev.addEventListener("click", function (e) {
      if (board.scrollLeft > 4) { e.preventDefault(); glideBy(-dayWidth() * 7); }
    });
    if (tod) tod.addEventListener("click", function (e) {
      var t = board.querySelector(".col.today");
      if (t) { e.preventDefault(); board.scrollTo({left: 0, behavior: "smooth"}); }
    });
  }

  // ---- open the edit window -------------------------------------------------------------
  document.addEventListener("click", function (e) {
    var a = e.target.closest("a.js-open");
    if (!a || !dlg || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    var here = location.pathname + location.search;
    fetch("/vazifa/" + a.dataset.id + "/?partial=1&next=" + encodeURIComponent(here), {credentials: "same-origin"})
      .then(function (r) { if (!r.ok) throw r; return r.text(); })
      .then(function (html) { body.innerHTML = html; cyr(body); dlg.showModal(); })
      .catch(function () { location.href = a.href; });
  });
  if (dlg) {
    dlg.addEventListener("click", function (e) {
      if (e.target === dlg || e.target.closest(".js-close")) dlg.close();
      var b = e.target.closest("[data-setdate]");
      if (b && b.dataset.setdate === "none") { dlg.querySelector('input[name="due"]').value = ""; b = null; }
      if (b) {
        var base = dlg.querySelector(".tp").dataset.today, d = new Date(base + "T12:00:00");
        d.setDate(d.getDate() + parseInt(b.dataset.setdate, 10));
        dlg.querySelector('input[name="due"]').value = d.toISOString().slice(0, 10);
      }
    });
  }

  // ---- drag a card to another day ----------------------------------------------------------
  var dragged = null;
  document.addEventListener("dragstart", function (e) {
    var c = e.target.closest && e.target.closest(".card.movable");
    if (!c) return;
    dragged = c; c.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", c.dataset.id);
  });
  document.addEventListener("dragend", function () {
    if (dragged) dragged.classList.remove("dragging");
    dragged = null;
    document.querySelectorAll(".col.drop").forEach(function (c) { c.classList.remove("drop"); });
  });
  function colAt(e) {
    // the column under the pointer, or — anywhere on the board, even below the cards — the one at its x position
    var col = e.target.closest && e.target.closest(".col[data-date]");
    if (col) return col;
    if (!(e.target.closest && e.target.closest(".board"))) return null;
    var cols = document.querySelectorAll(".col[data-date]");
    for (var i = 0; i < cols.length; i++) {
      var r = cols[i].getBoundingClientRect();
      if (e.clientX >= r.left - 11 && e.clientX <= r.right + 11) return cols[i];
    }
    return null;
  }
  document.addEventListener("dragover", function (e) {
    var col = colAt(e);
    if (!dragged || !col) return;
    e.preventDefault(); e.dataTransfer.dropEffect = "move";
    document.querySelectorAll(".col.drop").forEach(function (c) { if (c !== col) c.classList.remove("drop"); });
    col.classList.add("drop");
  });
  function recount() {
    document.querySelectorAll(".col").forEach(function (col) {
      var n = col.querySelectorAll(".card:not(.done)").length, c = col.querySelector(".js-count, .ch .c");
      if (c) c.textContent = n;
    });
  }
  document.addEventListener("drop", function (e) {
    var col = colAt(e);
    if (!dragged || !col) return;
    e.preventDefault();
    var card = dragged, from = card.parentNode, next = card.nextSibling;
    var anchor = col.querySelector(".donelink, .addline, .none");
    col.insertBefore(card, anchor);           // move now; put back if the server says no
    card.classList.remove("is-late");
    var late = card.querySelector(".lateby"); if (late) late.remove();
    recount();
    var fd = new FormData(); fd.append("due", col.dataset.date);
    fetch("/vazifa/" + card.dataset.id + "/kunga/", {method: "POST", body: fd, credentials: "same-origin",
      headers: {"X-CSRFToken": csrf}})
      .then(function (r) { return r.json().then(function (j) { if (!r.ok || !j.ok) throw j; }); })
      .catch(function (j) {
        from.insertBefore(card, next); recount();
        toast((j && j.error) || "Saqlanmadi. Sahifani yangilang.");
      });
  });
})();
