/* Read normal platform captions using this WebView's session. No credential export. */
(() => {
  const token = TOKEN;
  const previous = window.__givtCaptionRecovery;
  if (previous && previous.abort) previous.abort.abort();
  const state = {token, done:false, result:null, abort:new AbortController()};
  window.__givtCaptionRecovery = state;
  const timer = setTimeout(() => state.abort.abort(), 18000);
  const limit = 4 * 1024 * 1024;
  const safeCaption = value => {
    const u = new URL(value, location.href);
    if (u.protocol !== 'https:' || u.username || u.password || (u.port && u.port !== '443') ||
        !(u.hostname === 'hdslb.com' || u.hostname.endsWith('.hdslb.com')) ||
        !/^\/bfs\/(ai_subtitle|subtitle)\//.test(u.pathname)) throw new Error('caption_host');
    return u.href;
  };
  const read = async (url, credentials, caption=false) => {
    const response = await fetch(url, {credentials, signal:state.abort.signal, cache:'no-store'});
    if (!response.ok) throw new Error('http_' + response.status);
    if (caption) safeCaption(response.url);
    if (Number(response.headers.get('Content-Length')) > limit) throw new Error('size');
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let size=0, text='';
    try {
      while (true) {
        const {value,done} = await reader.read(); if (done) break;
        size += value.byteLength;
        if (size > limit) { await reader.cancel(); throw new Error('size'); }
        text += decoder.decode(value,{stream:true});
      }
      text += decoder.decode(); return JSON.parse(text.replace(/^\uFEFF/,''));
    } finally { reader.releaseLock(); }
  };
  (async () => {
    try {
      const url = new URL(location.href);
      if (url.protocol !== 'https:' || !(url.hostname === 'bilibili.com' || url.hostname.endsWith('.bilibili.com'))) throw new Error('page');
      const bvid = url.pathname.match(/\/video\/(BV[0-9A-Za-z]{10})(?:\/|$)/)?.[1] || url.searchParams.get('bvid');
      if (!/^BV[0-9A-Za-z]{10}$/.test(bvid || '')) throw new Error('page');
      const page = Math.max(1,Number(url.searchParams.get('p') || 1));
      const view = await read('https://api.bilibili.com/x/web-interface/view?bvid='+encodeURIComponent(bvid),'include');
      if (view.code !== 0) { state.result={status:'platform',code:view.code}; return; }
      const aid = view.data?.aid;
      let cid = url.hostname === 'player.bilibili.com' ? url.searchParams.get('cid') : '';
      if (!cid) {
        cid = view.data?.pages?.find(item => Number(item.page) === page)?.cid;
      }
      if (!/^\d+$/.test(String(cid || ''))) throw new Error('identity');
      const key={bvid,cid:String(cid),page};
      // Reuse a matching request already made by the real player. Never construct a WBI signature.
      const observed = performance.getEntriesByType('resource').slice(-300).reverse().map(item => {
        try { return new URL(item.name); } catch { return null; }
      }).find(u => u && u.hostname==='api.bilibili.com' && u.pathname==='/x/player/wbi/v2' &&
        u.searchParams.get('cid')===String(cid) &&
        ((aid && u.searchParams.get('aid')===String(aid)) || u.searchParams.get('bvid')===bvid));
      const ordinary = 'https://api.bilibili.com/x/player/v2?aid='+encodeURIComponent(aid)+'&cid='+encodeURIComponent(cid)+'&bvid='+encodeURIComponent(bvid);
      let player;
      if (observed) {
        try { player=await read(observed.href,'include'); } catch {}
      }
      if (!player || player.code!==0) player=await read(ordinary,'include');
      if (player.code !== 0) { state.result={status:'platform',code:player.code,key}; return; }
      if ((player.data?.cid && String(player.data.cid) !== String(cid)) ||
          (player.data?.bvid && player.data.bvid !== bvid)) throw new Error('identity');
      if (player.data?.need_login_subtitle) { state.result={status:'login',key}; return; }
      const tracks = player.data?.subtitle?.subtitles;
      const rank = t => /^(zh|zh-CN|zh-Hans)$/.test(t.lan) ? 0 : /^ai-zh/.test(t.lan) ? 1 : /zh/.test(t.lan) ? 2 : 3;
      const valid = (Array.isArray(tracks) ? tracks.slice(0,30) : []).filter(t => {
        try { safeCaption(t.subtitle_url); return true; } catch { return false; }
      }).sort((a,b) => rank(a)-rank(b));
      if (!valid.length) { state.result={status:'no_tracks',key}; return; }
      const track=valid[0], caption=await read(safeCaption(track.subtitle_url),'omit',true);
      state.result={status:'ok',key,label:String(track.lan_doc || track.lan || '字幕').slice(0,60),caption};
    } catch (error) {
      state.result={status:'error',reason:error.name === 'AbortError' ? 'timeout' : String(error.message).slice(0,60)};
    } finally {
      clearTimeout(timer); state.done=true;
    }
  })();
  return true;
})()
