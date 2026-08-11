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
      // Short delay so dragging the pointer across the nav doesn't flash
      // every panel on the way to the intended one.
      this.openTimer = setTimeout(function () {
        this.closeAll(item);
        item.open = true;
      }.bind(this), 90);
    }

    onLeave(event) {
      var item = event.target.closest ? event.target.closest('[data-menu]') : null;
      if (!item) return;
      clearTimeout(this.openTimer);
      this.closeTimer = setTimeout(function () {
        item.open = false;
      }, 180);
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
