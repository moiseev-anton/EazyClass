document.addEventListener('DOMContentLoaded', () => {
  const names = document.getElementById('id_sheet_names'), gids = document.getElementById('id_sheet_gids');
  const root = document.getElementById('source-sheets');
  if (!names || !gids || !root) return;
  function sync() {
    const rows = [...root.children].map(row => [...row.querySelectorAll('input')].map(i => i.value));
    names.value = JSON.stringify(rows.map(r => r[0]));
    gids.value = JSON.stringify(Object.fromEntries(rows.map(r => [r[0], r[1] === '' ? null : Number(r[1])])));
  }
  function add(name = '', gid = '') {
    const row = document.createElement('div'); row.style.cssText = 'display:flex;gap:12px;margin-bottom:12px;align-items:center;flex-wrap:wrap';
    for (const [label, value, type] of [['Название листа', name, 'text'], ['gid', gid, 'number']]) {
      const wrapper = document.createElement('label'); wrapper.style.width = 'auto'; wrapper.textContent = label + ' ';
      const input = document.createElement('input'); input.type = type; input.value = value; input.required = true;
      if (type === 'number') { input.min = '0'; input.step = '1'; }
      input.addEventListener('input', sync); wrapper.append(input); row.append(wrapper);
    }
    const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Удалить';
    remove.onclick = () => { row.remove(); sync(); }; row.append(remove); root.append(row);
  }
  let initial = [], mapping = {};
  try { initial = JSON.parse(names.value || '[]'); mapping = JSON.parse(gids.value || '{}'); } catch (_) {}
  if (Array.isArray(initial)) initial.forEach(name => add(name, mapping[name] ?? ''));
  if (!root.children.length) add();
  document.getElementById('source-add').onclick = () => { add(); sync(); };
  names.form.addEventListener('submit', sync);
});
