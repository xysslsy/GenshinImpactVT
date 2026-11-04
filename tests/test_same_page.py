import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from genshinimpactvt.browser import BrowserHost


class SamePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_deferred_request_and_closed_host(self):
        host=BrowserHost();event=SimpleNamespace(Uri='https://www.bilibili.com/video/test',Handled=False)
        callbacks=[]
        with patch('genshinimpactvt.browser.QTimer.singleShot',side_effect=lambda ms,fn:callbacks.append(fn)):
            host._on_new_window(None,event)
        self.assertTrue(event.Handled)
        with patch.object(host,'navigate') as navigate:
            callbacks[0]();navigate.assert_called_once_with(event.Uri)
            host._disposed=True;callbacks[0]();self.assertEqual(navigate.call_count,1)
        host.close()

    def test_unsupported_scheme_is_handled_without_launch(self):
        host=BrowserHost();messages=[];host.failed.connect(messages.append)
        event=SimpleNamespace(Uri='javascript:alert(1)',Handled=False)
        with patch('genshinimpactvt.browser.QTimer.singleShot') as defer:
            host._on_new_window(None,event);defer.assert_not_called()
        self.assertTrue(event.Handled);self.assertTrue(messages)
        host.close()


if __name__=='__main__':unittest.main()
