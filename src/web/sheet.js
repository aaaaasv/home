(() => {
  "use strict";
  const one = (selector, root = document) => root.querySelector(selector);
  const all = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  /* ── mounting a plate ──────────────────────────────────────────────────
     the strip stops being a filmstrip and becomes the drawer of plates a
     curator picks from: tapping one mounts it on the sheet above. */
  const mounted = one("#mounted");
  const caption = one("#mount-caption");
  const plates = all(".strip figure[data-photo]");
  if (mounted && plates.length > 1) {
    const mount = (plate) => {
      mounted.src = plate.dataset.photo;
      if (caption) caption.textContent = plate.dataset.caption;
      plates.forEach((other) => other.classList.toggle("is-mounted", other === plate));
      mounted.classList.remove("swap");
      void mounted.offsetWidth;
      mounted.classList.add("swap");
    };
    plates.forEach((plate) => {
      plate.setAttribute("role", "button");
      plate.tabIndex = 0;
      plate.addEventListener("click", () => mount(plate));
      plate.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          mount(plate);
        }
      });
    });
  }

  /* ── the loupe ─────────────────────────────────────────────────────────
     a toggle rather than plain hover, because on a phone a magnifier that
     follows every touch would eat the page scroll. */
  const frame = one(".mount");
  const loupeButton = one("#loupe");
  if (frame && mounted && loupeButton) {
    const lens = document.createElement("i");
    lens.className = "loupe-glass";
    frame.appendChild(lens);
    const ZOOM = 2.7;
    let active = false;

    const draw = (event) => {
      if (!active) return;
      const box = mounted.getBoundingClientRect();
      const x = event.clientX - box.left;
      const y = event.clientY - box.top;
      if (x < 0 || y < 0 || x > box.width || y > box.height) {
        lens.classList.remove("on");
        return;
      }
      lens.classList.add("on");
      lens.style.backgroundImage = `url("${mounted.currentSrc || mounted.src}")`;
      lens.style.backgroundSize = `${box.width * ZOOM}px ${box.height * ZOOM}px`;
      lens.style.backgroundPosition = `${lens.offsetWidth / 2 - x * ZOOM}px ${lens.offsetHeight / 2 - y * ZOOM}px`;
      lens.style.transform = `translate(${x - lens.offsetWidth / 2}px, ${y - lens.offsetHeight / 2}px)`;
    };

    loupeButton.addEventListener("click", () => {
      active = !active;
      loupeButton.classList.toggle("on", active);
      loupeButton.setAttribute("aria-pressed", String(active));
      frame.classList.toggle("magnifying", active);
      if (!active) lens.classList.remove("on");
    });
    frame.addEventListener("pointermove", draw);
    frame.addEventListener("pointerdown", draw);
    frame.addEventListener("pointerleave", () => lens.classList.remove("on"));
  }

  /* ── reading the climate plate ─────────────────────────────────────────
     touch-action stays pan-y in the stylesheet, so a vertical swipe still
     scrolls the page and only sideways movement scrubs the chart. */
  const plate = one("#climate");
  if (plate) {
    const readout = one("#climate-readout");
    const rule = one("#climate-rule");
    const points = JSON.parse(plate.dataset.points || "[]");
    if (points.length && readout && rule) {
      const scrub = (event) => {
        const box = plate.getBoundingClientRect();
        const ratio = Math.min(Math.max((event.clientX - box.left) / box.width, 0), 1);
        const point = points[Math.round(ratio * (points.length - 1))];
        if (!point) return;
        rule.style.left = `${ratio * 100}%`;
        plate.classList.add("reading");
        readout.textContent = `${point[0]}:00 · ${point[1].toFixed(1)} °C · ${point[2].toFixed(0)} %`;
      };
      plate.addEventListener("pointermove", scrub);
      plate.addEventListener("pointerdown", scrub);
      plate.addEventListener("pointerleave", () => plate.classList.remove("reading"));
    }
  }

  /* ── keep the open folder's tab in view ───────────────────────────────
     with five tabs on a phone the row scrolls, and the one you are reading
     is the one that should be visible when the page opens. */
  const here = one(".tabs .tab.here");
  if (here) {
    const row = here.parentElement;
    // scrollIntoView would scroll every scrollable ancestor, the document included; only the row should move
    if (row.scrollWidth > row.clientWidth) {
      row.scrollLeft = here.offsetLeft - (row.clientWidth - here.offsetWidth) / 2;
    }
  }

  /* ── per-row care notes ────────────────────────────────────────────────
     the note ships visible so a page with no script still shows it; the
     button only takes over once there is something to toggle with. */
  all(".regimen .info").forEach((button) => {
    const note = document.getElementById(button.getAttribute("aria-controls"));
    if (!note) return;
    note.hidden = true;
    button.setAttribute("aria-expanded", "false");
    button.addEventListener("click", () => {
      const open = note.hidden;
      note.hidden = !open;
      button.setAttribute("aria-expanded", String(open));
    });
  });

  /* ── the growth wipe ───────────────────────────────────────────────────
     a range input rather than a custom drag: it is already touch-sized,
     keyboard-reachable, and sits at 50% with no script at all. */
  const wipe = one("#wipe");
  if (wipe) {
    const compare = wipe.closest(".compare");
    const apply = () => compare.style.setProperty("--wipe", `${wipe.value}%`);
    wipe.addEventListener("input", apply);
    apply();
  }
})();
