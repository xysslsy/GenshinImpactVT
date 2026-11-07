"""Isolated real WebView2 with synthetic HTTP responses and delayed stale replies.

Every web request is answered locally. No account/session of the real website is used.
"""
import ctypes,json,os,sys,time
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
DATA=ROOT/'.test-v2/chaos';DATA.mkdir(parents=True,exist_ok=True);os.environ['LOCALAPPDATA']=str(DATA)
from PySide6.QtCore import QSettings,QTimer
from PySide6.QtWidgets import QApplication
from main import Main

BV='BV1CMHQzsEJV';OTHER='BV1xx411c7mD'

def main():
    settings=QSettings(str(DATA/'app/settings.ini'),QSettings.Format.IniFormat);settings.clear()
    for key in ('mouse/enabled','episode_keys/enabled'):settings.setValue(key,False)
    settings.setValue('subtitles/enabled',True);settings.sync()
    ole=ctypes.OleDLL('ole32');ole.OleInitialize(None);app=QApplication([])
    started=time.monotonic();win=Main(DATA/'app');feed=win.subtitles.native_feed
    checks={};errors=[];streams=[];captions=[];counts={'bad_metadata':0,'caption':0,'legacy':0};late={'armed':False,'pending':False,'delivered':False}
    win.subtitles.caption_changed.connect(lambda text,source:captions.append(text))
    def cid_for(bvid,page):return str((100000 if bvid==BV else 200000)+page)
    def reply(event,body,mime='application/json'):
        from System import Array,Byte
        from System.IO import MemoryStream
        raw=body.encode('utf-8');stream=MemoryStream(Array[Byte](raw));streams.append(stream)
        headers='Content-Type: '+mime+'; charset=utf-8\r\nAccess-Control-Allow-Origin: https://www.bilibili.com\r\nAccess-Control-Allow-Credentials: true\r\nCache-Control: no-store\r\n'
        event.Response=win.browser.web.CoreWebView2.Environment.CreateWebResourceResponse(stream,200,'OK',headers)
    def request(sender,event):
        p=urlsplit(str(event.Request.Uri));q=parse_qs(p.query)
        try:
            if p.hostname=='www.bilibili.com' and p.path.startswith('/video/'):
                bvid=p.path.split('/')[2];page=int(q.get('p',['1'])[0]);cid=cid_for(bvid,page)
                html='''<html><style>html,body{margin:0}video{width:640px;height:360px}</style><div class="bpx-player-container"><div class="bpx-player-video-wrap"><video muted loop playsinline></video></div><span class="bpx-player-subtitle-item-text">全局污染字幕，往西串线</span></div><script>
                window.__INITIAL_STATE__={bvid:'BV9999999999',cid:999999};
                window.player={getMediaInfo:()=>({playUrl:'https://media.test/upgcxcode/01/02/CID/CID-1-30280.m4s'})};
                // Simulate the player's own metadata requests. Erase resource timing
                // to require native response capture rather than a timing replay.
                const metadata=()=>fetch('https://api.bilibili.com/x/player/wbi/v2?aid=AID&cid=CID',{credentials:'include'}).then(r=>r.json()).then(()=>performance.clearResourceTimings());
                metadata();setTimeout(metadata,900);
                const c=document.createElement('canvas');c.width=640;c.height=360;const x=c.getContext('2d');let n=0;
                const painting=setInterval(()=>{x.fillStyle=n++%2?'red':'blue';x.fillRect(0,0,640,360)},50);
                const stream=c.captureStream(20),r=new MediaRecorder(stream),chunks=[];
                r.ondataavailable=e=>chunks.push(e.data);r.onstop=()=>{clearInterval(painting);stream.getTracks().forEach(t=>t.stop());let v=document.querySelector('video');v.src=URL.createObjectURL(new Blob(chunks,{type:r.mimeType}));v.play()};r.start();setTimeout(()=>r.stop(),600);
                </script></html>'''.replace('CID',cid).replace('AID',str(123 if bvid==BV else 456))
                reply(event,html,'text/html')
            elif p.hostname=='api.bilibili.com' and p.path=='/x/web-interface/view':
                bvid=q['bvid'][0]
                reply(event,json.dumps({'code':0,'data':{'bvid':bvid,'aid':123 if bvid==BV else 456,'pages':[{'page':page,'cid':int(cid_for(bvid,page)),'duration':1} for page in (1,2)]}}))
            elif p.hostname=='api.bilibili.com' and p.path=='/x/player/wbi/v2':
                cid=q['cid'][0];aid=int(q['aid'][0]);bad=counts['bad_metadata']==0
                counts['bad_metadata']+=1
                reply(event,json.dumps({'code':0,'data':{'aid':aid,'cid':999999 if bad else int(cid),'subtitle':{'subtitles':[{'id_str':'track-'+cid,'lan':'ai-zh','subtitle_url':'https://aisubtitle.hdslb.com/bfs/ai_subtitle/'+cid+'.json'}]}}}))
            elif p.hostname=='api.bilibili.com' and p.path=='/x/player/v2':
                # Status, aid and cid all look valid; the CONTENT is unrelated.
                counts['legacy']+=1
                reply(event,json.dumps({'code':0,'data':{'aid':int(q['aid'][0]),'cid':int(q['cid'][0]),'subtitle':{'subtitles':[{'id_str':'unrelated','lan':'ai-zh','subtitle_url':'https://aisubtitle.hdslb.com/bfs/ai_subtitle/hotpot.json'}]}}}))
            elif p.hostname=='aisubtitle.hdslb.com':
                counts['caption']+=1;cid=p.path.rsplit('/',1)[1].split('.')[0]
                text='男士在火锅店吃饭' if cid=='hotpot' else '向北正确字幕' if cid=='100001' else '向南正确字幕' if cid=='100002' else '向东新视频字幕'
                if late['armed'] and cid=='100001':
                    late['armed']=False;late['pending']=True;defer=event.GetDeferral()
                    def finish():
                        try:reply(event,json.dumps({'body':[{'from':0,'to':.55,'content':'向西旧回包串线'}]}));late['delivered']=True
                        finally:defer.Complete()
                    QTimer.singleShot(1800,finish)
                else:reply(event,json.dumps({'body':[{'from':0,'to':.55,'content':text}]}))
            else:reply(event,'{}')
        except Exception as exc:errors.append('handler: '+str(exc));reply(event,'{}')
    def attached():
        from Microsoft.Web.WebView2.Core import CoreWebView2WebResourceContext
        core=win.browser.web.CoreWebView2;core.AddWebResourceRequestedFilter('*',CoreWebView2WebResourceContext.All)
        core.WebResourceRequested+=request
        check('browser_ready_under_five_seconds',time.monotonic()-started<5)
        win.open_url('https://www.bilibili.com/video/'+BV+'/?p=1')
    win.browser.ready.connect(attached)
    def check(name,value):checks[name]=bool(value);print(name,bool(value),flush=True)
    def wait_for(predicate,seconds=18):
        deadline=time.monotonic()+seconds
        while not predicate():
            if time.monotonic()>deadline:raise TimeoutError('condition: '+feed.message)
            yield
    def delay(seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:yield
    def steps():
        yield from wait_for(lambda:bool(feed.timeline.cues))
        check('wrong_metadata_rejected_then_retried',counts['bad_metadata']>=2 and feed.video_key==(BV,'100001'))
        yield from wait_for(lambda:any('正确字幕' in text for text in captions))
        check('unverified_dom_never_overrides_platform',not any('全局污染' in text for text in captions))
        late['armed']=True;win.subtitles.refresh_subtitles()
        yield from wait_for(lambda:late['pending'])
        win.open_url('https://www.bilibili.com/video/'+BV+'/?p=2')
        yield from wait_for(lambda:feed.video_key==(BV,'100002'))
        yield from wait_for(lambda:late['delivered'])
        check('late_old_part_never_displays',not any('旧回包串线' in text for text in captions))
        check('current_part_stays_bound',feed.video_key==(BV,'100002') and feed._context['player_cid']=='100002')
        for _ in range(4):win.subtitles.refresh_subtitles()
        yield from wait_for(lambda:feed.video_key==(BV,'100002'))
        check('rapid_refresh_keeps_correct_part',all('串线' not in c for c in captions))
        win.open_url('https://www.bilibili.com/video/'+OTHER+'/?p=1')
        yield from wait_for(lambda:feed.video_key==(OTHER,'200001'))
        yield from wait_for(lambda:any('新视频字幕' in text for text in captions))
        check('different_video_loads_without_old_caption',feed.text_at(.1)=='向东新视频字幕')
        check('new_document_and_media_are_bound',feed._loaded_context==feed.signature(feed._context) and feed._loaded_page[0]==OTHER)
        yield from delay(.5)
        check('successful_loader_is_idle',not feed.timer.isActive())
        check('legacy_endpoint_never_requested',counts['legacy']==0)
        check('same_ids_foreign_content_never_displays',not any('火锅' in text for text in captions))
        check('native_metadata_survives_missing_resource_timing',bool(feed.captured_records()))
    it=steps()
    def tick():
        try:
            if time.monotonic()-started>65:raise TimeoutError('chaos test timeout')
            next(it);return
        except StopIteration:pass
        except Exception as exc:errors.append(str(exc));print(errors[-1],flush=True)
        timer.stop();win.close()
    timer=QTimer();timer.timeout.connect(tick);timer.start(50);app.exec();ole.OleUninitialize()
    result={'checks':checks,'errors':errors};(DATA/'result.json').write_text(json.dumps(result),encoding='utf-8')
    print(json.dumps(result),flush=True)
    return 0 if len(checks)==12 and all(checks.values()) and not errors else 1
if __name__=='__main__':sys.exit(main())
