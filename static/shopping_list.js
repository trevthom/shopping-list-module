/* Shopping List: collapse, drag to reorder, cross off, and undo. */
(() => {
  'use strict';

  const root = document.querySelector('[data-shopping-list]');
  if (!root) return;

  const base = root.dataset.base || '/shopping-list';
  const storesEl = root.querySelector('[data-stores]');
  const undoBar = document.getElementById('sl-undo');
  const undoName = document.getElementById('sl-undo-name');
  const undoButton = document.getElementById('sl-undo-button');

  const CHECK_SVG =
    '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" ' +
    'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="m5 12.5 4.2 4.2L19 6.8"/></svg>';

  /** Checked-off items waiting for undo; newest last. */
  const undoStack = [];

  function storeCards() {
    return storesEl ? Array.from(storesEl.querySelectorAll('.sl-store')) : [];
  }

  async function postJSON(url, body) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}),
      });
      let data = null;
      try {
        data = await response.json();
      } catch (error) {
        data = null;
      }
      return { ok: response.ok && !(data && data.ok === false), data };
    } catch (error) {
      return { ok: false, data: null };
    }
  }

  function refreshStore(card) {
    if (!card) return;
    const rows = card.querySelectorAll('.sl-item-row');
    const count = card.querySelector('[data-count]');
    if (count) count.textContent = String(rows.length);
    const empty = card.querySelector('[data-empty]');
    if (empty) empty.hidden = rows.length > 0;
  }

  function showNotice(card, message) {
    const notice = card ? card.querySelector('[data-notice]') : null;
    if (!notice) return;
    notice.textContent = message;
    notice.hidden = !message;
  }

  function showUndo() {
    if (!undoBar || !undoName) return;
    const entry = undoStack[undoStack.length - 1];
    if (!entry) {
      undoBar.hidden = true;
      return;
    }
    undoName.textContent = entry.name;
    undoBar.hidden = false;
  }

  function setCollapsed(card, collapsed, persist) {
    if (!card) return;
    card.classList.toggle('is-collapsed', collapsed);
    const toggle = card.querySelector('[data-toggle]');
    if (toggle) toggle.setAttribute('aria-expanded', String(!collapsed));
    if (persist) {
      postJSON(base + '/stores/' + card.dataset.storeId + '/collapsed', { collapsed });
    }
  }

  function updateLabels(card, name) {
    const set = (selector, value) => {
      const element = card.querySelector(selector);
      if (element) element.setAttribute('aria-label', value);
    };
    set('[data-drag-handle]', 'Reorder ' + name + '. Drag, or use the arrow keys.');
    set('[data-edit]', 'Rename ' + name);
    set('[data-delete-store] button', 'Delete ' + name);
    const addLabel = card.querySelector('.sl-add label');
    if (addLabel) addLabel.textContent = 'Add an item to ' + name;
  }

  function buildRow(item) {
    const row = document.createElement('li');
    row.className = 'sl-item-row';

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'sl-item';
    button.dataset.itemId = String(item.id);

    const circle = document.createElement('span');
    circle.className = 'sl-item__circle';
    circle.setAttribute('aria-hidden', 'true');
    circle.innerHTML = CHECK_SVG;

    const label = document.createElement('span');
    label.className = 'sl-item__label';
    label.textContent = item.name;

    button.append(circle, label);
    button.addEventListener('click', () => markOff(button));
    row.appendChild(button);
    return row;
  }

  function markOff(button) {
    if (!button || button.dataset.busy === '1') return;
    const row = button.closest('.sl-item-row');
    const list = row ? row.parentElement : null;
    const card = button.closest('.sl-store');
    if (!row || !list || !card) return;

    const label = button.querySelector('.sl-item__label');
    const name = label ? label.textContent : 'Item';
    const itemId = button.dataset.itemId;
    button.dataset.busy = '1';
    showNotice(card, '');

    postJSON(base + '/items/' + itemId + '/check').then((result) => {
      if (!result.ok) {
        delete button.dataset.busy;
        showNotice(
          card,
          (result.data && result.data.error) || 'Could not mark that off. Try again.'
        );
        return;
      }

      const entry = {
        id: itemId,
        name,
        row,
        list,
        card,
        index: Array.from(list.children).indexOf(row),
        timers: [],
        busy: false,
      };

      row.classList.add('is-checking');
      entry.timers.push(
        window.setTimeout(() => {
          row.classList.add('is-removing');
          entry.timers.push(
            window.setTimeout(() => {
              if (row.parentElement === list) row.remove();
              refreshStore(card);
            }, 280)
          );
        }, 320)
      );

      undoStack.push(entry);
      showUndo();
    });
  }

  function undoLast() {
    const entry = undoStack[undoStack.length - 1];
    if (!entry || entry.busy) return;
    entry.busy = true;

    postJSON(base + '/items/' + entry.id + '/undo').then((result) => {
      if (!result.ok) {
        entry.busy = false;
        showUndo();
        return;
      }

      entry.timers.forEach((timer) => window.clearTimeout(timer));
      entry.timers = [];
      undoStack.pop();

      entry.row.classList.remove('is-checking', 'is-removing');
      const button = entry.row.querySelector('.sl-item');
      if (button) delete button.dataset.busy;
      if (entry.row.parentElement !== entry.list) {
        const reference = entry.list.children[entry.index] || null;
        if (reference) entry.list.insertBefore(entry.row, reference);
        else entry.list.appendChild(entry.row);
      }

      setCollapsed(entry.card, false, true);
      refreshStore(entry.card);
      showUndo();
    });
  }

  function saveOrder() {
    const ids = storeCards().map((card) => Number(card.dataset.storeId));
    postJSON(base + '/stores/order', { ids });
  }

  function setupDrag(card) {
    const handle = card.querySelector('[data-drag-handle]');
    if (!handle) return;

    let drag = null;

    handle.addEventListener('pointerdown', (event) => {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      event.preventDefault();
      drag = { id: event.pointerId, startY: event.clientY, moved: false };
      card.classList.add('is-dragging');
      try {
        handle.setPointerCapture(event.pointerId);
      } catch (error) {
        /* Pointer capture is a nicety; the drag still works without it. */
      }
    });

    handle.addEventListener('pointermove', (event) => {
      if (!drag || event.pointerId !== drag.id) return;
      if (!drag.moved) {
        if (Math.abs(event.clientY - drag.startY) < 4) return;
        drag.moved = true;
        card.classList.add('is-lifted');
      }

      const y = event.clientY;
      let reference = null;
      for (const other of storeCards()) {
        if (other === card) continue;
        const rect = other.getBoundingClientRect();
        if (y < rect.top + rect.height / 2) {
          reference = other;
          break;
        }
      }
      if (reference) storesEl.insertBefore(card, reference);
      else storesEl.appendChild(card);
    });

    const finish = (event) => {
      if (!drag || event.pointerId !== drag.id) return;
      const moved = drag.moved;
      drag = null;
      card.classList.remove('is-dragging', 'is-lifted');
      try {
        if (handle.hasPointerCapture(event.pointerId)) {
          handle.releasePointerCapture(event.pointerId);
        }
      } catch (error) {
        /* ignore */
      }
      if (moved) saveOrder();
    };

    handle.addEventListener('pointerup', finish);
    handle.addEventListener('pointercancel', finish);

    handle.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
      event.preventDefault();
      const cards = storeCards();
      const index = cards.indexOf(card);
      const target = event.key === 'ArrowUp' ? cards[index - 1] : cards[index + 1];
      if (!target) return;
      if (event.key === 'ArrowUp') {
        storesEl.insertBefore(card, target);
      } else {
        storesEl.insertBefore(card, target.nextElementSibling);
      }
      saveOrder();
    });
  }

  function setupStore(card) {
    const nameEl = card.querySelector('.sl-store__name');

    const toggle = card.querySelector('[data-toggle]');
    if (toggle) {
      toggle.addEventListener('click', () => {
        setCollapsed(card, !card.classList.contains('is-collapsed'), true);
      });
    }

    const editButton = card.querySelector('[data-edit]');
    const renameForm = card.querySelector('[data-rename]');
    const renameInput = renameForm
      ? renameForm.querySelector('input[name="name"]')
      : null;
    const renameCancel = card.querySelector('[data-rename-cancel]');

    if (editButton && renameForm && renameInput) {
      editButton.addEventListener('click', () => {
        renameForm.hidden = false;
        renameInput.value = nameEl ? nameEl.textContent.trim() : '';
        renameInput.focus();
        renameInput.select();
      });

      if (renameCancel) {
        renameCancel.addEventListener('click', () => {
          renameForm.hidden = true;
        });
      }

      renameForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const name = renameInput.value.trim();
        if (!name) return;
        postJSON(base + '/stores/' + card.dataset.storeId + '/rename', { name }).then(
          (result) => {
            if (!result.ok) {
              showNotice(
                card,
                (result.data && result.data.error) || 'Could not rename that store.'
              );
              return;
            }
            const updated = (result.data && result.data.name) || name;
            if (nameEl) nameEl.textContent = updated;
            renameForm.hidden = true;
            updateLabels(card, updated);
            showNotice(card, '');
          }
        );
      });
    }

    const deleteForm = card.querySelector('[data-delete-store]');
    if (deleteForm) {
      deleteForm.addEventListener('submit', (event) => {
        const name = nameEl ? nameEl.textContent.trim() : 'this store';
        if (!window.confirm('Delete the ' + name + ' list and everything on it?')) {
          event.preventDefault();
        }
      });
    }

    const addForm = card.querySelector('[data-add-item]');
    if (addForm) {
      const input = addForm.querySelector('input[name="name"]');
      const submit = addForm.querySelector('button[type="submit"]');
      addForm.addEventListener('submit', (event) => {
        event.preventDefault();
        if (!input) return;
        const name = input.value.trim();
        if (!name) return;

        if (submit) submit.disabled = true;
        showNotice(card, '');

        postJSON(base + '/stores/' + card.dataset.storeId + '/items', { name }).then(
          (result) => {
            if (submit) submit.disabled = false;
            if (!result.ok || !result.data || !result.data.item) {
              showNotice(
                card,
                (result.data && result.data.error) || 'Could not add that item.'
              );
              return;
            }
            const list = card.querySelector('[data-items]');
            if (list) list.appendChild(buildRow(result.data.item));
            input.value = '';
            input.focus();
            refreshStore(card);
          }
        );
      });
    }

    for (const button of card.querySelectorAll('.sl-item')) {
      button.addEventListener('click', () => markOff(button));
    }

    setupDrag(card);
  }

  for (const card of storeCards()) setupStore(card);
  if (undoButton) undoButton.addEventListener('click', undoLast);
})();
