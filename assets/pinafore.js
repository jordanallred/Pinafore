/**
 * Pinafore theme behavior.
 *
 * Everything here is progressive enhancement. Navigation, search, the cart
 * and every quantity control are real links and form submits that work with
 * this file blocked or still loading; these components only make them faster
 * and keep the customer on the page.
 *
 * No framework, no dependencies. Drawers are native <dialog> elements, so the
 * focus trap, Escape handling and inert background come from the platform
 * rather than from code we would have to maintain.
 */
(function () {
  'use strict';

  document.documentElement.classList.add('js');

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  /* ------------------------------------------------------------ helpers */

  function closeDialog(dialog) {
    if (!dialog || !dialog.open) return;
    // Let the slide-out finish before the element leaves the top layer.
    if (reduceMotion.matches) {
      dialog.close();
      return;
    }
    var panel = dialog.querySelector('.drawer__panel');
    if (!panel) {
      dialog.close();
      return;
    }
    dialog.setAttribute('data-closing', '');
    var done = function () {
      dialog.removeAttribute('data-closing');
      dialog.close();
    };
    var t = setTimeout(done, 260);
    panel.addEventListener('transitionend', function handler() {
      clearTimeout(t);
      panel.removeEventListener('transitionend', handler);
      done();
    });
  }

  function syncExpanded(id, open) {
    var triggers = document.querySelectorAll('[data-drawer-open="' + id + '"]');
    for (var i = 0; i < triggers.length; i++) {
      if (triggers[i].hasAttribute('aria-expanded')) {
        triggers[i].setAttribute('aria-expanded', String(open));
      }
    }
  }

  /* ------------------------------------------------------------- drawers */

  document.addEventListener('click', function (event) {
    var opener = event.target.closest('[data-drawer-open]');
    if (opener) {
      var dialog = document.getElementById(opener.getAttribute('data-drawer-open'));
      if (dialog && typeof dialog.showModal === 'function') {
        // Only take over once we know we can actually show the drawer;
        // otherwise the href / default action still stands.
        event.preventDefault();
        dialog.showModal();
        syncExpanded(dialog.id, true);
        dialog.dispatchEvent(new CustomEvent('pinafore:open'));
      }
      return;
    }

    var closer = event.target.closest('[data-drawer-close]');
    if (closer) {
      event.preventDefault();
      closeDialog(closer.closest('dialog'));
    }
  });

  // Clicking the backdrop closes. The panel covers its own area, so any click
  // landing on the <dialog> itself was outside the panel.
  document.addEventListener('mousedown', function (event) {
    if (event.target.tagName === 'DIALOG' && event.target.classList.contains('drawer')) {
      closeDialog(event.target);
    }
  });

  document.addEventListener('close', function (event) {
    if (event.target.tagName === 'DIALOG') syncExpanded(event.target.id, false);
  }, true);

  /* -------------------------------------------------------------- header */

  customElements.define('pinafore-header', class extends HTMLElement {
    connectedCallback() {
      if (!this.hasAttribute('data-sticky')) return;
      // A zero-height sentinel above the header tells us when the page has
      // scrolled past it, without listening to scroll.
      var sentinel = document.createElement('div');
      sentinel.setAttribute('aria-hidden', 'true');
      sentinel.style.cssText = 'position:absolute;top:0;height:1px;width:1px;';
      this.parentNode.insertBefore(sentinel, this);

      var self = this;
      new IntersectionObserver(function (entries) {
        if (entries[0].isIntersecting) self.removeAttribute('data-scrolled');
        else self.setAttribute('data-scrolled', '');
      }).observe(sentinel);
    }
  });

  /* ----------------------------------------------------------- mega menu */

  customElements.define('pinafore-menu', class extends HTMLElement {
    connectedCallback() {
      this.items = Array.prototype.slice.call(this.querySelectorAll('[data-menu]'));
      if (!this.items.length) return;

      this.openTimer = null;
      this.closeTimer = null;

      this.addEventListener('pointerenter', this.onEnter.bind(this), true);
      this.addEventListener('pointerleave', this.onLeave.bind(this), true);
      this.addEventListener('focusout', this.onFocusOut.bind(this));
      this.addEventListener('keydown', this.onKeydown.bind(this));

      // A click outside the nav closes whatever is open.
      document.addEventListener('click', function (event) {
        if (!this.contains(event.target)) this.closeAll();
      }.bind(this));
    }

    onEnter(event) {
      var item = event.target.closest ? event.target.closest('[data-menu]') : null;
      if (!item || !this.contains(item)) return;
      clearTimeout(this.closeTimer);
      clearTimeout(this.openTimer);

      // Already showing: nothing to schedule. Re-running the open path here
      // would let a pointer moving *within* an open panel restart the timer.
      if (item.open) return;

      /*
       * A panel is much wider than the item that opens it, so its outer links
       * sit underneath the *neighbouring* nav items — "Bags" under "Girls"
       * renders directly below "Boys". Reaching them means crossing a sibling,
       * and the sibling's own pointerenter used to steal the panel on the way
       * past. That is why the menu only survived a perfect straight-down path.
       *
       * Geometry rules out the usual "safe triangle": the panel's top edge sits
       * above the nav row's bottom edge, so there is no corridor between them
       * to protect — the crossing happens at the same height as the trigger.
       *
       * So intent is measured by dwell instead. Switching away from an open
       * panel demands a longer pause, and — the part that actually fixes it —
       * the pointer must still be on the item when the timer fires. A pointer
       * merely passing over a sibling has moved on by then and nothing
       * switches. Opening from nothing stays quick.
       */
      var somethingOpen = this.querySelector('[data-menu][open]');
      var delay = somethingOpen ? 260 : 90;

      this.openTimer = setTimeout(
        function () {
          if (typeof item.matches === 'function' && !item.matches(':hover')) return;
          this.closeAll(item);
          item.open = true;
        }.bind(this),
        delay
      );
    }

    onLeave(event) {
      var item = event.target.closest ? event.target.closest('[data-menu]') : null;
      if (!item) return;
      clearTimeout(this.openTimer);
      /*
       * Nav items are separated by a ~24px gap that belongs to neither of
       * them, so a pointer crossing it is briefly over nothing at all. The
       * grace period has to outlast that crossing or the panel closes under a
       * hand that never left the menu. Matched to the switch dwell above so
       * the whole interaction has one tolerance rather than two.
       */
      this.closeTimer = setTimeout(function () {
        item.open = false;
      }, 280);
    }

    onFocusOut(event) {
      if (!this.contains(event.relatedTarget)) this.closeAll();
    }

    onKeydown(event) {
      if (event.key !== 'Escape') return;
      var open = this.querySelector('[data-menu][open]');
      if (!open) return;
      open.open = false;
      var summary = open.querySelector('summary');
      if (summary) summary.focus();
    }

    closeAll(except) {
      for (var i = 0; i < this.items.length; i++) {
        if (this.items[i] !== except) this.items[i].open = false;
      }
    }
  });

  /* ---------------------------------------------------------------- cart */

  customElements.define('pinafore-cart', class extends HTMLElement {
    connectedCallback() {
      this.addEventListener('click', this.onClick.bind(this));
      this.addEventListener('change', this.onNoteChange.bind(this));
    }

    onClick(event) {
      var link = event.target.closest('[data-qty-change]');
      if (!link) return;
      event.preventDefault();

      var url = new URL(link.href, window.location.origin);
      var line = url.searchParams.get('line');
      var quantity = url.searchParams.get('quantity');
      if (line === null || quantity === null) return;

      this.setBusy(true);
      fetch(window.Shopify.routes.root + 'cart/change.js', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          line: Number(line),
          quantity: Number(quantity),
          sections: 'cart-drawer,header',
          sections_url: window.location.pathname
        })
      })
        .then(function (r) {
          if (!r.ok) throw new Error('cart');
          return r.json();
        })
        .then(this.render.bind(this))
        .catch(function () {
          // Fall back to the plain navigation the link already described,
          // so a failed fetch still updates the customer's cart.
          window.location.href = link.href;
        });
    }

    onNoteChange(event) {
      if (!event.target.matches('[name="note"]')) return;
      fetch(window.Shopify.routes.root + 'cart/update.js', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: event.target.value })
      });
    }

    setBusy(busy) {
      this.toggleAttribute('aria-busy', busy);
      this.style.opacity = busy ? '0.6' : '';
    }

    render(data) {
      var sections = data.sections || {};
      var parser = new DOMParser();

      if (sections['cart-drawer']) {
        var doc = parser.parseFromString(sections['cart-drawer'], 'text/html');
        var fresh = doc.querySelector('pinafore-cart');
        // Swap the panel, not the <dialog>, so the drawer stays open and
        // keeps its place in the top layer.
        if (fresh) this.replaceWith(fresh);
      }

      if (sections.header) {
        var hdoc = parser.parseFromString(sections.header, 'text/html');
        var freshCount = hdoc.querySelector('[data-cart-count]');
        var liveCount = document.querySelector('[data-cart-count]');
        if (freshCount && liveCount) liveCount.replaceWith(freshCount);
      }
    }
  });

  /* ------------------------------------------------------------- gallery */

  customElements.define('pinafore-gallery', class extends HTMLElement {
    connectedCallback() {
      this.track = this.querySelector('[data-gallery-track]');
      if (!this.track) return;

      this.slides = Array.prototype.slice.call(this.querySelectorAll('[data-media-id]'));
      this.dots = Array.prototype.slice.call(this.querySelectorAll('[data-dot]'));
      this.thumbs = Array.prototype.slice.call(this.querySelectorAll('[data-thumb]'));

      // Which slide is showing is derived from scroll position rather than
      // tracked in state, so a swipe, a thumbnail click and a deep link all
      // converge on the same answer.
      if (this.slides.length > 1) {
        var observer = new IntersectionObserver(this.onIntersect.bind(this), {
          root: this.track,
          threshold: 0.6
        });
        this.slides.forEach(function (slide) { observer.observe(slide); });
      }

      this.addEventListener('click', this.onThumbClick.bind(this));
    }

    onIntersect(entries) {
      for (var i = 0; i < entries.length; i++) {
        if (!entries[i].isIntersecting) continue;
        this.setActive(this.slides.indexOf(entries[i].target));
      }
    }

    onThumbClick(event) {
      var thumb = event.target.closest('[data-thumb]');
      if (!thumb) return;
      event.preventDefault();
      this.showMedia(thumb.getAttribute('data-media-id'));
    }

    setActive(index) {
      if (index < 0) return;
      this.dots.forEach(function (dot, i) { dot.classList.toggle('is-active', i === index); });
      this.thumbs.forEach(function (t, i) { t.classList.toggle('is-active', i === index); });
    }

    // Called by <pinafore-variants> when the chosen variant has its own image.
    showMedia(mediaId) {
      // Must select the slide specifically: thumbnails carry the same
      // data-media-id, and scrolling to a thumbnail moves nothing.
      var slide = this.querySelector('.gallery__slide[data-media-id="' + mediaId + '"]');
      if (!slide || !this.track) return;

      // scrollIntoView walks up to the nearest scroll container and, with
      // mandatory scroll-snap, was being corrected straight back to the
      // previous snap point. Offsets are measured against the track itself
      // rather than offsetParent, which is the section, not the scroller.
      var left = this.track.scrollLeft
        + slide.getBoundingClientRect().left
        - this.track.getBoundingClientRect().left;

      // 'auto' is verified to work against a mandatory-snap container;
      // smooth is requested only when the platform will honour it.
      this.track.scrollTo({ left: left, behavior: 'auto' });
    }
  });

  /* ------------------------------------------------------------ variants */

  customElements.define('pinafore-variants', class extends HTMLElement {
    connectedCallback() {
      var data = this.querySelector('[data-variant-data]');
      if (!data) return;

      try {
        this.variants = JSON.parse(data.textContent);
      } catch (e) {
        return;
      }

      this.addEventListener('change', this.onChange.bind(this));
    }

    get selectedOptions() {
      return Array.prototype.map.call(
        this.querySelectorAll('.variants__input:checked'),
        function (input) { return input.value; }
      );
    }

    onChange() {
      var chosen = this.selectedOptions;
      var match = null;

      for (var i = 0; i < this.variants.length; i++) {
        var v = this.variants[i];
        var hit = true;
        for (var j = 0; j < chosen.length; j++) {
          if (v.options[j] !== chosen[j]) { hit = false; break; }
        }
        if (hit) { match = v; break; }
      }

      this.updateLabels(chosen);
      if (!match) {
        this.markUnavailable();
        return;
      }

      this.updateUrl(match);
      this.updateMedia(match);
      // Price, availability, installments and pickup all depend on the
      // variant, so the section is re-rendered rather than patched field by
      // field — one source of truth, and money stays formatted by Liquid.
      this.refreshSection(match);
    }

    updateLabels(chosen) {
      var values = this.querySelectorAll('[data-option-value]');
      for (var i = 0; i < values.length; i++) {
        if (chosen[i] !== undefined) values[i].textContent = chosen[i];
      }
    }

    markUnavailable() {
      var button = document.querySelector('[data-atc]');
      var label = document.querySelector('[data-atc-text]');
      if (button) button.disabled = true;
      if (label) label.textContent = label.getAttribute('data-unavailable-text') || label.textContent;
    }

    updateUrl(variant) {
      if (!window.history.replaceState) return;
      var url = new URL(window.location.href);
      url.searchParams.set('variant', variant.id);
      window.history.replaceState({}, '', url.toString());
    }

    updateMedia(variant) {
      if (!variant.featured_media) return;
      var gallery = document.querySelector('pinafore-gallery');
      if (gallery && gallery.showMedia) gallery.showMedia(variant.featured_media.id);
    }

    refreshSection(variant) {
      var section = this.getAttribute('data-section');
      var url = this.getAttribute('data-url');
      if (!section || !url) return;

      fetch(url + '?variant=' + variant.id + '&section_id=' + section)
        .then(function (r) { return r.text(); })
        .then(function (html) {
          var doc = new DOMParser().parseFromString(html, 'text/html');

          // Swap only the parts that actually depend on the variant. The
          // picker itself is left alone so focus stays where the customer
          // put it.
          ['[data-price]', '[data-pickup]'].forEach(function (sel) {
            var fresh = doc.querySelector(sel);
            var live = document.querySelector(sel);
            if (fresh && live) live.innerHTML = fresh.innerHTML;
          });

          var freshButton = doc.querySelector('[data-atc]');
          var liveButton = document.querySelector('[data-atc]');
          if (freshButton && liveButton) {
            liveButton.disabled = freshButton.disabled;
            liveButton.innerHTML = freshButton.innerHTML;
          }

          var idInput = document.querySelector('[data-variant-id]');
          if (idInput) idInput.value = variant.id;
        })
        .catch(function () { /* the form still carries a valid variant id */ });
    }
  });

  /* ----------------------------------------------------------- sticky ATC */

  customElements.define('pinafore-sticky-atc', class extends HTMLElement {
    connectedCallback() {
      var target = document.querySelector('[data-atc]');
      if (!target) return;

      var self = this;
      // Shown only once the real button has left the viewport, so the bar
      // never covers the control it is standing in for.
      new IntersectionObserver(function (entries) {
        self.hidden = entries[0].isIntersecting;
      }, { rootMargin: '0px 0px -80px 0px' }).observe(target);
    }
  });

  /* ------------------------------------------------- card variant preview */

  /*
   * Hovering a colour thumbnail previews that colour in the card's main
   * image. The generic second-image-on-hover swap is disabled for products
   * with a colourway axis, because there the second image is a different
   * colour rather than another angle — so merely passing the cursor over a
   * card changed which product it appeared to be.
   */
  document.addEventListener('pointerover', function (event) {
    var thumb = event.target.closest ? event.target.closest('[data-variant-image]') : null;
    if (!thumb) return;

    var card = thumb.closest('.card');
    var main = card && card.querySelector('.card__image--main');
    if (!main) return;

    if (!main.dataset.restoreSrc) {
      main.dataset.restoreSrc = main.getAttribute('src') || '';
      main.dataset.restoreSrcset = main.getAttribute('srcset') || '';
    }
    main.removeAttribute('srcset');
    main.src = thumb.getAttribute('data-variant-image');
  });

  document.addEventListener('pointerout', function (event) {
    var card = event.target.closest ? event.target.closest('.card') : null;
    if (!card || card.contains(event.relatedTarget)) return;

    var main = card.querySelector('.card__image--main');
    if (!main || !main.dataset.restoreSrc) return;
    main.src = main.dataset.restoreSrc;
    if (main.dataset.restoreSrcset) main.setAttribute('srcset', main.dataset.restoreSrcset);
  });

  /* -------------------------------------------------------------- facets */

  customElements.define('pinafore-facets', class extends HTMLElement {
    connectedCallback() {
      this.form = this.querySelector('[data-facet-form]');
      if (!this.form) return;

      this.section = this.getAttribute('data-section');
      this.form.addEventListener('submit', this.onSubmit.bind(this));
    }

    onSubmit(event) {
      event.preventDefault();

      // FormData drops unchecked boxes and empty inputs for us, which is
      // exactly the query string Shopify's filters expect.
      var params = new URLSearchParams(new FormData(this.form));
      var url = window.location.pathname + '?' + params.toString();

      this.apply(url);
      closeDialog(this.form.closest('dialog'));
    }

    apply(url) {
      var results = document.querySelector('[data-results]');
      if (results) results.setAttribute('aria-busy', 'true');

      fetch(url + '&section_id=' + this.section)
        .then(function (r) { return r.text(); })
        .then(function (html) {
          var doc = new DOMParser().parseFromString(html, 'text/html');
          var fresh = doc.querySelector('[data-results]');
          if (fresh && results) results.replaceWith(fresh);

          // Keep the URL honest so the view is shareable and the back
          // button returns to the previous filter state.
          window.history.pushState({ facets: true }, '', url);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        })
        .catch(function () { window.location.href = url; });
    }
  });

  // Back/forward across filtered views.
  window.addEventListener('popstate', function (event) {
    if (event.state && event.state.facets) window.location.reload();
  });

  /* ----------------------------------------------------------- quick add */

  document.addEventListener('submit', function (event) {
    var form = event.target.closest('[data-quick-add]');
    if (!form) return;
    event.preventDefault();

    var button = form.querySelector('button');
    if (button) button.disabled = true;

    fetch(window.Shopify.routes.root + 'cart/add.js', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        items: [{ id: Number(form.querySelector('[name="id"]').value), quantity: 1 }],
        sections: 'cart-drawer,header',
        sections_url: window.location.pathname
      })
    })
      .then(function (r) {
        if (!r.ok) throw new Error('add');
        return r.json();
      })
      .then(function (data) {
        var cart = document.querySelector('pinafore-cart');
        if (cart) cart.render(data);

        // Opening the drawer is the confirmation — no toast needed, and the
        // customer can see exactly what landed in the cart.
        var drawer = document.getElementById('CartDrawer');
        if (drawer && drawer.showModal) drawer.showModal();
      })
      .catch(function () { form.submit(); })
      .finally(function () {
        if (button) button.disabled = false;
      });
  });

  /* -------------------------------------------------------------- search */

  customElements.define('pinafore-search', class extends HTMLElement {
    connectedCallback() {
      this.input = this.querySelector('[data-search-input]');
      this.results = this.querySelector('[data-search-results]');
      if (!this.input || !this.results || !this.hasAttribute('data-predictive')) return;

      this.timer = null;
      this.controller = null;
      this.cache = {};

      this.input.addEventListener('input', this.onInput.bind(this));

      // Focus the field when the sheet opens, but not on touch — the on-screen
      // keyboard covering the results is worse than one extra tap.
      var dialog = this.closest('dialog');
      if (dialog) {
        dialog.addEventListener('pinafore:open', function () {
          if (window.matchMedia('(hover: hover)').matches) this.input.focus();
        }.bind(this));
      }
    }

    onInput() {
      var term = this.input.value.trim();
      clearTimeout(this.timer);

      if (term.length < 2) {
        this.results.innerHTML = '';
        this.input.setAttribute('aria-expanded', 'false');
        return;
      }

      this.timer = setTimeout(this.search.bind(this, term), 200);
    }

    search(term) {
      if (this.cache[term]) {
        this.show(this.cache[term]);
        return;
      }

      // Abandon an in-flight request whose answer is already stale.
      if (this.controller) this.controller.abort();
      this.controller = new AbortController();

      var params = new URLSearchParams({
        q: term,
        'resources[type]': 'product,collection,query',
        'resources[limit]': '6',
        section_id: 'predictive-search'
      });

      fetch(window.Shopify.routes.root + 'search/suggest?' + params, {
        signal: this.controller.signal
      })
        .then(function (r) { return r.text(); })
        .then(function (html) {
          this.cache[term] = html;
          this.show(html);
        }.bind(this))
        .catch(function () { /* aborted or offline; the form still submits */ });
    }

    show(html) {
      this.results.innerHTML = html;
      this.input.setAttribute('aria-expanded', 'true');
    }
  });
})();
