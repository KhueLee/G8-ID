// Màn hình vận hành: hỏi trạng thái mỗi 400 ms. Mọi nghiệp vụ nằm ở phần nền (Python),
// nên đóng/mở lại Chrome hay tải lại trang không ảnh hưởng việc cân - in.
'use strict';
const $ = id => document.getElementById(id);
const val = id => $(id).value;
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
let pass = '', state = null, fails = 0, tab = 'home', busy = false, lastRows = '', lastPending = null;

async function api(path, body, method) {
  const opt = { method: method || (body ? 'POST' : 'GET'), headers: { 'X-Pass': pass } };
  if (body) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  return r.json();
}

// ---------- hộp thoại ----------
function modal(title, text, buttons, input) {
  return new Promise(resolve => {
    $('m-title').textContent = title; $('m-text').textContent = text;
    const inp = $('m-input'); inp.value = ''; inp.classList.toggle('hidden', !input);
    const box = $('m-btns'); box.innerHTML = '';
    const done = v => { $('modal').classList.add('hidden'); resolve(input && v ? inp.value : v); };
    buttons.forEach(([label, v]) => { const b = document.createElement('button'); b.textContent = label; b.onclick = () => done(v); box.appendChild(b); });
    inp.onkeydown = e => { if (e.key === 'Enter') done(true); };
    $('modal').classList.remove('hidden');
    if (input) inp.focus();
  });
}
const alertBox = (text, title) => modal(title || 'THÔNG BÁO', text, [['OK', true]]);
const confirmBox = (text, title, yes, no) => modal(title || 'XÁC NHẬN', text, [[yes || 'OK', true], [no || 'Cancel', false]]);

// ---------- vẽ trang chủ ----------
function ind(id, ok) { const e = $(id); e.classList.toggle('ok', ok === true); e.classList.toggle('bad', ok === false); }
function render(s) {
  state = s;
  $('swName').textContent = s.software;
  $('clock').textContent = s.time;
  $('meta').textContent = `${s.date} · v${s.version} · ${s.station} · ${s.mode}`;
  $('manualBanner').classList.toggle('hidden', s.mode === 'AUTO');
  $('manualBanner').textContent = s.mode === 'HYBRID'
    ? 'CHẾ ĐỘ HYBRID (THIẾT BỊ THẬT + WCS/RCS MÔ PHỎNG) — không dùng cho sản xuất thật'
    : 'CHẾ ĐỘ MANUAL (MÔ PHỎNG) — không dùng cho sản xuất thật';
  ['plc', 'printer', 'scale', 'barcode'].forEach(k => { ind('ind-' + k, s.dev[k].ok); $('ind-' + k).title = s.dev[k].detail; });
  ind('ind-wcs', s.wcs); ind('ind-rcs', s.rcs === null ? null : s.rcs); $('ind-rcs').title = s.rcs_error || '';
  ['red', 'yellow', 'green'].forEach(c => $('lamp-' + c).classList.toggle('on', s.light === c));
  $('btnIdentify').disabled = !s.can_identify;

  const p = s.pallet || {};
  $('curDone').textContent = s.carton[0]; $('curTotal').textContent = '/' + s.carton[1];
  $('f-po').textContent = p.po || 'N/A'; $('f-pallet').textContent = p.pallet_id || 'N/A';
  $('f-loc').textContent = p.location || 'N/A'; $('f-item').textContent = p.item || 'N/A';
  $('f-spec').textContent = p.spec || 'N/A'; $('f-weight').textContent = p.weight || 'N/A';
  $('f-pallets').textContent = s.pallets[0] + '/' + s.pallets[1];
  $('f-order').textContent = s.order[0] + '/' + s.order[1];
  $('f-date').textContent = p.mfg_date || s.date;
  for (let i = 0; i < 3; i++) {
    const e = $('pos' + i); e.classList.toggle('on', s.pos === i);
    e.querySelector('b').textContent = s.pos === i ? (s.positions[i] || '') : '';
  }

  const key = JSON.stringify(s.rows) + s.current;
  if (key !== lastRows) {
    lastRows = key;
    const next = s.current || (s.rows.find(r => r.st === 0) || {}).code;
    $('list').tBodies[0].innerHTML = s.rows.map(r => {
      const cls = r.code === next ? 'cur' : r.st >= 1 ? 'done' : r.text === 'In lỗi' ? 'err' : '';
      return `<tr class="${cls}"><td>${r.stt}</td><td>${esc(r.code)}</td><td>${esc(r.text)}</td><td>${esc(r.pallet)}</td></tr>`;
    }).join('');
    const cur = document.querySelector('#list tr.cur'); if (cur) cur.scrollIntoView({ block: 'nearest' });
  }

  const m = $('message'); m.textContent = s.message; m.className = 'c-' + s.msg_color;
  $('weight').textContent = s.weight === null ? '--- g' : s.weight + ' g';
  const big = $('big'); big.textContent = s.big; big.className = 'big ' + s.big;
  const c = s.counter, pct = n => (c.total ? (n * 100 / c.total).toFixed(1) : '0.0') + '%';
  $('c-pass').textContent = c.pass + '/' + c.total; $('c-fail').textContent = c.fail + '/' + c.total;
  $('c-ppass').textContent = pct(c.pass); $('c-pfail').textContent = pct(c.fail);
  const printing = !!(s.job && s.job.active);
  $('btnStart').disabled = s.running || printing; $('btnStart').innerHTML = s.running ? '&#9654; Đang chạy' : printing ? '&#9113; Đang in lại' : '&#9654; Bắt đầu';

  const lb = $('logbox'), atEnd = lb.scrollTop + lb.clientHeight >= lb.scrollHeight - 30;
  lb.innerHTML = s.logs.map(l => `<div class="${l.lv}">${l.t} [${l.lv}] [${esc(l.tag)}] ${esc(l.msg)}</div>`).join('');
  if (atEnd) lb.scrollTop = lb.scrollHeight;

  // Hộp thoại nhận lệnh nằm ở phần nền: tải lại trang vẫn còn.
  const pend = s.pending ? JSON.stringify(s.pending) : null;
  if (pend && pend !== lastPending && $('modal').classList.contains('hidden')) {
    lastPending = pend;
    confirmBox(`Có tiếp nhận lệnh sản xuất mới không?\nMã lệnh: ${s.pending.po}`, 'Xác nhận tiếp nhận lệnh', 'Yes', 'No')
      .then(async yes => { const r = await api('/api/order/answer', { accept: !!yes }); lastPending = null; if (!r.ok) alertBox(r.error, 'Lỗi'); });
  }
  if (!pend) lastPending = null;
}

async function poll() {
  try {
    render(await api('/api/state'));
    fails = 0; $('offline').classList.add('hidden');
  } catch (e) {
    if (++fails >= 3) $('offline').classList.remove('hidden');
  }
  setTimeout(poll, 400);
}

// ---------- nút vận hành ----------
async function guardBusy(fn) { if (busy) return; busy = true; try { await fn(); } catch (e) { alertBox('Không gọi được phần mềm: ' + e, 'LỖI'); } finally { busy = false; } }
$('btnStart').onclick = () => guardBusy(async () => {
  let r = await api('/api/start', {});
  if (r.confirm) { if (!(await confirmBox(r.confirm, r.title))) return; r = await api('/api/start', { confirm_no_light: true }); }
  if (!r.ok && r.error) alertBox(r.error, r.title);
});
$('btnStop').onclick = () => guardBusy(() => api('/api/stop', {}));
$('btnReset').onclick = () => guardBusy(async () => {
  if (await confirmBox('Bạn có chắc muốn đặt lại toàn bộ bộ đếm không?', 'Xác nhận', 'Yes', 'No')) { await api('/api/counter/reset', {}); alertBox('Đã đặt lại bộ đếm!'); }
});
$('btnIdentify').onclick = () => guardBusy(async () => {
  if (!(await confirmBox('Gửi định danh pallet về server?', 'ĐỊNH DANH', 'Yes', 'No'))) return;
  const r = await api('/api/identify', {});
  if (!r.ok) alertBox(r.error, 'GỬI PALLET LỖI!');
});

// ---------- thẻ ----------
document.querySelectorAll('nav button').forEach(b => b.onclick = () => openTab(b.dataset.tab));
async function openTab(name) {
  if (name === 'settings') {
    if (state && state.running) return alertBox('Thẻ Cài đặt bị khóa khi đang chạy. Hãy bấm Dừng trước.');
    const p = await modal('Cài đặt', 'Nhập mật khẩu:', [['OK', true], ['Cancel', false]], true);
    if (p === false) return;
    pass = p;
    if (!(await api('/api/login', {})).ok) { pass = ''; return alertBox('Sai mật khẩu', 'LỖI'); }
    await loadSettings();
  }
  tab = name;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('hidden', t.id !== 'tab-' + name));
  document.querySelectorAll('nav button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  if (name === 'info') loadInfo();
  if (name === 'logs') loadLogFiles();
}

// ---------- cài đặt ----------
const S_NUM = ['scale_value', 'scale_error', 'time_scale', 'pallet_print_delay_s', 'barcode_retries', 'barcode_timeout_ms'];
const D_FIELDS = { scale: ['port', 'baudrate'], barcode: ['port', 'baudrate'], printer: ['connect_type', 'usb_name', 'com_port', 'lan_ip', 'driver_name'], plc: ['enabled', 'station_number'] };
async function loadSettings() {
  const r = await api('/api/settings');
  if (!r.ok) return alertBox(r.error, 'LỖI');
  const s = r.settings;
  $('s-mode').textContent = r.mode;
  S_NUM.forEach(k => $('s-' + k).value = s[k]);
  $('s-print_pallet').checked = s.print_pallet; $('s-confirm_new_order').checked = s.confirm_new_order;
  $('s-auto_start_on_order').checked = s.auto_start_on_order;
  $('s-pallet_done_trigger').value = s.pallet_done_trigger;
  for (let i = 0; i < 6; i++) $('s-pos' + i).value = s.positions[i] || '';
  for (const d in D_FIELDS) D_FIELDS[d].forEach(k => { const e = $(`d-${d}-${k}`); if (e.type === 'checkbox') e.checked = !!r.devices[d][k]; else e.value = r.devices[d][k]; });
  $('v-pallet_done_url').value = r.servers.pallet_done_url;
  $('comlist').innerHTML = r.ports.map(p => `<option value="${esc(p.port)}">${esc(p.desc)}</option>`).join('');
  $('comhint').textContent = 'Cổng COM đang có: ' + (r.ports.map(p => `${p.port} (${p.desc})`).join(', ') || 'không có');
}
async function act(path, body, okText) {
  const r = await api(path, body);
  await alertBox(r.ok ? okText : r.error, r.ok ? 'THÔNG BÁO' : 'LỖI');
  return r.ok;
}
async function saveSettings() {
  const b = { print_pallet: $('s-print_pallet').checked, confirm_new_order: $('s-confirm_new_order').checked, auto_start_on_order: $('s-auto_start_on_order').checked, pallet_done_trigger: val('s-pallet_done_trigger'), positions: [] };
  S_NUM.forEach(k => b[k] = Number(val('s-' + k)));
  for (let i = 0; i < 6; i++) b.positions.push(val('s-pos' + i));
  await act('/api/settings', b, 'Đã lưu thông số.');
}
async function saveDevices() {
  if (!(await confirmBox('Do you want to reset all of the connections', 'Warning!'))) return;
  const devices = {};
  for (const d in D_FIELDS) { devices[d] = {}; D_FIELDS[d].forEach(k => { const e = $(`d-${d}-${k}`); devices[d][k] = e.type === 'checkbox' ? e.checked : e.type === 'number' ? Number(e.value) : e.value.trim(); }); }
  await act('/api/devices', { devices, servers: { pallet_done_url: val('v-pallet_done_url').trim() } }, 'Đã lưu và kết nối lại thiết bị.');
}
async function setMode(m) {
  if (!(await confirmBox(`Chuyển sang chế độ ${m}?`, 'Chế độ chạy', 'Yes', 'No'))) return;
  if (await act('/api/mode', { mode: m }, 'Đã chuyển chế độ ' + m)) loadSettings();
}
async function reprintPallet(palletId) {
  const q = palletId ? `In lại toàn bộ tem của pallet ${palletId}?` : 'Bạn có chắc muốn in toàn bộ mã pallet đang thực hiện không?';
  if (!(await confirmBox(q, 'In lại tem pallet', 'Yes', 'No'))) return;
  const r = await api('/api/reprint_pallet', { pallet_id: palletId });
  if (!r.ok) return alertBox(r.error, 'LỖI');
  await alertBox(`Đang in lại ${r.total} tem của pallet ${r.pallet_id}.\nTiến độ hiện ở dòng thông báo Trang chủ. Bấm Dừng để hủy.`);
  openTab('home');
}
async function changePass() { if (await act('/api/password', { new: val('m-pass') }, 'Đã đổi mật khẩu.')) pass = val('m-pass'); }
async function quitApp() {
  if (await confirmBox('Thoát hẳn phần mềm (đóng thiết bị, tắt cơ sở dữ liệu)?', 'Thoát', 'Yes', 'No')) await act('/api/quit', {}, 'Phần mềm đang thoát. Chạy lại run_app.bat để mở.');
}

// ---------- thông số ----------
const kv = (id, rows) => $(id).innerHTML = rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('');
async function loadInfo() {
  const r = await api('/api/info'), s = r.settings;
  kv('i-station', [['Mã trạm', r.station], ['Phiên bản', r.version], ['Chế độ', r.mode], ['Đã chạy', r.uptime_min + ' phút'],
    ['Khối lượng chuẩn', s.scale_value + ' g (dùng khi lệnh không gửi Weight_ref)'], ['Sai số', '± ' + s.scale_error + ' g'], ['Thời gian cân', s.time_scale + ' s'],
    ['In mã pallet', s.print_pallet ? 'Có' : 'Không'], ['Gửi pallet', s.pallet_done_trigger === 'auto' ? 'Tự động' : 'Bấm nút ĐỊNH DANH'], ['Vị trí sàn', s.positions.join(', ')]]);
  kv('i-dev', [...['plc', 'printer', 'scale', 'barcode'].map(k => [k.toUpperCase(), (r.devices[k].ok ? 'ĐÃ KẾT NỐI' : 'MẤT KẾT NỐI') + ' — ' + r.devices[k].detail]),
    ['Cổng nhận lệnh', r.order_port + '  (/ids/orderTask/, /ids/cancelTask/, /ids/confirm_product/)'], ['Server nhận pallet', r.pallet_done_url],
    ['Lần gửi gần nhất', r.rcs === null ? 'chưa gửi' : r.rcs ? 'thành công' : 'LỖI: ' + r.rcs_error], ['Thư mục log', r.log_dir]]);
  kv('i-db', [['Database', r.db_name], ['Pallet đang làm / chờ', r.db.pallets], ['Thùng đang làm / chờ', r.db.parcels], ['Lịch sử pallet', r.db.pallets_his],
    ['Lịch sử thùng', r.db.parcels_his], ['Sự kiện', r.db.event_log], ['Dung lượng', (r.db.size_mb || 0) + ' MB']]);
  $('i-queue').innerHTML = '<tr><th>Pallet</th><th>Mã lệnh</th><th>Task</th><th>Vị trí</th><th>Số thùng</th><th>Trạng thái</th><th></th></tr>' +
    (r.queue.map(q => `<tr><td>${esc(q.pallet_id)}</td><td>${esc(q.po)}</td><td>${esc(q.task_id)}</td><td>${esc(q.location)}</td><td>${q.cartons}</td><td>${q.status}</td>
      <td><button class="b danger" data-cancel="${esc(q.pallet_id)}">Hủy</button></td></tr>`).join('') || '<tr><td colspan="7">Không có lệnh</td></tr>');
  if (!$('h-from').value) { const d = new Date(), t = new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); $('h-from').value = t; $('h-to').value = t; }
  loadHistory();
}
async function needPass() {
  if (pass && (await api('/api/login', {})).ok) return true;
  const p = await modal('Mật khẩu', 'Nhập mật khẩu:', [['OK', true], ['Cancel', false]], true);
  if (p === false) return false;
  pass = p;
  if ((await api('/api/login', {})).ok) return true;
  pass = ''; await alertBox('Sai mật khẩu', 'LỖI'); return false;
}
document.addEventListener('click', async e => {
  const t = e.target;
  if (t.dataset.cancel) { if (await needPass() && await confirmBox('Hủy pallet ' + t.dataset.cancel + '?', 'Hủy', 'Yes', 'No')) { await act('/api/cancel', { pallet_id: t.dataset.cancel }, 'Đã hủy pallet.'); loadInfo(); } }
  if (t.dataset.reload) { if (await needPass() && await confirmBox('Nạp lại pallet ' + t.dataset.reload + ' để làm lại?', 'Reload', 'Yes', 'No')) { await act('/api/reload', { pallet_id: t.dataset.reload }, 'Đã nạp lại pallet.'); loadInfo(); } }
  if (t.dataset.reprint) { if (await needPass()) await reprintPallet(t.dataset.reprint); }
  if (t.dataset.parcels) {
    const r = await api('/api/history/parcels?pallet=' + encodeURIComponent(t.dataset.parcels));
    $('i-his-parcels').innerHTML = `<tr><th colspan="5">Thùng của pallet ${esc(t.dataset.parcels)}</th></tr><tr><th>STT</th><th>Mã định danh</th><th>Khối lượng (g)</th><th>Số lần in</th><th>Thời gian</th></tr>` +
      r.rows.map(x => `<tr><td>${x.stt}</td><td>${esc(x.code)}</td><td>${x.weight == null ? '' : x.weight}</td><td>${x.prints}</td><td>${x.done_at}</td></tr>`).join('');
  }
});
async function loadHistory() {
  const r = await api(`/api/history?from=${val('h-from')}&to=${val('h-to')}&q=${encodeURIComponent(val('h-q'))}`);
  $('i-his').innerHTML = '<tr><th>Thời gian</th><th>Pallet</th><th>Mã lệnh</th><th>Sản phẩm</th><th>Vị trí</th><th>Thùng đạt</th><th>Kết quả</th><th></th></tr>' +
    (r.rows.map(h => `<tr><td>${h.done_at}</td><td>${esc(h.pallet_id)}</td><td>${esc(h.po)}</td><td>${esc(h.item)}</td><td>${esc(h.location)}</td><td>${h.cartons}</td><td>${h.status} / ${esc(h.reason)}</td>
      <td><button class="b" data-parcels="${esc(h.pallet_id)}">Xem thùng</button> <button class="b" data-reprint="${esc(h.pallet_id)}">In lại tem</button> <button class="b warn" data-reload="${esc(h.pallet_id)}">Nạp lại</button></td></tr>`).join('') || '<tr><td colspan="8">Không có dữ liệu</td></tr>');
}

// ---------- log ----------
async function loadLogFiles() {
  const r = await api('/api/logs/files');
  $('l-file').innerHTML = '<option value="">(300 dòng gần nhất trong bộ nhớ)</option>' + r.files.map(f => `<option value="${esc(f.name)}">${esc(f.name)} — ${(f.size / 1024).toFixed(0)} KB — ${f.mtime}</option>`).join('');
  loadLogs();
}
async function loadLogs() {
  const r = await api(`/api/logs?file=${encodeURIComponent(val('l-file'))}&grep=${encodeURIComponent(val('l-grep'))}`);
  const g = val('l-grep').toLowerCase();
  $('l-out').textContent = r.lines.filter(x => !g || x.toLowerCase().includes(g)).join('\n') || '(không có dòng nào)';
  window.scrollTo(0, document.body.scrollHeight); $('tab-logs').scrollTop = $('tab-logs').scrollHeight;
}

poll();
