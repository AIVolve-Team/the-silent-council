"use strict";
// The visual checks: this script is in the page only when the view comes from a complex PDF. The texts
// come ready in both languages from review.view (#visual); here they only become nodes, as text, never as HTML.
(() => {
  const texts = JSON.parse(document.getElementById("visual").textContent);
  const section = () => {
    const x = texts[language] ?? texts.it;
    return el("section", { class: "visual-checks", "aria-label": x.title },
      el("h2", {}, x.title),
      el("p", {}, x.route),
      x.why.length ? el("div", {}, el("p", { class: "label" }, x.why_title), el("ul", {}, x.why.map(w => el("li", {}, w)))) : null,
      el("p", { class: "muted" }, x.hidden),
      x.checks.length ? el("div", {}, el("p", { class: "label" }, x.checks_title),
        el("ol", { class: "checks" }, x.checks.map(c => el("li", {},
          el("p", { class: "question" }, c.question),
          el("p", { class: "answer" }, c.answer),
          c.unknown ? el("p", { class: "muted" }, c.unknown) : null,
          c.objects.length ? el("ul", { class: "objects" }, c.objects.map(o => el("li", {}, o))) : null)))) : null);
  };
  // After the recommendation and the objections, before the clauses: the form of the document comes before its words.
  const add = () => {
    const page = document.getElementById("page");
    const before = page.querySelector(":scope > .group, :scope > .actions");
    if (before) page.insertBefore(section(), before);
  };
  // The page redraws itself when the reader changes language: the section is redrawn with it.
  const base = show;
  show = (view) => { base(view); add(); };
  add();
})();
