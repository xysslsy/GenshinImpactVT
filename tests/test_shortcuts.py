import ctypes
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication,QWidget,QCheckBox,QComboBox,QLabel
from genshinimpactvt.shortcuts import ACTIONS,parse_binding,validate_bindings,Shortcuts,KeyboardHook,SystemKeys
from genshinimpactvt.episode_keys import KeyData


class ShortcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def test_defaults_and_modifiers(self):
        bindings=validate_bindings({key:default for key,(_,default) in ACTIONS.items()})
        self.assertEqual(bindings['forward'].vk,0x36)
        self.assertEqual(bindings['controls'].vk,0x78)
        self.assertIsNone(bindings['pause'])
        combo=parse_binding('Ctrl+Alt+K')
        self.assertEqual((combo.modifiers,combo.vk),(3,0x4b))

    def test_conflict_and_invalid_sequences(self):
        for values in ({'previous':'7','next':'7'},{'pause':'Ctrl+K, Ctrl+P'},
                       {'controls':'F12'},{'visible':'Alt+F4'},{'pause':'未知键'}):
            with self.assertRaises(ValueError): validate_bindings(values)

    def test_hook_repeat_modifiers_and_injected_filter(self):
        parent=QWidget(); hook=KeyboardHook(parent); actions=[]; hook.pressed.connect(actions.append)
        hook.bindings={(0,0x36):'forward',(2,0x4b):'pause'}
        data=KeyData(0x36,0,0,0,0)
        with patch('genshinimpactvt.shortcuts.user32.CallNextHookEx',return_value=123), patch('genshinimpactvt.shortcuts.user32.GetAsyncKeyState',return_value=0):
            self.assertEqual(hook._hook(0,0x100,ctypes.addressof(data)),123)
            hook._hook(0,0x100,ctypes.addressof(data))
            self.assertEqual(actions,['forward'])
            hook._hook(0,0x101,ctypes.addressof(data));data.flags=0x10
            hook._hook(0,0x100,ctypes.addressof(data));self.assertEqual(actions,['forward'])
            hook._hook(0,0x101,ctypes.addressof(data)); data.vkCode=0x4b;data.flags=0
            with patch('genshinimpactvt.shortcuts.user32.GetAsyncKeyState',side_effect=lambda vk:0x8000 if vk==0x11 else 0):
                hook._hook(0,0x100,ctypes.addressof(data))
            self.assertEqual(actions,['forward','pause'])
        parent.close()

    def test_system_registration_failure_releases_partial_set(self):
        system=SystemKeys(None)
        system.bindings=validate_bindings({'previous':'7','next':'8'})
        with patch('genshinimpactvt.shortcuts.user32.RegisterHotKey',side_effect=[1,0]), patch('genshinimpactvt.shortcuts.user32.UnregisterHotKey') as release:
            self.assertFalse(system.start());self.assertFalse(system.active)
            self.assertFalse(system.registered);release.assert_called_once()
            self.assertIn('8',system.error)

    def test_edit_save_restart_and_failed_apply_preserve_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            main=QWidget(); main.settings=QSettings(str(Path(temp)/'settings.ini'),QSettings.Format.IniFormat)
            main.episode_toggle=QCheckBox();main.episode_toggle.setChecked(True)
            main.episode_mode=QComboBox();main.episode_mode.addItem('hook','hook');main.episode_status=QLabel()
            actions=[];main.media_action=actions.append
            manager=Shortcuts(main)
            with patch.object(manager.hook,'start',return_value=True):
                manager.page.begin();manager.dispatch('forward');self.assertEqual(actions,[])
                values=dict(manager.values,forward='J',pause='P',controls='F7')
                manager.apply(values,{2:'forward',1:'pause'})
                manager.dispatch('forward');self.assertEqual(actions,['forward'])
                manager.page.cancel()
                restored=Shortcuts(main)
                self.assertEqual(restored.values['forward'],'J');self.assertEqual(restored.mouse[2],'forward')
                with patch.object(manager.hook,'start',return_value=False):
                    with self.assertRaises(ValueError): manager.apply(dict(values,forward='L'),{2:'back',1:''})
                self.assertEqual(manager.values['forward'],'J')
                self.assertEqual(main.settings.value('shortcuts/forward'),'J')
                self.assertTrue(manager.suspended)
                manager.stop();restored.stop()
            manager.page.close();restored.page.close();main.close()


if __name__=='__main__': unittest.main()
