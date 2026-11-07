/* Read normal platform captions using this WebView's session. No credential export. */
(() => {
  const token = TOKEN, expected=EXPECTED;
  const captured=CAPTURED_RECORDS;
  const snapshot=MEDIA_CONTEXT, initial=snapshot();
  const logical=()=>{const u=new URL(location.href);return [u.pathname.match(/\/video\/(BV[0-9A-Za-z]{10})(?:\/|$)/)?.[1]||u.searchParams.get('bvid'),Math.max(1,Number(u.searchParams.get('p')||1)),u.hostname==='player.bilibili.com'?(u.searchParams.get('cid')||''):''];};
  const context=()=>{const m=snapshot();return m?{document:m.document,media:m.media,src:m.src,player_cid:m.playerCid}:null;};
  const initialContext=context();
  const stillCurrent=()=>JSON.stringify(logical())===JSON.stringify(expected)&&JSON.stringify(context())===JSON.stringify(initialContext);
  const finish=(status,extra={})=>({status,token,context:initialContext,...extra});
  const previous = window.__givtCaptionRecovery;
  if (previous && previous.abort) previous.abort.abort();
  const state = {token, done:false, result:null, abort:new AbortController()};
  window.__givtCaptionRecovery = state;
  const timer = setTimeout(() => state.abort.abort(), 20000);
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
      if(!initial||initial.ready<2||!initial.src||!stillCurrent()){state.result=finish('waiting');return;}
      const url = new URL(location.href);
      if (url.protocol !== 'https:' || !(url.hostname === 'bilibili.com' || url.hostname.endsWith('.bilibili.com'))) throw new Error('page');
      const bvid = url.pathname.match(/\/video\/(BV[0-9A-Za-z]{10})(?:\/|$)/)?.[1] || url.searchParams.get('bvid');
      if (!/^BV[0-9A-Za-z]{10}$/.test(bvid || '')) throw new Error('page');
      const page = Math.max(1,Number(url.searchParams.get('p') || 1));
      const view = await read('https://api.bilibili.com/x/web-interface/view?bvid='+encodeURIComponent(bvid),'include');
      if (view.code !== 0) { state.result=finish('platform',{message:'平台视频信息暂不可读（'+view.code+'）'}); return; }
      if(view.data?.bvid!==bvid)throw new Error('视频信息与当前 BVID 不一致');
      const aid = view.data?.aid;
      let cid = url.hostname === 'player.bilibili.com' ? url.searchParams.get('cid') : '';
      if (!cid) {
        cid = view.data?.pages?.find(item => Number(item.page) === page)?.cid;
      }
      if (!/^\d+$/.test(String(cid || ''))) throw new Error('identity');
      const key={bvid,cid:String(cid),aid:String(aid),page};
      if(initial.playerCid&&initial.playerCid!==String(cid)){state.result=finish('waiting',{key});return;}
      const duration=Number(view.data?.pages?.find(item=>String(item.cid)===String(cid))?.duration||0);
      if(duration&&initial.duration&&Math.abs(initial.duration-duration)>Math.max(5,duration*.015)){state.result=finish('waiting',{key});return;}
      // Reuse a matching request already made by the real player. Never construct a WBI signature.
      const observed = performance.getEntriesByType('resource').slice(-300).reverse().map(item => {
        try { return new URL(item.name); } catch { return null; }
      }).find(u => u && u.hostname==='api.bilibili.com' && u.pathname==='/x/player/wbi/v2' &&
        u.searchParams.get('cid')===String(cid) &&
        ((aid && u.searchParams.get('aid')===String(aid)) || u.searchParams.get('bvid')===bvid));
      let player=captured.find(record=>String(record.data?.aid)===String(aid)&&String(record.data?.cid)===String(cid));
      if (!player && observed) {
        try { player=await read(observed.href,'include'); } catch {}
      }
      // The unsigned legacy endpoint was observed returning unrelated tracks with matching IDs.
      // Never use it as a fallback. Only metadata actually offered to this player is eligible.
      if(!player){state.result=finish('metadata_pending',{key,message:'等待播放器字幕信息，可在 B站播放器开启字幕后重试'});return;}
      if (player.code !== 0) { state.result=finish('platform',{key,message:'平台字幕信息暂不可读（'+player.code+'）'}); return; }
      if(String(player.data?.cid||'')!==String(cid)||(player.data?.aid&&String(player.data.aid)!==String(aid))||
          (player.data?.bvid&&player.data.bvid!==bvid))throw new Error('字幕接口返回了其他视频，已拒绝');
      if (player.data?.need_login_subtitle) { state.result=finish('login',{key,message:'请在软件内登录 B站后重试'}); return; }
      const tracks = player.data?.subtitle?.subtitles;
      const rank = t => /^(zh|zh-CN|zh-Hans)$/.test(t.lan) ? 0 : /^ai-zh/.test(t.lan) ? 1 : /zh/.test(t.lan) ? 2 : 3;
      const valid = (Array.isArray(tracks) ? tracks.slice(0,30) : []).filter(t => {
        try { safeCaption(t.subtitle_url); return true; } catch { return false; }
      }).filter(t=>/zh/.test(String(t.lan))).sort((a,b) => rank(a)-rank(b));
      if (!valid.length) { state.result=finish('no_tracks',{key,message:'平台未提供可读的中文字幕'}); return; }
      const track=valid[0], caption=await read(safeCaption(track.subtitle_url),'omit',true);
      if(!stillCurrent()){state.result=finish('stale',{key,message:'播放实例已经变化，丢弃旧字幕'});return;}
      state.result=finish('ok',{key,verified:true,track_id:String(track.id_str||track.id||track.lan),label:String(track.lan_doc||track.lan||'中文字幕').slice(0,60),caption});
    } catch (error) {
      state.result=finish('error',{message:error.name==='AbortError'?'字幕请求超时':String(error.message).slice(0,100)});
    } finally {
      clearTimeout(timer); state.done=true;
    }
  })();
  return true;
})()
