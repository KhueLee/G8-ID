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
// Chữ dài thì xuống dòng, vẫn dài thì thu nhỏ dần cho vừa ô (tối đa `lines` dòng).
function setFit(el, text, max, min, lines) {
  text = String(text == null ? '' : text);
  const key = text + '|' + el.clientWidth + 'x' + el.clientHeight;
  if (el.dataset.fit === key) return;
  el.dataset.fit = key;
  el.innerHTML = `<span class="fit">${esc(text)}</span>`;
  const sp = el.firstChild;
  let f = max;
  for (; f > min; f -= 2) {
    el.style.fontSize = f + 'px';
    const h = sp.getBoundingClientRect().height;
    if (h <= el.clientHeight + 1 && h <= f * 1.15 * lines + 2) break;
  }
  el.style.fontSize = f + 'px';
}
function ind(id, ok) { const e = $(id); e.classList.toggle('ok', ok === true); e.classList.toggle('bad', ok === false); }
function render(s) {
  state = s;
  $('swName').textContent = s.software;
  $('clock').textContent = s.time;
  $('meta').textContent = `${s.date} · v${s.version} · ${s.station} · Bàn ${s.desk_no} · ${s.mode}`;
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
  const rows = { 'f-po': p.po, 'f-pallet': p.pallet_id, 'f-loc': p.location, 'f-item': p.item, 'f-spec': p.spec,
    'f-weight': p.weight, 'f-pallets': s.pallets[0] + '/' + s.pallets[1], 'f-order': s.order[0] + '/' + s.order[1],
    'f-date': p.mfg_date || s.date };
  for (const id in rows) setFit($(id), rows[id] || 'N/A', 28, 14, 2);
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

  const m = $('message'); setFit(m, s.message, 44, 18, 2); m.className = 'c-' + s.msg_color;
  $('weight').textContent = s.weight === null ? '--- g' : s.weight + ' g';
  const big = $('big'); big.textContent = s.big; big.className = 'big ' + s.big;
  const c = s.counter, pct = n => (c.total ? (n * 100 / c.total).toFixed(1) : '0.0') + '%';
  $('c-pass').textContent = c.pass + '/' + c.total; $('c-fail').textContent = c.fail + '/' + c.total;
  $('c-ppass').textContent = pct(c.pass); $('c-pfail').textContent = pct(c.fail);
  const printing = !!(s.job && s.job.active);
  $('btnStart').disabled = s.running || printing; $('btnStart').innerHTML = s.running ? '&#9654; Đang chạy' : printing ? '&#9113; Đang in lại' : '&#9654; Bắt đầu';


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
// Không hỏi xác nhận: nút chỉ sáng khi có pallet đủ thùng chờ định danh, phần nền kiểm tra lại.
$('btnIdentify').onclick = () => guardBusy(async () => {
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
    loadMfg(); loadInfo();
  }
  tab = name;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('hidden', t.id !== 'tab-' + name));
  document.querySelectorAll('nav button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  if (name === 'info') openOrders();
  if (name === 'logs') loadLogFiles();
}

// ---------- cài đặt ----------
const S_NUM = ['scale_value', 'scale_error', 'time_scale'];
const D_FIELDS = { scale: ['port', 'baudrate'], barcode: ['port', 'baudrate'], printer: ['connect_type', 'usb_name', 'com_port', 'lan_ip', 'driver_name'], plc: ['enabled', 'station_number', 'com_port'] };
const COM_SEL = { scale: 'd-scale-port', barcode: 'd-barcode-port', printer: 'd-printer-com_port', plc: 'd-plc-com_port' };
const DEV_NAME = { scale: 'Cân', barcode: 'Đầu đọc', printer: 'Máy in', plc: 'PLC' };
let ports = [];
async function loadSettings() {
  const r = await api('/api/settings');
  if (!r.ok) return alertBox(r.error, 'LỖI');
  const s = r.settings;
  $('s-mode').textContent = r.mode;
  S_NUM.forEach(k => $('s-' + k).value = s[k]);
  $('s-confirm_new_order').checked = s.confirm_new_order;
  $('s-auto_start_on_order').checked = s.auto_start_on_order;
  $('s-pallet_done_trigger').value = s.pallet_done_trigger;
  for (let i = 0; i < 6; i++) $('s-pos' + i).value = s.positions[i] || '';
  for (const d in D_FIELDS) D_FIELDS[d].forEach(k => { const e = $(`d-${d}-${k}`); if (e.type === 'checkbox') e.checked = !!r.devices[d][k]; else if (!e.classList.contains('comsel')) e.value = r.devices[d][k] == null ? '' : r.devices[d][k]; });
  $('d-desk_no').value = r.desk_no;
  $('v-pallet_done_url').value = r.servers.pallet_done_url;
  document.querySelectorAll('.testres').forEach(e => { e.textContent = ''; e.className = 'testres'; });
  ports = r.ports;
  detectPat = Object.fromEntries(AUTO_DEV.map(d => [d, r.devices[d].detect || '']));
  fillPorts(Object.fromEntries(Object.keys(COM_SEL).map(d => [d, { auto: r.devices[d].auto !== false, port: r.devices[d][COM_SEL[d].split('-').pop()] || '' }])));
}

// ---------- chọn cổng COM: Tự dò (theo tên cổng trong Windows) / None / cổng đang có, không cho trùng ----------
const AUTO_DEV = ['scale', 'barcode', 'plc'];
let detectPat = {};
const comActive = d => d === 'printer' ? val('d-printer-connect_type') === 'COM' : d === 'plc' ? $('d-plc-enabled').checked : true;
function preview() {
  // Giống portmap.detect phía Python: cổng chọn tay giữ nguyên, thiết bị Tự dò lấy cổng khớp tên.
  const taken = new Set(Object.keys(COM_SEL).filter(d => comActive(d) && val(COM_SEL[d]) !== 'AUTO' && val(COM_SEL[d])).map(d => val(COM_SEL[d]).toUpperCase()));
  const out = {};
  for (const d of AUTO_DEV) {
    if (val(COM_SEL[d]) !== 'AUTO' || !comActive(d)) continue;
    const pat = (detectPat[d] || '').toLowerCase();
    const hits = ports.filter(p => pat && p.desc.toLowerCase().includes(pat) && !taken.has(p.port.toUpperCase())).map(p => p.port);
    out[d] = hits.length === 1 ? { port: hits[0] } : { port: '', note: hits.length ? `có ${hits.length} cổng khớp (${hits.join(', ')})` : 'không thấy cổng' };
    if (hits.length === 1) taken.add(hits[0].toUpperCase());
  }
  return out;
}
const portOf = (d, pv) => val(COM_SEL[d]) === 'AUTO' ? ((pv[d] || {}).port || '') : val(COM_SEL[d]);
function fillPorts(current) {
  for (const d in COM_SEL) {
    const sel = $(COM_SEL[d]), cur = current[d] || {}, want = String(cur.port || '').trim().toUpperCase();
    const opts = [['', 'None (không dùng)']].concat(ports.map(p => [p.port, `${p.port} — ${p.desc}`]));
    const have = opts.find(([v]) => v && v.toUpperCase() === want);
    if (want && !have) opts.splice(1, 0, [want, `${want} — KHÔNG CÓ TRÊN MÁY`]);
    if (AUTO_DEV.includes(d)) opts.unshift(['AUTO', 'Tự dò']);
    sel.innerHTML = opts.map(([v, t]) => `<option value="${esc(v)}" data-label="${esc(t)}">${esc(t)}</option>`).join('');
    sel.value = cur.auto && AUTO_DEV.includes(d) ? 'AUTO' : have ? have[0] : want;
  }
  markTaken();
}
function markTaken() {
  const pv = preview(), used = {}, clash = [], miss = [];
  for (const d in COM_SEL) {
    const p = portOf(d, pv).toUpperCase();
    if (!comActive(d) || !p) continue;
    if (used[p]) clash.push(`${p}: ${DEV_NAME[used[p]]} và ${DEV_NAME[d]}`); else used[p] = d;
  }
  for (const d in COM_SEL) {
    const sel = $(COM_SEL[d]);
    sel.disabled = !comActive(d);
    for (const o of sel.options) {
      if (o.value === 'AUTO') {
        const r = pv[d];
        o.textContent = `Tự dò "${detectPat[d] || ''}"` + (!r ? '' : ' → ' + (r.port || 'KHÔNG THẤY, chọn cổng thủ công'));
        if (r && !r.port) miss.push(`${DEV_NAME[d]} (${r.note} "${detectPat[d] || ''}")`);
        continue;
      }
      const by = o.value && used[o.value.toUpperCase()], taken = by && by !== d && o.value !== sel.value;
      o.disabled = !!taken;
      o.textContent = o.dataset.label + (taken ? `  [đang dùng: ${DEV_NAME[by]}]` : '');
    }
  }
  const lines = ['Cổng COM đang có trên máy: ' + (ports.map(p => `${p.port} (${p.desc})`).join(', ') || 'không có')];
  if (miss.length) lines.push('TỰ DÒ KHÔNG RA: ' + miss.join('; ') + ' — kiểm tra cáp, bấm Dò lại cổng COM hoặc chọn cổng thủ công.');
  if (clash.length) lines.push('TRÙNG CỔNG — ' + clash.join('; ') + '. Đổi một thiết bị sang cổng khác hoặc None.');
  const h = $('comhint');
  h.textContent = lines.join('\n');
  h.classList.toggle('bad', miss.length + clash.length > 0);
}
document.addEventListener('change', e => { if (e.target.classList.contains('comsel') || ['d-printer-connect_type', 'd-plc-enabled'].includes(e.target.id)) markTaken(); });
const curPorts = () => Object.fromEntries(Object.keys(COM_SEL).map(d => [d, val(COM_SEL[d]) === 'AUTO' ? { auto: true, port: '' } : { auto: false, port: val(COM_SEL[d]) }]));
async function refreshPorts() {
  const r = await api('/api/ports');
  if (!r.ok) return alertBox(r.error, 'LỖI');
  ports = r.ports;
  fillPorts(curPorts());
}
function formDevice(d) {
  const o = {}, pv = preview();
  D_FIELDS[d].forEach(k => {
    const e = $(`d-${d}-${k}`);
    if (e.classList.contains('comsel')) {
      if (AUTO_DEV.includes(d)) o.auto = e.value === 'AUTO';
      o[k] = portOf(d, pv);
    } else o[k] = e.type === 'checkbox' ? e.checked : e.type === 'number' ? Number(e.value) : e.value.trim();
  });
  return o;
}
async function testDevice(d, btn) {
  const out = $('t-' + d);
  out.className = 'testres';
  out.textContent = d === 'barcode' ? 'Đang kiểm tra… đưa một mã vạch vào trước đầu đọc (chờ tối đa 6 s).' : 'Đang kiểm tra…';
  btn.disabled = true;
  try {
    const r = await api('/api/devices/test', { device: d, cfg: formDevice(d) });
    out.textContent = r.ok ? r.text : r.error;
    out.classList.add(r.ok && r.pass ? 'good' : 'bad');
  } catch (e) {
    out.textContent = 'Lỗi: ' + e; out.classList.add('bad');
  } finally { btn.disabled = false; }
}
async function act(path, body, okText) {
  const r = await api(path, body);
  await alertBox(r.ok ? okText : r.error, r.ok ? 'THÔNG BÁO' : 'LỖI');
  return r.ok;
}
async function saveSettings() {
  const b = { confirm_new_order: $('s-confirm_new_order').checked, auto_start_on_order: $('s-auto_start_on_order').checked, pallet_done_trigger: val('s-pallet_done_trigger'), positions: [] };
  S_NUM.forEach(k => b[k] = Number(val('s-' + k)));
  for (let i = 0; i < 6; i++) b.positions.push(val('s-pos' + i));
  await act('/api/settings', b, 'Đã lưu thông số.');
}
async function saveDevices() {
  if (!(await confirmBox('Do you want to reset all of the connections', 'Warning!'))) return;
  const devices = {};
  for (const d in D_FIELDS) devices[d] = formDevice(d);
  await act('/api/devices', { devices, desk_no: Number(val('d-desk_no')), servers: { pallet_done_url: val('v-pallet_done_url').trim() } }, 'Đã lưu và kết nối lại thiết bị.');
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
  if (await confirmBox('Thoát hẳn phần mềm (đóng thiết bị, tắt cơ sở dữ liệu)?', 'Thoát', 'Yes', 'No')) await act('/api/quit', {}, 'Phần mềm đang thoát. Chạy lại chay_dinh_danh.bat để mở.');
}

// ---------- thông tin trạm (thẻ Cài đặt) ----------
const kv = (id, rows) => $(id).innerHTML = rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('');
async function loadInfo() {
  const r = await api('/api/info'), s = r.settings;
  kv('i-station', [['Mã trạm', r.station], ['Bàn định danh số', r.desk_no], ['Phiên bản', r.version], ['Chế độ', r.mode], ['Đã chạy', r.uptime_min + ' phút'],
    ['Khối lượng chuẩn', s.scale_value + ' g (dùng khi lệnh không gửi Weight_ref)'], ['Sai số', '± ' + s.scale_error + ' g'], ['Thời gian cân', s.time_scale + ' s'],
    ['Gửi pallet', s.pallet_done_trigger === 'auto' ? 'Tự động' : 'Bấm nút ĐỊNH DANH'], ['Vị trí sàn', s.positions.join(', ')]]);
  kv('i-dev', [...['plc', 'printer', 'scale', 'barcode'].map(k => [k.toUpperCase(), (r.devices[k].ok ? 'ĐÃ KẾT NỐI' : 'MẤT KẾT NỐI') + ' — ' + r.devices[k].detail]),
    ['Cổng nhận lệnh', r.order_port + '  (/ids/orderTask/, /ids/cancelTask/, /ids/confirm_product/)'], ['Server nhận pallet', r.pallet_done_url],
    ['Lần gửi gần nhất', r.rcs === null ? 'chưa gửi' : r.rcs ? 'thành công' : 'LỖI: ' + r.rcs_error], ['Thư mục log', r.log_dir]]);
  kv('i-db', [['Database', r.db_name], ['Pallet đang làm / chờ', r.db.pallets], ['Thùng đang làm / chờ', r.db.parcels], ['Lịch sử pallet', r.db.pallets_his],
    ['Lịch sử thùng', r.db.parcels_his], ['Sự kiện', r.db.event_log], ['Dung lượng', (r.db.size_mb || 0) + ' MB']]);
}
async function needPass() {
  if (pass && (await api('/api/login', {})).ok) return true;
  const p = await modal('Mật khẩu', 'Nhập mật khẩu:', [['OK', true], ['Cancel', false]], true);
  if (p === false) return false;
  pass = p;
  if ((await api('/api/login', {})).ok) return true;
  pass = ''; await alertBox('Sai mật khẩu', 'LỖI'); return false;
}
document.addEventListener('click', async e => { if (e.target.dataset.test) await testDevice(e.target.dataset.test, e.target); });

// ---------- ngày sản xuất (Cài đặt vận hành) ----------
const toIso = d => /^\d{2}\/\d{2}\/\d{4}$/.test(d || '') ? d.split('/').reverse().join('-') : '';
const fromIso = d => d ? d.split('-').reverse().join('/') : '';
let mfgLocked = true;
function mfgUi() { $('mf-date').disabled = mfgLocked || !$('mf-on').checked; }
$('mf-on').onchange = mfgUi;
function showMfg(m) {
  mfgLocked = !m.has_order || m.locked;
  $('mf-po').textContent = m.has_order ? m.po : 'Chưa có lệnh';
  $('mf-order').textContent = m.has_order ? (m.order_date || '(lệnh không gửi ngày)') : '-';
  $('mf-eff').textContent = m.has_order ? (m.effective || '-') + (m.manual ? '  (sửa tay)' : '  (theo lệnh)') : '-';
  $('mf-on').checked = !!m.manual; $('mf-on').disabled = mfgLocked; $('mf-save').disabled = mfgLocked;
  $('mf-date').value = toIso(m.manual ? m.date : m.order_date) || new Date().toISOString().slice(0, 10);
  const h = $('mf-hint');
  h.textContent = !m.has_order ? 'Chưa có lệnh sản xuất trên bàn: ngày sản xuất chỉ sửa được cho lệnh đã về bàn.'
    : m.locked ? 'Lệnh này đã định danh thùng / pallet: không sửa được ngày sản xuất nữa.'
    : 'Tích “Sửa ngày sản xuất” rồi chọn ngày để in lên tem. Bỏ tích = in theo lệnh. Lệnh mới về bàn luôn lấy ngày theo lệnh.';
  h.classList.toggle('bad', !!(m.has_order && m.locked));
  mfgUi();
}
async function loadMfg() { const r = await api('/api/mfg'); if (r.ok) showMfg(r.mfg); }
async function saveMfg() {
  const on = $('mf-on').checked, d = fromIso(val('mf-date'));
  if (on && !d) return alertBox('Chọn ngày sản xuất.', 'LỖI');
  if (!(await confirmBox(on ? `In ngày sản xuất ${d} cho lệnh ${$('mf-po').textContent}?` : 'In ngày sản xuất theo lệnh?', 'Ngày sản xuất', 'Yes', 'No'))) return;
  const r = await api('/api/mfg', { enabled: on, date: d });
  if (!r.ok) { await alertBox(r.error, 'LỖI'); return loadMfg(); }
  showMfg(r.mfg);
  alertBox('Đã lưu. Tem in ra ngày ' + r.mfg.effective + '.');
}

// ---------- thẻ Thông số: bố cục và nút như phần mềm cũ ----------
const PEND_COLS = [['inner_pallet', 'Inner_Pallet'], ['pallet_id', 'Pallet_ID'], ['item_code', 'Item_Code'], ['item_name', 'Item_Name'], ['po', 'PO_Name'],
  ['location', 'Location'], ['status', 'Status'], ['cartons', 'Thùng đạt'], ['mfg_date', 'MFG_Date'], ['wh_code', 'WH_Code'], ['line_id', 'Line_ID'], ['po_id', 'PO_ID'], ['created_at', 'CreatedAt']];
const DONE_COLS = PEND_COLS.concat([['done_at', 'DoneAt'], ['done_reason', 'DoneReason'], ['ctn', 'Ctn'], ['qty', 'Qty'], ['pcs', 'Pcs']]);
const PARCEL_COLS = [['stt', 'STT'], ['code', 'Mã định danh'], ['text', 'Trạng thái'], ['mfg_date', 'Mfg_Date'], ['weight', 'Khối lượng (g)'], ['prints', 'Số lần in'], ['done_at', 'Thời gian']];
let ord = { pending: [], completed: [] }, selPend = '', selDone = null, lastSel = '', parcelsOf = null, ordTimer = null;
const selCodes = new Set();
function grid(id, cols, rows, isSel, empty) {
  $(id).innerHTML = `<tr>${cols.map(c => `<th>${esc(c[1])}</th>`).join('')}</tr>` + (rows.map((r, i) =>
    `<tr data-i="${i}" class="${isSel(r) ? 'sel' : ''}">${cols.map(c => `<td title="${esc(r[c[0]])}">${esc(r[c[0]])}</td>`).join('')}</tr>`).join('')
    || `<tr><td class="empty" colspan="${cols.length}">${empty}</td></tr>`);
}
function drawOrders() {
  grid('g-pending', PEND_COLS, ord.pending, r => r.pallet_id === selPend, 'Không có lệnh');
  grid('g-completed', DONE_COLS, ord.completed, r => !!selDone && r.key === selDone.key && r.pallet_id === selDone.pallet_id, 'Không có dữ liệu');
}
function openOrders() {
  if (!$('h-from').value) { const d = new Date(), t = new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); $('h-from').value = t; $('h-to').value = t; }
  loadOrders();
  clearInterval(ordTimer);
  ordTimer = setInterval(() => { if (tab === 'info' && $('modal').classList.contains('hidden')) loadOrders(); }, 5000);
}
async function loadOrders() {
  const r = await api(`/api/orders?from=${val('h-from')}&to=${val('h-to')}&pallet=${encodeURIComponent(val('h-pallet'))}&po=${encodeURIComponent(val('h-po'))}`);
  if (!r.ok) return;
  ord = r;
  if (selPend && !ord.pending.some(x => x.pallet_id === selPend)) selPend = '';
  $('st-active').textContent = r.stats.active; $('st-passed').textContent = r.stats.passed; $('st-cartons').textContent = r.stats.cartons;
  drawOrders();
  if (parcelsOf) loadParcels(true);
}
$('g-pending').onclick = e => { const tr = e.target.closest('tr[data-i]'); if (!tr) return; selPend = ord.pending[tr.dataset.i].pallet_id; lastSel = 'pending'; drawOrders(); };
$('g-completed').onclick = e => {
  const tr = e.target.closest('tr[data-i]'); if (!tr) return;
  const r = ord.completed[tr.dataset.i];
  selDone = { pallet_id: r.pallet_id, key: r.key, inner: r.inner_pallet }; lastSel = 'completed'; drawOrders();
};
$('g-pending').ondblclick = $('g-completed').ondblclick = () => loadParcels();
['h-pallet', 'h-po'].forEach(id => $(id).onkeydown = e => { if (e.key === 'Enter') loadOrders(); });
const curPend = () => selPend || (ord.pending[0] || {}).pallet_id || '';   // không chọn = pallet đang làm
async function opDone(r, okText, failText) {
  await alertBox(r.ok ? okText : (failText ? failText + '\n' : '') + r.error, r.ok ? 'THÔNG BÁO' : (r.title || 'LỖI'));
  loadOrders();
}
async function pdfCurrent() {
  const pid = curPend();
  if (!pid) return alertBox('Chưa có mã pallet hiện tại.');
  if (!(await confirmBox(`Bạn có chắc muốn in toàn bộ mã pallet ${pid} không?\nTrang tem mở ở thẻ mới: chọn máy in, hoặc "Lưu dưới dạng PDF" để lưu file.`, 'In PDF mã hiện tại', 'Yes', 'No'))) return;
  window.open('/labels?pallet=' + encodeURIComponent(pid), '_blank');
}
async function fakeComplete() {
  const pid = curPend();
  if (!pid) return alertBox('Chưa có lệnh sản xuất đang chạy.');
  if (!(await needPass()) || !(await confirmBox(`Bạn có chắc muốn gửi thành công pallet ${pid} (ảo)?\nPallet được tính là đã định danh, KHÔNG gửi gì lên server.`, 'Thành công ảo', 'Yes', 'No'))) return;
  opDone(await api('/api/orders/fake_complete', { pallet_id: pid }), 'Gửi thành công thông tin ảo định danh pallet!', 'Gửi không thành công thông tin ảo định danh pallet!');
}
async function pullNext() {
  if (!(await confirmBox('BẠN CÓ CHẮC CHẮN TẢI LỆNH TIẾP THEO KHÔNG?', 'THÔNG BÁO', 'Yes', 'No'))) return;
  const r = await api('/api/orders/pull_next', {});
  opDone(r, 'Đã tải lệnh: pallet ' + r.pallet_id);
}
async function deleteTask() {
  const pid = curPend();
  if (!pid) return alertBox('Chưa có lệnh sản xuất đang chạy.');
  if (!(await needPass()) || !(await confirmBox(`Bạn muốn xóa lệnh đang làm (pallet ${pid}) đúng không?\nPallet chuyển xuống bảng LỆNH ĐÃ HOÀN THÀNH (ĐÃ XÓA), làm lại được bằng nút Thực hiện lại.`, 'Xóa lệnh đang làm', 'Yes', 'No'))) return;
  opDone(await api('/api/orders/delete', { pallet_id: pid }), 'Đã xóa lệnh pallet ' + pid);
}
async function sendIdentify() {
  const pid = curPend();
  if (!pid) return alertBox('Chưa có lệnh sản xuất đang chạy.');
  opDone(await api('/api/identify', { pallet_id: pid }), 'Gửi thành công thông tin định danh pallet!', 'Gửi không thành công thông tin định danh pallet!');
}
async function reloadTask() {
  if (!selDone) return alertBox('Vui lòng chọn một lệnh ở bảng LỆNH ĐÃ HOÀN THÀNH.');
  if (!(await needPass()) || !(await confirmBox(`Bạn có chắc chắn muốn reload lệnh sản xuất này không?\n\nPallet_ID: ${selDone.pallet_id}\nInner_Pallet: ${selDone.inner}`, 'Thực hiện lại', 'Yes', 'No'))) return;
  opDone(await api('/api/reload', { pallet_id: selDone.pallet_id }), 'Reload pallet từ lịch sử thành công.');
}
async function loadParcels(quiet) {
  if (!quiet) {
    if (lastSel === 'pending' && selPend) parcelsOf = { pallet_id: selPend, key: '' };
    else if (lastSel === 'completed' && selDone) parcelsOf = { pallet_id: selDone.pallet_id, key: selDone.key };
    else return alertBox('Vui lòng chọn một lệnh (pallet) trước khi tải mã định danh.');
    selCodes.clear();
  }
  const r = await api(`/api/orders/parcels?pallet=${encodeURIComponent(parcelsOf.pallet_id)}&key=${parcelsOf.key}`);
  if (!r.ok) {
    if (quiet) return;                     // pallet vừa chuyển sang lịch sử: giữ bảng cũ
    parcelsOf = null;
    return alertBox(r.error);
  }
  parcelsOf.item = r.item; parcelsOf.rows = r.rows;
  $('ps-total').textContent = `Tổng số thùng trong pallet: ${r.done} / ${r.total}`;
  $('ps-pallet').textContent = '— ' + r.pallet_id;
  const all = r.rows.length > 0 && r.rows.every(x => selCodes.has(x.code));
  $('g-parcels').innerHTML = `<tr><th><input type="checkbox" id="ps-all" ${all ? 'checked' : ''} title="Chọn tất cả"></th>${PARCEL_COLS.map(c => `<th>${c[1]}</th>`).join('')}</tr>` +
    (r.rows.map((x, i) => `<tr data-i="${i}" class="${selCodes.has(x.code) ? 'sel' : ''}"><td><input type="checkbox" ${selCodes.has(x.code) ? 'checked' : ''}></td>${PARCEL_COLS.map(c => `<td>${esc(x[c[0]])}</td>`).join('')}</tr>`).join('')
      || `<tr><td class="empty" colspan="8">Không có thùng</td></tr>`);
}
$('g-parcels').onclick = e => {
  if (!parcelsOf || !parcelsOf.rows) return;
  if (e.target.id === 'ps-all') { if (e.target.checked) parcelsOf.rows.forEach(x => selCodes.add(x.code)); else selCodes.clear(); }
  else {
    const tr = e.target.closest('tr[data-i]'); if (!tr) return;
    const c = parcelsOf.rows[tr.dataset.i].code;
    if (selCodes.has(c)) selCodes.delete(c); else selCodes.add(c);
  }
  loadParcels(true);
};
async function reprintCodes() {
  if (!parcelsOf || !selCodes.size) return alertBox('Vui lòng chọn một thùng (parcel) để in lại.');
  const codes = [...selCodes];
  if (!(await needPass()) || !(await confirmBox(codes.length === 1 ? `In lại tem thùng ${codes[0]}?` : `In lại ${codes.length} tem của pallet ${parcelsOf.pallet_id}?`, 'In lại mã định danh', 'Yes', 'No'))) return;
  const r = await api('/api/reprint_pallet', { pallet_id: parcelsOf.pallet_id, codes });
  if (!r.ok) return alertBox('In lại tem thất bại: ' + r.error, 'LỖI');
  // In chạy nền (bấm Dừng để hủy); chờ xong rồi báo kết quả như bản cũ.
  let j = null;
  for (let t = 0; t < 1200; t++) {
    await new Promise(ok => setTimeout(ok, 500));
    j = state && state.job;
    if (j && j.id === r.job && !j.active) break;
  }
  if (!j || j.active) return;
  if (j.error) alertBox(`In lại tem thất bại: ${j.error} (${j.done}/${j.total})`, 'LỖI');
  else if (j.cancelled) alertBox(`Đã hủy in lại (${j.done}/${j.total}).`);
  else alertBox(r.total === 1 ? `In lại tem thành công: ${codes[0]} với mã hàng: ${parcelsOf.item}` : `In lại tem thành công: ${j.done} tem của pallet ${r.pallet_id}.`);
  loadParcels(true);
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
