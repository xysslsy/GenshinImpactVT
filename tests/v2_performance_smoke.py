"""Source-startup and isolated process-tree observations, not a full Bilibili benchmark."""
import time
START=time.perf_counter()
import ctypes,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
DATA=ROOT/'.test-v2/performance';DATA.mkdir(parents=True,exist_ok=True);os.environ['LOCALAPPDATA']=str(DATA)
import psutil
from PySide6.QtCore import QSettings,QTimer
from PySide6.QtWidgets import QApplication
from main import Main

def main():
    settings=QSettings(str(DATA/'app/settings.ini'),QSettings.Format.IniFormat);settings.clear()
    for key in ('mouse/enabled','episode_keys/enabled'):settings.setValue(key,False)
    settings.setValue('subtitles/enabled',True)
    settings.sync();ole=ctypes.OleDLL('ole32');ole.OleInitialize(None);app=QApplication([]);win=Main(DATA/'app')
    observations={};errors=[]
    win.browser.ready.connect(lambda:observations.update(source_browser_ready_seconds=round(time.perf_counter()-START,3)))
    def sample():
        own=psutil.Process();processes=[own]+own.children(recursive=True);cpu=0;browser=0
        for process in processes:
            try:
                times=process.cpu_times();cpu+=times.user+times.system
                if process.pid!=own.pid:browser+=process.memory_info().rss
            except psutil.Error:pass
        return {'main_rss_mib':round(own.memory_info().rss/1024**2,1),'child_rss_mib':round(browser/1024**2,1),'processes':len(processes),'cpu_seconds':cpu,'wall':time.perf_counter()}
    def delay(seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:yield
    def js(script):
        task=win.browser.execute_script(script)
        while not task.IsCompleted:yield
        return task.Result
    def steps():
        yield from delay(5);first=sample();yield from delay(2);idle=sample()
        idle['one_core_cpu_percent']=round((idle['cpu_seconds']-first['cpu_seconds'])/(idle['wall']-first['wall'])*100,2)
        yield from js("document.querySelector('video').play();true")
        first=sample();yield from delay(2);playing=sample()
        playing['one_core_cpu_percent']=round((playing['cpu_seconds']-first['cpu_seconds'])/(playing['wall']-first['wall'])*100,2)
        for row in (idle,playing):row.pop('cpu_seconds');row.pop('wall')
        observations.update(local_idle=idle,synthetic_video_playing=playing)
    it=steps()
    def tick():
        try:
            if time.perf_counter()-START>25:raise TimeoutError('performance timeout')
            next(it);return
        except StopIteration:pass
        except Exception as exc:errors.append(str(exc))
        timer.stop();win.close()
    timer=QTimer();timer.timeout.connect(tick);timer.start(50);app.exec();ole.OleUninitialize()
    observations['errors']=errors;(DATA/'result.json').write_text(json.dumps(observations,indent=2),encoding='utf-8')
    print(json.dumps(observations),flush=True);return 1 if errors else 0
if __name__=='__main__':sys.exit(main())
