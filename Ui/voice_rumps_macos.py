# Voice/Ui/voice_rumps.py
from ast import Not
import rumps
import threading
import subprocess
import sys
import os
import requests
import time
from pathlib import Path

class VoiceServiceApp(rumps.App):
    def __init__(self):
        # 初始图标为白色圆
        super(VoiceServiceApp, self).__init__("⚪")
        
        self.api_process = None
        self.api_url = "http://127.0.0.1:8000"
        self.voice_recorder = None
        self.recorder_thread = None
        
        # 菜单项
        self.menu = [
            "启动API服务",
            "停止API服务",
            None,
            "打开API文档",
            "测试连接",
            None,
            "关于",
            "退出"
        ]

    @rumps.clicked("启动API服务")
    def start_api(self, sender):
        """启动FastAPI服务器"""
        
        if self.api_process and self.api_process.poll() is None or not self._check_api_health():
            rumps.alert(title="提示", message="API服务已经在运行中")
            return
        
        else:
            try:
                # 启动API服务器
                self.api_process = subprocess.Popen(
                    [sys.executable, "-m", "Api.STT"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                # 等待API服务启动
                for _ in range(10):
                    if self._check_api_health():
                        break
                    time.sleep(1)
                else:
                    raise Exception("API服务启动超时")
                
                # 更新菜单文字和图标
                sender.title = "停止API服务"
                self.title = "🔴"
                
                rumps.notification(
                    title="语音服务",
                    subtitle="已启动",
                    message="FastAPI服务正在运行"
                )
                
                # 启动录音器
                self._start_recorder()
                
            except Exception as e:
                rumps.alert(title="启动失败", message=str(e))
    
    @rumps.clicked("停止API服务")
    def stop_api(self, sender):
        """停止API服务器"""

        if self.api_process and self.api_process.poll() is None or not self._check_api_health():
            try:
                # 先优雅关闭
                self.api_process.terminate()

                try:
                    self.api_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # 如果没关掉就强制杀
                    self.api_process.kill()

                # 关闭管道
                if self.api_process.stdout:
                    self.api_process.stdout.close()
                if self.api_process.stderr:
                    self.api_process.stderr.close()

                self.api_process = None

                # 恢复菜单文字
                sender.title = "启动API服务"

                rumps.notification(
                    title="语音服务",
                    subtitle="已停止",
                    message="FastAPI服务已关闭"
                )

                self.title = "⚪"

            except Exception as e:
                rumps.alert(title="停止失败", message=str(e))

        else:
            rumps.alert(title="提示", message="API服务未运行")
    
    @rumps.clicked("打开API文档")
    def open_docs(self, _):
        """打开API文档"""
        import webbrowser
        if self._check_api_health():
            webbrowser.open(f"{self.api_url}/docs")
            rumps.notification("API文档", "已打开", "在浏览器中查看")
        else:
            rumps.alert(title="提示", message="请先启动API服务")
    
    @rumps.clicked("测试连接")
    def test_connection(self, _):
        """测试API连接"""
        if self._check_api_health():
            rumps.notification("连接测试", "成功", "API服务正常")
        else:
            rumps.alert(title="提示", message="API服务未运行")
    
    @rumps.clicked("关于")
    def about(self, _):
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
        rumps.alert(message=info)
    
    @rumps.clicked("退出")
    def quit_app(self, _):
        """退出应用"""
        if self.api_process and self.api_process.poll() is None:
            self.api_process.terminate()
        rumps.quit_application()
    
    def _check_api_health(self):
        """检查API服务是否健康"""
        try:
            response = requests.get(self.api_url, timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def _start_recorder(self):
        """启动录音器"""
        try:
            # 避免重复启动
            if self.voice_recorder and hasattr(self.voice_recorder, 'is_recording'):
                return
            
            # 导入VoiceRecorder
            from voice import VoiceRecorder
            
            # 创建录音器实例，传入self以便更新图标
            self.voice_recorder = VoiceRecorder(
                api_url=self.api_url,
                menu_app=self
            )
            
            # 在新线程中启动录音器
            self.recorder_thread = threading.Thread(
                target=self.voice_recorder.start_listening,
                daemon=True
            )
            self.recorder_thread.start()
            
            print("✅ 录音器已启动")
            
        except Exception as e:
            print(f"❌ 启动录音器失败: {e}")