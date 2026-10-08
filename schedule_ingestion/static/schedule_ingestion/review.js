document.addEventListener('DOMContentLoaded', () => {
  const app = document.getElementById('review-app'); if (!app) return;
  let state = JSON.parse(document.getElementById('review-payload').textContent), url = app.dataset.url;
  let drafts = {}, added = [], openKey = null, busy = false, requestId = crypto.randomUUID();
  const editable = app.dataset.edit === '1', table = document.getElementById('schedule-table'), scroll = app.querySelector('.review-scroll');
  const search = document.getElementById('search'), group = document.getElementById('group-filter'), date = document.getElementById('date-filter'), filter = document.getElementById('status-filter');
  const status = document.getElementById('save-status'), save = document.getElementById('save-all'), publish = document.getElementById('publish');
  const unchecked = document.getElementById('unchecked-only');
  const params = new URLSearchParams(location.search); search.value = params.get('q') || ''; group.value = params.get('group') || ''; date.value = params.get('date') || ''; filter.value = params.get('status') || (params.has('needs_review') ? 'needs' : '');
  unchecked.checked = params.get('unchecked') === '1';
  const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
  const button = (text, fn) => { const b = el('button', text); b.type = 'button'; b.onclick = fn; return b; };
  const clone = value => JSON.parse(JSON.stringify(value));
  const annotation = row => row.annotations ? row.annotations.map(a => typeof a === 'string' ? a : a.text || '').join('; ') : row.annotation || '';
  const formatDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') ? value.split('-').reverse().join('.') : value || '';
  const keyOf = card => card.key || String(card.index);
  const cards = () => [...state.cards, ...added];
  const storageKey = () => 'tableparser-draft:' + url;
  const dirty = () => Object.keys(drafts).length > 0;
  function controls(row, index) { return {base_index:index, group:row.group || state.groups[0] || '', date:row.date || app.dataset.date, lesson_number:String(row.lesson_number || 1), part:String(row.part || 0), subgroup:String(row.subgroup || 0), subject:row.subject || '', teacher:row.teacher || '', classroom:row.classroom || '', annotation:annotation(row), reviewed:row.review_status === 'reviewed'}; }
  const originalRows = card => card.rows.map((row, i) => controls(row, card.indices[i]));
  const formRows = card => drafts[keyOf(card)] ? clone(drafts[keyOf(card)].rows) : originalRows(card);
  function displayRows(card) {
    if (!drafts[keyOf(card)]) return card.rows;
    return drafts[keyOf(card)].rows.map(row => ({...(card.rows[card.indices.indexOf(row.base_index)] || card.rows[0] || {}), ...row, annotations:undefined, review_status:row.reviewed || card.index === null ? 'reviewed' : 'needs_review'}));
  }
  function isAuto(row) { return row.review_status === 'confirmed' || Boolean(row.automatic_review_rule) || [true, 'True', 'true'].includes(row.teacher_proposal_applied) || ['confirmed','ml_proposal','extraction_ml_proposal','extraction_identity_proposal','prior_confirmation_proposal'].includes(row.parse_source) || (row.parse_source || '').startsWith('verified_'); }
  const wasRequired = card => card.rows.some(row => row.review_required === true || row.review_status === 'needs_review' || row.review_original_rows?.some(r => r.review_status === 'needs_review'));
  const applied = card => card.rows.some(row => row.review_applied === true);
  const changedCard = card => Boolean(drafts[keyOf(card)]) || applied(card);
  function matchesSearch(card) {
    const rows = displayRows(card);
    return (!group.value || rows.some(r => r.group === group.value)) && (!date.value || rows.some(r => r.date === date.value)) && (!search.value || JSON.stringify([card.rows, rows]).toLowerCase().includes(search.value.toLowerCase()));
  }
  function updateTabs() {
    const matching = cards().filter(matchesSearch);
    const counts = {'':matching.length, needs:matching.filter(wasRequired).length, auto:matching.filter(c => c.rows.some(isAuto)).length, dirty:matching.filter(changedCard).length};
    filter.querySelectorAll('button').forEach(b => { b.setAttribute('aria-pressed', String(b.dataset.filter === filter.value)); b.querySelector('.tab-count').textContent = counts[b.dataset.filter]; });
    document.getElementById('unchecked-label').hidden = filter.value !== 'needs';
  }
  function announce(text, error = false) { status.textContent = text; status.className = error ? 'error' : ''; }
  function persist() {
    try { if (dirty()) sessionStorage.setItem(storageKey(), JSON.stringify({drafts, added, requestId})); else sessionStorage.removeItem(storageKey()); }
    catch (_) { announce('Черновик остаётся в открытой странице, но браузер не смог сохранить его для восстановления. Не закрывайте вкладку до общего сохранения.', true); }
  }
  function updateControls() {
    const count = Object.keys(drafts).length;
    document.getElementById('draft-count').textContent = count ? `Изменено карточек: ${count} · ещё не сохранено` : '';
    document.getElementById('discard-all').hidden = !count;
    if (save) save.disabled = busy || !count;
    updateTabs();
  }
  function touch(card, rows) {
    const key = keyOf(card);
    if (card.index !== null && JSON.stringify(rows) === JSON.stringify(originalRows(card))) delete drafts[key];
    else drafts[key] = {index:card.index, rows:clone(rows)};
    requestId = crypto.randomUUID(); persist(); updateControls();
    const section = [...table.tBodies].find(b => b.dataset.key === key);
    if (section) { section.classList.toggle('dirty', Boolean(drafts[key])); const dot = section.querySelector('.dirty-dot'); if (dot) dot.hidden = !drafts[key]; }
  }
  function query() { const p = new URLSearchParams(); if (search.value) p.set('q', search.value); if (group.value) p.set('group', group.value); if (date.value) p.set('date', date.value); if (filter.value === 'needs') p.set('needs_review', '1'); else if (filter.value) p.set('status', filter.value); if (unchecked.checked) p.set('unchecked', '1'); return p.size ? '?' + p : ''; }
  function render() {
    const top = scroll.scrollTop, left = scroll.scrollLeft;
    [...table.tBodies].forEach(b => b.remove()); let count = 0, lessons = 0;
    for (const card of cards()) {
      const key = keyOf(card), rows = displayRows(card), needs = rows.some(r => r.review_status === 'needs_review');
      if (key !== openKey && (filter.value === 'needs' && (!wasRequired(card) || unchecked.checked && !rows.some(r => r.review_status !== 'reviewed')) || filter.value === 'auto' && !card.rows.some(isAuto) || filter.value === 'dirty' && !changedCard(card) || !matchesSearch(card))) continue;
      count++; lessons += rows.length;
      const section = el('tbody', undefined, 'review-card'); section.dataset.key = key; section.classList.toggle('needs', needs); section.classList.toggle('dirty', Boolean(drafts[key])); section.classList.toggle('expanded', openKey === key);
      section.classList.toggle('applied', applied(card)); section.classList.toggle('multiple', rows.length > 1);
      const visibleRows = rows.length ? rows : [null];
      visibleRows.forEach((row, number) => {
        const tr = el('tr', undefined, 'lesson-row');
        if (editable) { tr.tabIndex = 0; tr.setAttribute('aria-expanded', String(openKey === key)); tr.title = 'Нажмите, чтобы открыть или свернуть редактор';
          const toggle = () => { if (busy) return; openKey = openKey === key ? null : key; render(); };
          tr.onclick = () => { if (!window.getSelection().toString()) toggle(); };
          tr.onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggle(); } };
        }
        if (!number) { const raw = el('td', undefined, 'source'); raw.rowSpan = visibleRows.length; const dot = el('span', undefined, 'dirty-dot'); dot.hidden = !drafts[key]; dot.title = 'Изменения не сохранены'; raw.append(dot, el('span', card.rows[0]?.raw_cell || 'Добавленные занятия')); tr.append(raw); }
        if (row) {
          for (const [value, cls] of [[row.group,''],[formatDate(row.date),'date'],[row.lesson_number,''],[row.part || 0,''],[row.subgroup || 0,'']]) tr.append(el('td', value ?? '', cls));
          const subject = el('td', row.subject || '', 'subject'); if (annotation(row)) subject.append(el('br'), el('span', annotation(row), 'annotation')); tr.append(subject, el('td', row.teacher || ''), el('td', row.classroom || ''));
        } else { const empty = el('td', 'Все занятия карточки удалены из черновика.'); empty.colSpan = 8; tr.append(empty); }
        if (!number) {
          const review = el('td', undefined, 'reason'); review.rowSpan = visibleRows.length;
          review.append(el('span', !rows.length ? 'Удалено' : needs ? 'Требует ревью' : rows.every(r => r.review_status === 'reviewed') ? 'Проверено' : card.rows.some(isAuto) ? 'Автоисправлено' : 'Разобрано', 'badge'));
          const reasons = [...new Set(card.rows.map(r => r.review_reason).filter(Boolean))]; if (reasons.length) review.append(el('div', reasons.join('; '), 'muted')); tr.append(review);
          if (applied(card)) review.append(el('div', 'Правки сохранены', 'applied-label'));
        }
        section.append(tr);
      });
      table.append(section);
      if (openKey === key && editable) buildEditor(card, section);
    }
    if (!count) { const empty = table.createTBody(), row = empty.insertRow(), cell = row.insertCell(); cell.colSpan = 10; cell.textContent = 'Нет карточек по выбранным фильтрам.'; }
    document.getElementById('row-count').textContent = `Карточек: ${count} · Занятий: ${lessons}`;
    scroll.scrollTop = top; scroll.scrollLeft = left; history.replaceState(null, '', url + query()); updateControls();
  }
  function buildEditor(card, section) {
    const tr = el('tr', undefined, 'cell-editor'), td = el('td'); td.colSpan = 10;
    const panel = el('div', undefined, 'inline-panel'); panel.style.width = Math.max(300, scroll.clientWidth - 48) + 'px'; td.append(panel); tr.append(td); section.append(tr);
    const context = el('div', undefined, 'editor-context'), source = el('div'); source.append(el('strong', card.index === null ? 'Новые занятия' : 'Исходная ячейка'), el('pre', card.rows[0]?.raw_cell || 'Заполните одно или несколько занятий.'));
    const details = el('details'); details.append(el('summary', 'Данные парсера'), el('pre', JSON.stringify(card.rows, null, 2))); if (card.index !== null) context.append(source, details); else context.append(source); panel.append(context);
    const before = card.rows[0]?.review_original_rows;
    if (before?.length && before.some(row => Object.keys(row).length)) {
      const history = el('details', undefined, 'review-before'); history.append(el('summary', 'До первого ручного исправления'));
      const originalTable = el('table'), head = el('tr');
      ['Группа','Дата','Пара','Часть','Подгр.','Предмет','Преподаватель','Кабинет','Примечание'].forEach(label => head.append(el('th', label))); originalTable.append(head);
      before.forEach(row => { const line = el('tr'); [row.group,formatDate(row.date),row.lesson_number,row.part,row.subgroup,row.subject,row.teacher,row.classroom,annotation(row)].forEach(value => line.append(el('td', value ?? ''))); originalTable.append(line); });
      history.append(originalTable); panel.append(history);
    }
    const records = el('div'); panel.append(records); let rows = formRows(card);
    const changed = () => touch(card, rows);
    function drawRecords() {
      records.replaceChildren();
      rows.forEach((row, index) => {
        const record = el('div', undefined, 'edit-record');
        for (const [key, label, type] of [['group','Группа','select'],['date','Дата','date'],['lesson_number','Пара','number'],['part','Часть (0 / 1 / 2)','number'],['subgroup','Подгруппа (0 — общая)','number'],['classroom','Кабинет','text'],['subject','Предмет','text'],['teacher','Преподаватель','text'],['annotation','Примечание','text']]) {
          const wrapper = el('label', label, ['subject','teacher','annotation'].includes(key) ? 'wide' : ''), input = el(type === 'select' ? 'select' : 'input');
          if (type === 'select') state.groups.forEach(g => { const option = el('option', g); option.value = g; input.append(option); }); else input.type = type;
          input.value = row[key] ?? ''; if (type === 'number') { input.min = key === 'lesson_number' ? 1 : 0; input.step = 1; if (key === 'part') input.max = 2; if (key === 'subgroup') input.max = 9; }
          input.oninput = () => { row[key] = input.value; changed(); }; wrapper.append(input); record.append(wrapper);
        }
        if (card.index !== null) { const label = el('label', 'Строка проверена', 'check'), check = el('input'); check.type = 'checkbox'; check.checked = row.reviewed; check.onchange = () => { row.reviewed = check.checked; changed(); }; label.append(check); record.append(label); }
        const tools = el('div', undefined, 'row-tools'); tools.append(button('Копировать', () => { rows.splice(index + 1, 0, {...clone(row), base_index:null}); changed(); drawRecords(); }), button('Удалить', () => { rows.splice(index, 1); changed(); drawRecords(); })); record.append(tools); records.append(record);
      });
    }
    drawRecords();
    const actions = el('div', undefined, 'editor-actions'); actions.append(button('+ Пустое занятие', () => { rows.push({...controls({}, null), group:rows[0]?.group || state.groups[0] || '', date:rows[0]?.date || app.dataset.date, reviewed:card.index === null}); changed(); drawRecords(); }), el('span', 'Правки накапливаются. Сохранение — общей кнопкой вверху.', 'muted'));
    if (card.index !== null) actions.prepend(button('Сбросить правки карточки', () => { delete drafts[keyOf(card)]; requestId = crypto.randomUUID(); persist(); render(); }));
    panel.append(actions);
  }
  function lock(value) { busy = value; app.querySelectorAll('button,input,select').forEach(control => control.disabled = value); if (publish) publish.setAttribute('aria-disabled', String(value)); updateControls(); }
  async function saveAll() {
    if (busy) return false; if (!dirty()) return true;
    lock(true); announce('Сохранение…');
    try {
      const response = await fetch(url.replace('/review/', '/batch/'), {method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':app.querySelector('[name=csrfmiddlewaretoken]').value}, body:JSON.stringify({changes:Object.values(drafts), reason:'Ревью выгрузки', request_id:requestId})});
      const result = await response.json();
      if (!response.ok) { announce(result.error || 'Не удалось сохранить изменения.', true); if (result.latest_url) { const link = el('a', ' Открыть актуальную версию в новой вкладке'); link.href = result.latest_url; link.target = '_blank'; link.rel = 'noopener'; status.append(link); } return false; }
      try { sessionStorage.removeItem(storageKey()); } catch (_) {}
      state = result.state; url = result.url; drafts = {}; added = []; openKey = null; requestId = crypto.randomUUID();
      document.getElementById('version').textContent = 'v' + result.number;
      document.title = app.querySelector('h1').textContent + ' | EazyClass';
      app.querySelectorAll('[data-action]').forEach(a => a.href = url.replace('/review/', '/' + a.dataset.action + '/'));
      if (publish) publish.href = url.replace('/review/', '/publish/');
      app.querySelector('.review-history').textContent = 'Эта версия ещё не публиковалась.';
      render(); announce(`Все изменения сохранены одной версией — v${result.number}.`); return true;
    } catch (_) { announce('Не удалось получить ответ. Черновик сохранён в этой вкладке; повторите сохранение. Повтор запроса не создаст лишнюю версию.', true); return false; }
    finally { lock(false); }
  }
  if (save) save.onclick = saveAll;
  if (publish) publish.onclick = async event => { event.preventDefault(); if (busy) return; if (await saveAll()) location.assign(url.replace('/review/', '/publish/')); };
  if (editable) document.getElementById('add-card').onclick = () => { const card = {key:'new:' + crypto.randomUUID(), index:null, indices:[], rows:[]}; added.push(card); touch(card, [{...controls({}, null), reviewed:true}]); openKey = keyOf(card); render(); scroll.scrollTop = scroll.scrollHeight; scroll.scrollLeft = 0; };
  document.getElementById('discard-all').onclick = () => { if (!busy && confirm('Отменить все несохранённые правки этой вкладки?')) { drafts = {}; added = []; openKey = null; persist(); render(); announce('Черновик отменён. Сохранённая выгрузка не изменилась.'); } };
  filter.querySelectorAll('button').forEach(b => b.onclick = () => { filter.value = b.dataset.filter; openKey = null; render(); });
  for (const input of [search, group, date, unchecked]) input.onchange = () => { openKey = null; render(); };
  document.getElementById('clear-filters').onclick = () => { search.value = group.value = date.value = filter.value = ''; unchecked.checked = false; openKey = null; render(); };
  window.addEventListener('beforeunload', event => { if (dirty() || busy) { event.preventDefault(); event.returnValue = ''; } });
  if (editable) { try { const restored = JSON.parse(sessionStorage.getItem(storageKey()) || 'null'); if (restored) { drafts = restored.drafts; added = restored.added; requestId = restored.requestId; announce('Восстановлены несохранённые правки этой вкладки.'); } } catch (_) { announce('Не удалось восстановить локальный черновик.', true); } }
  render();
});
