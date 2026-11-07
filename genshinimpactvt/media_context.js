(() => {
  return () => {
    const bili=/(^|\.)bilibili\.com$/.test(location.hostname);
    let candidates=Array.from(document.querySelectorAll('.bpx-player-video-wrap video,.bilibili-player-video video'));
    if (!candidates.length && (!bili || location.hostname==='player.bilibili.com')) candidates=Array.from(document.querySelectorAll('video'));
    const video=candidates.map((element,index)=>{const r=element.getBoundingClientRect(),s=getComputedStyle(element);return {element,index,area:r.width*r.height,visible:r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity)!==0};})
      .filter(item=>item.visible).sort((a,b)=>b.area-a.area||b.index-a.index)[0]?.element;
    if (!video) return null;
    window.__givtDocumentId ||= crypto.randomUUID();
    video.__givtId ||= crypto.randomUUID();
    video.__givtEpoch ||= 0;
    if (!video.__givtBound) {
      video.__givtBound=true;
      video.addEventListener('seeking',()=>video.__givtEpoch++);
      video.addEventListener('emptied',()=>video.__givtEpoch++);
    }
    let playerCid='';
    try {
      const source=window.player?.getMediaInfo?.()?.playUrl;
      if (typeof source==='string') playerCid=source.match(/\/upgcxcode\/\d+\/\d+\/(\d+)(?:\/|$)/)?.[1] || '';
    } catch {}
    if (video.__givtCidSource!==video.currentSrc) {
      video.__givtCidSource=video.currentSrc;video.__givtCachedCid='';
    }
    if (playerCid) video.__givtCachedCid=playerCid;
    else playerCid=video.__givtCachedCid||'';
    return {element:video,document:window.__givtDocumentId,media:video.__givtId,
      src:video.currentSrc||'',playerCid,duration:Number.isFinite(video.duration)?video.duration:0,ready:video.readyState};
  };
})()
