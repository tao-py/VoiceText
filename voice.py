# Voice/voice.py
import pyaudio
import wave
import threading
import numpy as np
import time
import pyautogui
import requests
import io
import sys
import os
import base64
import json
from pathlib import Path
from pynput import keyboard as pynput_keyboard

class VoiceRecorder:
    def __init__(self, api_url="http://127.0.0.1:8000", menu_app=None):
        """初始化录音器
        
        Args:
            api_url: STT服务的API地址
            menu_app: rumps菜单应用实例，用于更新图标
        """
        # 音频参数
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000
        self.CHUNK = 1024
        
        # 状态标志
        self.is_recording = False
        self.is_processing = False
        
        # 音频数据
        self.audio_frames = []
        self.recording_thread = None
        
        # PyAudio实例
        self.p = pyaudio.PyAudio()
        
        # API配置
        self.api_url = api_url
        self.menu_app = menu_app  # rumps应用实例
        
        # 按键监听器
        self.listener = None
        
        print("✅ 录音器初始化完成")
        print("🎤 按住 Alt 键开始录音，松开自动识别并填入光标位置")
        print("❌ 按 ESC 键退出程序")
    
    def update_menu_icon(self, is_recording):
        """更新菜单栏图标"""
        if self.menu_app:
            if is_recording:
                self.menu_app.title = "🔴"  # 录音中显示红圆
            else:
                self.menu_app.title = "⚪"  # 空闲显示白圆
            print(f"图标已更新: {self.menu_app.title}")  # 调试信息
    
    def on_press(self, key):
        """按下按键时的回调函数"""
        try:
            # 检测Alt键按下
            if key in [pynput_keyboard.Key.alt_l, pynput_keyboard.Key.alt_r]:
                if not self.is_recording and not self.is_processing:
                    print("\n🎤 开始录音... (松开Alt键结束)")
                    self.start_recording()
                    
            # ESC键退出
            elif key == pynput_keyboard.Key.esc:
                print("\n👋 正在退出...")
                return False
                
        except AttributeError:
            pass
    
    def on_release(self, key):
        """松开按键时的回调函数"""
        try:
            # 检测Alt键松开
            if key in [pynput_keyboard.Key.alt_l, pynput_keyboard.Key.alt_r]:
                if self.is_recording:
                    print("\n⏹️ 录音结束，正在识别...")
                    self.stop_recording()
                    
        except AttributeError:
            pass
    
    def start_recording(self):
        """开始录制音频"""
        self.is_recording = True
        self.audio_frames = []
        
        # 更新图标为红色
        self.update_menu_icon(True)
        
        # 在新线程中录制音频
        self.recording_thread = threading.Thread(target=self._record_audio)
        self.recording_thread.daemon = True
        self.recording_thread.start()
    
    def _record_audio(self):
        """在后台线程中录制音频"""
        stream = None
        try:
            stream = self.p.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK
            )
            
            print("🎤 录音中", end="", flush=True)
            
            while self.is_recording:
                try:
                    data = stream.read(self.CHUNK, exception_on_overflow=False)
                    self.audio_frames.append(data)
                    print(".", end="", flush=True)
                except Exception as e:
                    print(f"\n❌ 读取音频错误: {e}")
                    break
            print()
            
        except Exception as e:
            print(f"\n❌ 打开音频流失败: {e}")
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except:
                    pass
    
    def stop_recording(self):
        """停止录制并进行语音识别"""
        if not self.is_recording:
            return
        
        # 停止录音
        self.is_recording = False
        
        # 恢复图标为白色
        self.update_menu_icon(False)
        
        # 等待录音线程结束
        if self.recording_thread and self.recording_thread.is_alive():
            self.recording_thread.join(timeout=2.0)
        
        # 如果有音频数据，进行识别
        if self.audio_frames:
            self.is_processing = True
            try:
                # 在后台线程中处理识别
                process_thread = threading.Thread(target=self._process_audio)
                process_thread.daemon = True
                process_thread.start()
            except Exception as e:
                print(f"❌ 启动识别线程失败: {e}")
                self.is_processing = False
        else:
            print("⚠️ 没有录到音频数据")
    
    def _process_audio(self):
        """通过API进行语音识别"""
        try:
            # 转换音频数据为WAV格式
            audio_file = self._save_audio_to_bytes()
            
            if audio_file is None:
                print("⚠️ 音频数据为空")
                self.is_processing = False
                return
            
            # 调用API进行识别
            print("🔄 正在识别...", end="", flush=True)
            transcription = self._transcribe_via_api(audio_file)
            
            if transcription:
                print(f"\n📝 识别结果: {transcription}")
                
                # 将识别结果填入光标位置
                self._insert_text_with_pyautogui(transcription)
            else:
                print("\n⚠️ 未能识别出文字")
                
        except Exception as e:
            print(f"\n❌ 语音识别错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.is_processing = False
    
    def _save_audio_to_bytes(self):
        """将录制的音频保存为WAV格式的字节数据"""
        if not self.audio_frames:
            return None
        
        try:
            # 创建字节流
            audio_bytes = io.BytesIO()
            
            # 写入WAV文件头
            with wave.open(audio_bytes, 'wb') as wf:
                wf.setnchannels(self.CHANNELS)
                wf.setsampwidth(self.p.get_sample_size(self.FORMAT))
                wf.setframerate(self.RATE)
                wf.writeframes(b''.join(self.audio_frames))
            
            # 获取字节数据
            audio_bytes.seek(0)
            return audio_bytes.getvalue()
            
        except Exception as e:
            print(f"❌ 音频转换错误: {e}")
            return None
    
    def _transcribe_via_api(self, audio_bytes):
        """通过API调用语音识别"""
        try:
            # 方法1: 直接上传文件
            files = {
                'file': ('audio.wav', audio_bytes, 'audio/wav')
            }
            
            response = requests.post(
                f"{self.api_url}/transcribe/",
                files=files,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('transcription', '')
            else:
                print(f"\n❌ API错误: {response.status_code}")
                return None
                
        except requests.exceptions.ConnectionError:
            print(f"\n❌ 无法连接到API服务器 {self.api_url}")
            print("请确保API服务已启动")
            return None
        except Exception as e:
            print(f"\n❌ API调用错误: {e}")
            return None
    
    def _insert_text_with_pyautogui(self, text):
        """使用pyautogui插入文本"""
        try:
            # 短暂延迟，确保焦点在正确的窗口
            time.sleep(0.2)
            
            # 使用pyautogui输入文本
            pyautogui.write(text, interval=0.01)  # interval可以调整输入速度
            
            print("✅ 文字已填入光标位置 (使用pyautogui)")
            
        except Exception as e:
            print(f"❌ pyautogui输入失败: {e}")
            # 备选方案：复制到剪贴板
            self._insert_text_via_clipboard(text)
    
    def _insert_text_with_pyautogui(self, text):
        """使用系统剪贴板方式输入文本（支持中文）"""
        try:
            # 方法1：使用剪贴板粘贴（支持中文）
            import pyperclip
            import keyboard
            
            # 保存当前剪贴板内容
            old_clipboard = pyperclip.paste()
            
            # 将识别结果复制到剪贴板
            pyperclip.copy(text)
            time.sleep(0.1)  # 确保剪贴板更新
            
            # 模拟粘贴操作 (Cmd+V on Mac, Ctrl+V on Windows/Linux)
            if sys.platform == 'darwin':  # macOS
                keyboard.press_and_release('command+v')
            else:  # Windows/Linux
                keyboard.press_and_release('ctrl+v')
            
            # 短暂延迟后恢复原剪贴板内容
            time.sleep(0.2)
            pyperclip.copy(old_clipboard)
            
            print("✅ 文字已填入光标位置 (通过剪贴板，支持中文)")
            
        except Exception as e:
            print(f"❌ 剪贴板方式失败: {e}")
            
            # 方法2：使用 pyautogui 逐个字符输入（备用）
            try:
                print("尝试使用 pyautogui 逐个字符输入...")
                
                # 对于中文，可能需要设置合适的输入法
                # 逐个字符输入，增加间隔时间
                for char in text:
                    pyautogui.write(char, interval=0.05)  # 每个字符间隔50ms
                    time.sleep(0.01)
                
                print("✅ 文字已填入光标位置 (使用 pyautogui)")
                
            except Exception as e2:
                print(f"❌ pyautogui输入也失败: {e2}")
                print(f"📋 请手动复制: {text}")
    
    def start_listening(self):
        """开始监听按键"""
        print("\n🎤 语音输入程序已启动")
        print("=" * 40)
        print("按住 Alt 键 - 开始录音")
        print("松开 Alt 键 - 停止并识别")
        print("按 ESC 键 - 退出程序")
        print("=" * 40)
        
        # 初始图标为白色
        self.update_menu_icon(False)
        
        # 创建并启动监听器
        with pynput_keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        ) as listener:
            self.listener = listener
            listener.join()
    
    def cleanup(self):
        """清理资源"""
        print("\n正在清理资源...")
        if self.p:
            self.p.terminate()
        print("✅ 已退出")


# 如果直接运行voice.py，提示需要通过run.py启动
if __name__ == "__main__":
    print("请通过 run.py 启动程序")
    print("python Voice/run.py")