# Voice/Ui/voice_tray_simple.py
import sys
import os
import threading
import subprocess
import time
import requests
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QMessageBox,
                               QWidget, QHBoxLayout, QLabel, QFrame)
from PySide6.QtCore import QTimer, Signal, QObject, Qt
import PySide6.QtGui
import ctypes
from ctypes import wintypes

# 用于全局热键的Windows API
user32 = ctypes.windll.user32

class HotKeyManager(QObject):
    """全局热键管理器"""
    alt_pressed = Signal()
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.hotkey_id = 1
        
    def start_listening(self):
        """开始监听全局热键"""
        MOD_ALT = 0x0001
        VK_MENU = 0x12  # Alt键
        
        # 注册热键
        user32.RegisterHotKey(None, self.hotkey_id, MOD_ALT, VK_MENU)
        
        try:
            msg = wintypes.MSG()
            while self.running:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == -1:
                    break
                
                if msg.message == 0x0312:  # WM_HOTKEY
                    if msg.wParam == self.hotkey_id:
                        self.alt_pressed.emit()
                    
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnregisterHotKey(None, self.hotkey_id)
    
    def stop(self):
        """停止监听"""
        self.running = False
        user32.PostQuitMessage(0)

class VoiceTrayIcon(QSystemTrayIcon):
    """系统托盘图标类 - 放在任务栏右侧"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 设置图标（使用emoji作为临时图标，实际使用时替换为ico文件）
        self.setIcon(self._create_icon("🎤"))
        self.setToolTip("语音服务控制器")
        
        # 创建右键菜单
        self.menu = QMenu()
        
        # 状态显示（自定义）
        self.status_action = PySide6.QtGui.QAction("● 服务状态: 已停止", self.menu)
        self.status_action.setEnabled(False)
        self.status_action.setIcon(self._create_colored_icon("#f44336"))
        self.menu.addAction(self.status_action)
        
        self.menu.addSeparator()
        
        # 控制菜单
        self.start_action = PySide6.QtGui.QAction("▶ 启动API服务", self.menu)
        self.start_action.triggered.connect(self.start_api)
        self.menu.addAction(self.start_action)
        
        self.stop_action = PySide6.QtGui.QAction("⏹ 停止API服务", self.menu)
        self.stop_action.triggered.connect(self.stop_api)
        self.stop_action.setEnabled(False)
        self.menu.addAction(self.stop_action)
        
        self.menu.addSeparator()
        
        self.docs_action = PySide6.QtGui.QAction("📄 打开API文档", self.menu)
        self.docs_action.triggered.connect(self.open_docs)
        self.menu.addAction(self.docs_action)
        
        self.test_action = PySide6.QtGui.QAction("🔌 测试连接", self.menu)
        self.test_action.triggered.connect(self.test_connection)
        self.menu.addAction(self.test_action)
        
        self.menu.addSeparator()
        
        self.about_action = PySide6.QtGui.QAction("ℹ 关于", self.menu)
        self.about_action.triggered.connect(self.show_about)
        self.menu.addAction(self.about_action)
        
        self.quit_action = PySide6.QtGui.QAction("✖ 退出", self.menu)
        self.quit_action.triggered.connect(self.quit_app)
        self.menu.addAction(self.quit_action)
        
        # 设置菜单
        self.setContextMenu(self.menu)
        
        # 连接信号
        self.activated.connect(self.on_tray_activated)
        
        # 初始化管理器
        self.api_process = None
        self.api_url = "http://127.0.0.1:8000"
        self.api_running = False
        
        # 定时检查API状态
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.check_api_status)
        self.status_timer.start(3000)  # 每3秒检查一次
        
        # 录音器相关
        self.recorder = None
        self.hotkey_manager = None
        
        # 启动时检查
        QTimer.singleShot(1000, self.check_api_status)
    
    def _create_icon(self, char):
        """创建简单的文字图标"""
        from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI", 32)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, char)
        painter.end()
        return PySide6.QtGui.QIcon(pixmap)
    
    def _create_colored_icon(self, color):
        """创建彩色圆点图标"""
        from PySide6.QtGui import QPixmap, QPainter, QColor
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()
        return PySide6.QtGui.QIcon(pixmap)
    
    def on_tray_activated(self, reason):
        """托盘图标被激活"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            # 双击托盘图标，启动/停止快速录音（可自定义）
            if self.api_running:
                self.show_notification("提示", "双击录音", "按住Alt键开始录音")
    
    def check_api_status(self):
        """检查API状态"""
        running = self._check_api_health()
        
        if running != self.api_running:
            self.api_running = running
            self.update_ui_status()
    
    def update_ui_status(self):
        """更新UI状态"""
        if self.api_running:
            self.status_action.setText("● 服务状态: 运行中")
            self.status_action.setIcon(self._create_colored_icon("#4caf50"))
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(True)
            self.setIcon(self._create_icon("🔴"))
            self.setToolTip("语音服务控制器 (运行中)")
            
            # 启动录音器
            self.start_recorder()
        else:
            self.status_action.setText("● 服务状态: 已停止")
            self.status_action.setIcon(self._create_colored_icon("#f44336"))
            self.start_action.setEnabled(True)
            self.stop_action.setEnabled(False)
            self.setIcon(self._create_icon("⚪"))
            self.setToolTip("语音服务控制器 (已停止)")
    
    def _check_api_health(self):
        """检查API服务健康状态"""
        try:
            response = requests.get(self.api_url, timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def start_api(self):
        """启动API服务"""
        if self.api_running:
            QMessageBox.information(None, "提示", "API服务已经在运行中")
            return
        
        try:
            # 启动API服务器
            self.api_process = subprocess.Popen(
                [sys.executable, "-m", "Api.STT"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # 等待API服务启动
            for _ in range(10):
                if self._check_api_health():
                    break
                time.sleep(1)
            else:
                raise Exception("API服务启动超时")
            
            self.api_running = True
            self.update_ui_status()
            
            self.show_notification(
                "语音服务",
                "已启动",
                "FastAPI服务正在运行"
            )
            
        except Exception as e:
            QMessageBox.critical(None, "启动失败", str(e))
    
    def stop_api(self):
        """停止API服务"""
        if not self.api_running:
            QMessageBox.information(None, "提示", "API服务未运行")
            return
        
        try:
            if self.api_process:
                self.api_process.terminate()
                try:
                    self.api_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.api_process.kill()
                
                self.api_process = None
            
            self.api_running = False
            self.update_ui_status()
            
            self.show_notification(
                "语音服务",
                "已停止",
                "FastAPI服务已关闭"
            )
            
        except Exception as e:
            QMessageBox.critical(None, "停止失败", str(e))
    
    def open_docs(self):
        """打开API文档"""
        import webbrowser
        if self._check_api_health():
            webbrowser.open(f"{self.api_url}/docs")
            self.show_notification("API文档", "已打开", "在浏览器中查看")
        else:
            QMessageBox.information(None, "提示", "请先启动API服务")
    
    def test_connection(self):
        """测试API连接"""
        if self._check_api_health():
            self.show_notification("连接测试", "成功", "API服务正常")
        else:
            QMessageBox.information(None, "提示", "API服务未运行")
    
    def start_recorder(self):
        """启动录音器"""
        if self.recorder is None and self.api_running:
            try:
                from voice import VoiceRecorder
                
                self.recorder = VoiceRecorder(
                    api_url=self.api_url,
                    menu_app=self
                )
                
                self.recorder_thread = threading.Thread(
                    target=self.recorder.start_listening,
                    daemon=True
                )
                self.recorder_thread.start()
                
                # 启动热键监听
                self.start_hotkey_listener()
                
                print("✅ 录音器已启动")
                
            except Exception as e:
                print(f"❌ 启动录音器失败: {e}")
    
    def start_hotkey_listener(self):
        """启动热键监听"""
        if not self.hotkey_manager:
            self.hotkey_manager = HotKeyManager()
            self.hotkey_manager.alt_pressed.connect(self.on_alt_pressed)
            
            self.hotkey_thread = threading.Thread(
                target=self.hotkey_manager.start_listening,
                daemon=True
            )
            self.hotkey_thread.start()
    
    def on_alt_pressed(self):
        """Alt键按下回调"""
        if self.api_running and self.recorder:
            print("Alt pressed - recording")
            # 这里可以添加录音开始的提示
            self.show_notification("录音中", "", "正在录音...")
    
    def show_notification(self, title, subtitle, message):
        """显示通知"""
        self.showMessage(
            title, 
            f"{subtitle}\n{message}" if subtitle else message,
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
    
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.information(
            None, 
            "关于",
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
    
    def quit_app(self):
        """退出应用"""
        # 停止API服务
        if self.api_running:
            self.stop_api()
        
        # 停止热键监听
        if self.hotkey_manager:
            self.hotkey_manager.stop()
        
        # 退出应用
        QApplication.quit()

class VoiceTrayApp:
    """主应用类"""
    
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName("语音服务控制器")
        
        # 创建托盘图标（自动显示在任务栏右侧）
        self.tray_icon = VoiceTrayIcon()
        self.tray_icon.show()
    
    def run(self):
        return self.app.exec()

def main():
    if sys.platform != 'win32':
        print("此应用仅支持Windows系统")
        return 1
    
    app = VoiceTrayApp()
    sys.exit(app.run())

if __name__ == "__main__":
    main()