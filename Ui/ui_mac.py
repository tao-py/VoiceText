import sys
import os
import threading
import subprocess
import time
import requests
from pathlib import Path

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox, QWidget
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QFont
from PySide6.QtCore import Qt


class VoiceServiceApp(QWidget):
    def __init__(self):
        super().__init__()

        self.api_process = None
        self.api_url = "http://127.0.0.1:8000"
        self.voice_recorder = None
        self.recorder_thread = None

        self._init_tray_icon()

    def _init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self._create_icon("⚪"))
        self.tray_icon.setToolTip("语音识别服务")

        self._create_menu()
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _create_icon(self, emoji):
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setFont(QFont("Segoe UI Emoji", 32))
        painter.drawText(pixmap.rect(), 0, emoji)
        painter.end()
        return QIcon(pixmap)

    def _create_menu(self):
        self.menu = QMenu()

        self.start_api_action = QAction("启动API服务", self)
        self.start_api_action.triggered.connect(self.start_api)

        self.stop_api_action = QAction("停止API服务", self)
        self.stop_api_action.triggered.connect(self.stop_api)
        self.stop_api_action.setEnabled(False)

        self.menu.addAction(self.start_api_action)
        self.menu.addAction(self.stop_api_action)
        self.menu.addSeparator()

        open_docs_action = QAction("打开API文档", self)
        open_docs_action.triggered.connect(self.open_docs)

        test_connection_action = QAction("测试连接", self)
        test_connection_action.triggered.connect(self.test_connection)

        self.menu.addAction(open_docs_action)
        self.menu.addAction(test_connection_action)
        self.menu.addSeparator()

        about_action = QAction("关于", self)
        about_action.triggered.connect(self.about)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)

        self.menu.addAction(about_action)
        self.menu.addAction(quit_action)

        self.tray_icon.setContextMenu(self.menu)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.test_connection(None)

    def start_api(self, sender=None):
        if (
            self.api_process
            and self.api_process.poll() is None
            or not self._check_api_health()
        ):
            QMessageBox.information(self, "提示", "API服务已经在运行中")
            return

        try:
            self.api_process = subprocess.Popen(
                [sys.executable, "-m", "Api.STT"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            for _ in range(10):
                if self._check_api_health():
                    break
                time.sleep(1)
            else:
                raise Exception("API服务启动超时")

            self.start_api_action.setText("停止API服务")
            self.start_api_action.triggered.disconnect()
            self.start_api_action.triggered.connect(self.stop_api)
            self.stop_api_action.setEnabled(True)

            self.tray_icon.setIcon(self._create_icon("🔴"))

            self.tray_icon.showMessage(
                "语音服务", "FastAPI服务正在运行", QSystemTrayIcon.Information, 3000
            )

            self._start_recorder()

        except Exception as e:
            QMessageBox.warning(self, "启动失败", str(e))

    def stop_api(self, sender=None):
        if (
            self.api_process
            and self.api_process.poll() is None
            or not self._check_api_health()
        ):
            try:
                self.api_process.terminate()

                try:
                    self.api_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.api_process.kill()

                if self.api_process.stdout:
                    self.api_process.stdout.close()
                if self.api_process.stderr:
                    self.api_process.stderr.close()

                self.api_process = None

                self.start_api_action.setText("启动API服务")
                self.start_api_action.triggered.disconnect()
                self.start_api_action.triggered.connect(self.start_api)
                self.stop_api_action.setEnabled(False)

                self.tray_icon.showMessage(
                    "语音服务", "FastAPI服务已关闭", QSystemTrayIcon.Information, 3000
                )

                self.tray_icon.setIcon(self._create_icon("⚪"))

            except Exception as e:
                QMessageBox.warning(self, "停止失败", str(e))

        else:
            QMessageBox.information(self, "提示", "API服务未运行")

    def open_docs(self, _=None):
        if self._check_api_health():
            import webbrowser

            webbrowser.open(f"{self.api_url}/docs")
            self.tray_icon.showMessage(
                "API文档", "已在浏览器中打开", QSystemTrayIcon.Information, 2000
            )
        else:
            QMessageBox.information(self, "提示", "请先启动API服务")

    def test_connection(self, _=None):
        if self._check_api_health():
            self.tray_icon.showMessage(
                "连接测试", "API服务正常", QSystemTrayIcon.Information, 2000
            )
        else:
            QMessageBox.information(self, "提示", "API服务未运行")

    def about(self, _=None):
        info = (
            "🎤 语音识别服务控制器\n\n"
            "功能:\n"
            "- 控制API服务器的启动/停止\n"
            "- 按住Alt键录音并自动识别\n"
            "- 识别结果自动填入光标位置\n\n"
            "使用说明:\n"
            "1. 点击'启动API服务'\n"
            "2. 按住Alt键开始录音\n"
            "3. 松开Alt键自动识别并填入"
        )
        QMessageBox.information(self, "关于", info)

    def quit_app(self, _=None):
        if self.api_process and self.api_process.poll() is None:
            self.api_process.terminate()
        QApplication.quit()

    def _check_api_health(self):
        try:
            response = requests.get(self.api_url, timeout=2)
            return response.status_code == 200
        except:
            return False

    def _start_recorder(self):
        try:
            if self.voice_recorder and hasattr(self.voice_recorder, "is_recording"):
                return

            from voice import VoiceRecorder

            self.voice_recorder = VoiceRecorder(api_url=self.api_url, menu_app=self)

            self.recorder_thread = threading.Thread(
                target=self.voice_recorder.start_listening, daemon=True
            )
            self.recorder_thread.start()

            print("✅ 录音器已启动")

        except Exception as e:
            print(f"❌ 启动录音器失败: {e}")

    def update_icon(self, is_recording):
        if is_recording:
            self.tray_icon.setIcon(self._create_icon("🔴"))
        else:
            self.tray_icon.setIcon(self._create_icon("⚪"))

    def run(self):
        self.show()

    def closeEvent(self, event):
        event.ignore()
        self.hide()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = VoiceServiceApp()
    window.run()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
