import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from genshinimpactvt.uninstaller import (MARKER,load_install,remove_owned_files,
    plain_path,purge_user_data,wait_for_app)
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QWidget,QMessageBox


class UninstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.root=self.base/'GenshinImpactVT'
        self.root.mkdir()
        self.files={'GenshinImpactVT.exe':b'not executable: test fixture',
                    'Uninstall.exe':b'not executable: test helper',
                    '_internal/nested/runtime.dll':b'fixture library','README.md':b'fixture readme'}
        for name,content in self.files.items():
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
        self.manifest={'product':'GenshinImpactVT','schema':1,'files':{
            name:hashlib.sha256(content).hexdigest() for name,content in self.files.items()}}
        self.save()

    def save(self):
        (self.root/MARKER).write_text(json.dumps(self.manifest),encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def test_removes_owned_files_and_empty_directories(self):
        self.assertEqual(remove_owned_files(self.root,retry_seconds=0),[])
        self.assertFalse(self.root.exists())

    def test_preserves_extra_and_changed_files(self):
        note=self.root/'my-notes.txt';note.write_text('user notes')
        readme=self.root/'README.md';readme.write_text('edited by user')
        other=self.base/'previous-version';other.mkdir();(other/'keep').write_text('old version')
        self.assertEqual(remove_owned_files(self.root,retry_seconds=0),['README.md'])
        self.assertEqual(note.read_text(),'user notes')
        self.assertEqual(readme.read_text(),'edited by user')
        self.assertTrue((other/'keep').exists())

    def test_rejects_paths_outside_install_before_removing_anything(self):
        outside=self.base/'outside.txt';outside.write_bytes(b'keep')
        for path in ('../outside.txt','/outside.txt','C:/outside.txt','_internal/../../outside.txt','a\\b','./README.md'):
            with self.subTest(path=path):
                self.manifest['files'][path]=hashlib.sha256(b'keep').hexdigest();self.save()
                with self.assertRaises(ValueError):remove_owned_files(self.root,retry_seconds=0)
                self.assertTrue((self.root/'GenshinImpactVT.exe').exists())
                self.assertEqual(outside.read_bytes(),b'keep')
                del self.manifest['files'][path]

    def test_rejects_source_tree(self):
        (self.root/'.git').mkdir()
        with self.assertRaises(ValueError):load_install(self.root)
        self.assertTrue((self.root/'GenshinImpactVT.exe').exists())

    def test_rejects_link_or_junction_attributes(self):
        with patch.object(Path,'lstat',return_value=SimpleNamespace(st_mode=0o100644,st_file_attributes=0x400)):
            with self.assertRaises(ValueError):plain_path(self.root)

    def test_manifest_required_and_invalid_digest_rejected(self):
        self.manifest['files']['README.md']='bad';self.save()
        with self.assertRaises(ValueError):load_install(self.root)
        (self.root/MARKER).unlink()
        with self.assertRaises(FileNotFoundError):load_install(self.root)

    def test_optional_purge_uses_only_known_data_directory(self):
        data=self.base/'MaBaoNext';data.mkdir();(data/'settings.ini').write_text('fixture')
        other=self.base/'other-app';other.mkdir();(other/'keep').write_text('keep')
        with patch('genshinimpactvt.uninstaller.user_data_dir',return_value=data):purge_user_data()
        self.assertFalse(data.exists());self.assertTrue((other/'keep').exists())

    def test_cannot_wait_on_an_unrelated_process(self):
        with self.assertRaises(ValueError):wait_for_app(os.getpid(),self.root)

    def confirm_dialog(self,confirm,purge):
        from main import Main
        window=QWidget();observations=[]
        def choose():
            dialog=QApplication.activeModalWidget()
            observations.append(isinstance(dialog,QMessageBox) and not dialog.checkBox().isChecked())
            dialog.checkBox().setChecked(purge)
            dialog.done(QMessageBox.StandardButton.Yes if confirm else QMessageBox.StandardButton.Cancel)
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',str(self.root/'GenshinImpactVT.exe')):
            with patch('subprocess.Popen') as launch,patch.object(window,'close') as close:
                QTimer.singleShot(50,choose)
                Main.request_uninstall(window)
                if confirm:
                    self.assertEqual(launch.call_count,1)
                    args=launch.call_args.args[0]
                    self.assertEqual('--purge-user-data' in args,purge)
                    close.assert_called_once()
                else:
                    launch.assert_not_called();close.assert_not_called()
        self.assertEqual(observations,[True])
        window.close()

    def test_real_confirmation_cancel_starts_no_helper(self):
        self.confirm_dialog(False,False)
        self.assertTrue((self.root/'GenshinImpactVT.exe').exists())

    def test_real_confirmation_passes_explicit_data_choice(self):
        self.confirm_dialog(True,True)


if __name__=='__main__':unittest.main()
