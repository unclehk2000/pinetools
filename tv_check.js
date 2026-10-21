// TradingView light compile check (type and scope errors) for any number of .pine files, no account needed.
// 1. Open https://www.tradingview.com/robots.txt (any tradingview.com page works; this one is light).
// 2. Open the browser console (F12 → Console) and paste this whole file.
// 3. Click the file picker that appears, choose your .pine files, then run:  await chk()
// It POSTs each file to the editor's own light-compile endpoint as Guest and prints errors and warnings.
// It does NOT check the size limits (CE10117 / CE10295 / CE10205) or CE10116 / CE10237: run pine_size.py and
// pine_limits.py for those.
document.body.innerHTML = '<input type="file" id="pf" multiple accept=".pine,.txt">';
window.chk = async () => {
  const out = [];
  for (const f of document.getElementById('pf').files) {
    const fd = new FormData();
    fd.append('source', await f.text());
    const r = await fetch('https://pine-facade.tradingview.com/pine-facade/translate_light?user_name=Guest&pine_id=00000000-0000-0000-0000-000000000000',
      { method: 'POST', body: fd, credentials: 'omit' });
    const j = await r.json();
    const res = j.result || {};
    out.push({ file: f.name, success: j.success, errors: (res.errors2 || res.errors || []), warnings: (res.warnings2 || res.warnings || []), reason: j.reason });
  }
  console.table(out.map(o => ({ file: o.file, success: o.success, errors: o.errors.length, warnings: o.warnings.length })));
  return out;
};
'ready: choose files, then run  await chk()';
