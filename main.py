# Voice/run.py
import sys
import os
import threading
import time

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入模块
import STT
import voice
from Ui import voice_rumps_macos

class VoiceTTinput:
    def __init__(self):
        print("初始化 VoiceTTinput...")
        self.api_thread = None
        self.menu_app = None
        self.running = False
    
    def run(self):
        """同时启动API服务和菜单栏应用"""
        print("=" * 50)
        print("启动语音识别服务")
        print("=" * 50)
        
        self.running = True
        
        # 线程1: 启动FastAPI服务器
        self.api_thread = threading.Thread(
            target=self._run_api_server,
            name="APIServer",
            daemon=True  # 设置为守护线程，主程序退出时自动结束
        )
        self.api_thread.start()
        print("✅ API服务器线程已启动")
        
        # 给API服务器一点启动时间
        time.sleep(1)
        
        # 主线程: 启动菜单栏应用（会阻塞）
        print("✅ 启动菜单栏应用...")
        self.menu_app = voice_rumps_macos.VoiceServiceApp()
        self.menu_app.run()
    
    def _run_api_server(self):
        """运行API服务器的函数"""
        try:
            print("🚀 启动FastAPI服务器...")
            STT.main()  # 这会阻塞，但在单独的线程中
        except Exception as e:
            print(f"❌ API服务器启动失败: {e}")
        finally:
            self.running = False
    
    def stop(self):
        """停止所有服务"""
        self.running = False
        print("正在停止所有服务...")


if __name__ == "__main__":
    app = VoiceTTinput()
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n收到退出信号，正在关闭...")
        app.stop()