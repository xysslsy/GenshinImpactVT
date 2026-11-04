"""Real WebView2 text-track -> controller -> visible footer, isolated profile."""
import ctypes,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    data=ROOT/'.test-footer';data.mkdir(exist_ok=True);os.environ['LOCALAPPDATA']=str(data)
    from PySide6.QtCore import QTimer,QSettings
    from PySide6.QtWidgets import QApplication
    from main import Main,STYLE
    settings=QSettings(str(data/'app'/'settings.ini'),QSettings.Format.IniFormat)
    for key in ('mouse/enabled','episode_keys/enabled','subtitles/enabled'):settings.setValue(key,False)
    settings.setValue('browser/last_url','');settings.setValue('subtitles/show_footer',True);settings.sync()
    ole=ctypes.OleDLL('ole32');ole.OleInitialize(None);app=QApplication([]);app.setStyleSheet(STYLE)
    win=Main(data/'app');checks={}
    def start():
        s=win.subtitles;s.page.mode.setCurrentIndex(s.page.mode.findData('dom'));s.page.enabled.setChecked(True)
        win.browser.execute_script("(()=>{let v=document.querySelector('video');let t=v.addTextTrack('subtitles','local-test','zh');t.mode='hidden';t.addCue(new VTTCue(0,10,'往东北方向走，沿着道路继续前进'));v.currentTime=.5;v.pause()})()")
        QTimer.singleShot(1400,inspect)
    def inspect():
        checks['browser_caption_in_footer']='往东北方向走' in win.subtitle_strip.current
        checks['footer_visible']=win.subtitle_strip.isVisible()
        win.grab().save(str(data/'footer-preview.png'))
        win.toggle_immersive();checks['immersive_keeps_subtitles']=win.subtitle_strip.isVisible()
        win.toggle_immersive();win.subtitles.page.show_footer.setChecked(False)
        checks['hide_switch']=not win.subtitle_strip.isVisible()
        win.subtitles.page.show_footer.setChecked(True);win.subtitles.page.enabled.setChecked(False)
        checks['disable_clears']=not win.subtitle_strip.current
        checks['visibility_saved']=win.settings.value('subtitles/show_footer',False,type=bool)
        win.close()
    QTimer.singleShot(4500,start);QTimer.singleShot(12000,app.quit);app.exec();ole.OleUninitialize()
    (data/'result.json').write_text(json.dumps(checks,indent=2),encoding='utf-8');print(json.dumps(checks),flush=True)
    return 0 if len(checks)==6 and all(checks.values()) else 1


if __name__=='__main__':sys.exit(main())
