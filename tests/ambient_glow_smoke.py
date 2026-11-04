"""Real Qt fade timing and settings integration; local page, isolated data."""
import ctypes,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    data=ROOT/'.test-glow';data.mkdir(exist_ok=True);os.environ['LOCALAPPDATA']=str(data)
    from PySide6.QtCore import QTimer,QSettings,Qt,QAbstractAnimation
    from PySide6.QtGui import QImage,QPainter,QColor,QFont
    from PySide6.QtWidgets import QApplication
    from main import Main,STYLE
    from genshinimpactvt.compass import Compass,ambient_position
    settings=QSettings(str(data/'app'/'settings.ini'),QSettings.Format.IniFormat)
    for key in ('mouse/enabled','episode_keys/enabled','subtitles/enabled'):settings.setValue(key,False)
    settings.setValue('compass/enabled',True);settings.setValue('browser/last_url','');settings.sync()
    ole=ctypes.OleDLL('ole32');ole.OleInitialize(None);app=QApplication([]);app.setStyleSheet(STYLE)
    win=Main(data/'app');result={}
    # Contact sheet is a rendering reference, not a capture of a game.
    sheet=QImage(1120,560,QImage.Format.Format_ARGB32_Premultiplied);sheet.fill(QColor('#19212d'))
    painter=QPainter(sheet);painter.setFont(QFont('Microsoft YaHei UI',13));painter.setPen(QColor('white'))
    preview=Compass();preview.show()
    for n,label in enumerate(('北','东北','东','东南','南','西南','西','西北')):
        preview.set_text('向'+label+'走');preview.animation.setCurrentTime(preview.animation.duration())
        image=QImage(240,240,QImage.Format.Format_ARGB32_Premultiplied);image.fill(Qt.GlobalColor.transparent);preview.render(image)
        x,y=(n%4)*280,(n//4)*280;painter.drawImage(x+20,y+4,image)
        painter.drawText(x,y+248,280,28,Qt.AlignmentFlag.AlignCenter,label)
    painter.end();sheet.save(str(data/'ambient-preview.png'));preview.close()
    win.glow_strength.setValue(90);win.glow_size.setValue(300);win.settings.sync()
    def start():
        win.subtitles.deliver('往东北方向走','platform')
        QTimer.singleShot(350,hold)
        QTimer.singleShot(5200,fade)
        QTimer.singleShot(5800,finish)
    def hold():
        c=win.compass
        result['northeast_active']=c.active=={'东','北'}
        result['hold_has_no_animation']=c.animation.state()==QAbstractAnimation.State.Stopped
        result['size_and_strength']=c.width()==300 and abs(c.strength-.9)<.001
        win.grab().save(str(data/'main-preview.png'))
    def fade():
        c=win.compass;result['actual_fade_out']=c._phase=='out' and 0<c._opacity<1
    def finish():
        c=win.compass
        result['expires_and_stops']=not c.active and not c.expiry.isActive() and c.animation.state()==QAbstractAnimation.State.Stopped
        read=QSettings(str(data/'app'/'settings.ini'),QSettings.Format.IniFormat)
        result['settings_saved']=read.value('compass/glow_size',type=int)==300 and read.value('compass/glow_strength',type=int)==90
        win.close();app.quit()
    QTimer.singleShot(1000,start);QTimer.singleShot(8000,app.quit);app.exec();ole.OleUninitialize()
    (data/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
    return 0 if len(result)==6 and all(result.values()) else 1


if __name__=='__main__':sys.exit(main())
