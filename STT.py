import os
import numpy as np
import torch
from transformers import WhisperProcessor, WhisperForConditionalGeneration
import io
import base64
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import uvicorn
import soundfile as sf


class VoiceTypingApp:
    def __init__(self, model_path=None, model_size="openai/whisper-small", device=None):
        """
        初始化语音识别服务

        Args:
            model_path: 本地模型路径（如：./models/openai/whisper-small）
            model_size: Hugging Face模型ID或本地路径
            device: 运行设备 ('cpu', 'cuda', 或 None自动选择)
        """
        # 设置设备
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        print(f"使用设备: {self.device}")

        # 加载Whisper模型（使用Transformers）
        self._load_model(model_path, model_size)

        # 转录控制
        self.transcription_text = ""

    def _load_model(self, model_path, model_size):
        """加载Whisper模型（使用Transformers库）"""
        try:
            # 确定模型路径
            if model_path and os.path.exists(model_path):
                model_name_or_path = model_path
                print(f"正在从本地路径加载模型: {model_path}")
            else:
                model_name_or_path = model_size
                print(f"正在从Hugging Face加载模型: {model_size}")

            # 加载processor和model
            print("加载processor...")
            self.processor = WhisperProcessor.from_pretrained(model_name_or_path)

            print("加载model...")
            self.model = WhisperForConditionalGeneration.from_pretrained(
                model_name_or_path,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            )

            # 移动到指定设备
            self.model = self.model.to(self.device)

            # 设置模型配置
            self.model.config.forced_decoder_ids = None

            print("✅ 模型加载完成！")

            # 测试模型
            self._test_model()

        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            import traceback

            traceback.print_exc()
            raise

    def _test_model(self):
        """测试模型是否正常工作"""
        try:
            # 创建一个静音音频进行测试
            dummy_audio = np.zeros(16000, dtype=np.float32)
            input_features = self.processor(
                dummy_audio, sampling_rate=16000, return_tensors="pt"
            ).input_features.to(self.device)

            # 测试生成
            with torch.no_grad():
                predicted_ids = self.model.generate(input_features)
                transcription = self.processor.batch_decode(
                    predicted_ids, skip_special_tokens=True
                )
            print("✅ 模型测试成功！")
        except Exception as e:
            print(f"⚠️ 模型测试警告: {e}")

    def transcribe_audio_data(self, audio_data, sample_rate=16000):
        """将传入的音频数据转换为文字（使用Transformers）"""
        try:
            # 将音频数据标准化到[-1, 1]范围
            if audio_data.dtype == np.int16:
                audio_array = audio_data.astype(np.float32) / 32768.0
            elif audio_data.dtype == np.int32:
                audio_array = audio_data.astype(np.float32) / 2147483648.0
            else:
                audio_array = audio_data.astype(np.float32)
            
            # 确保音频数据是单声道
            if len(audio_array.shape) > 1:
                audio_array = audio_array[:, 0]  # 取第一个声道
            
            print(f"📊 输入音频数组形状: {audio_array.shape}, 采样率: {sample_rate}")

            # 使用processor处理音频
            print("🔄 处理音频特征...")
            input_features = self.processor(
                audio_array, sampling_rate=sample_rate, return_tensors="pt"
            ).input_features

            # 移动到指定设备
            input_features = input_features.to(self.device)

            # 生成token ids
            print("🔄 生成识别结果...")
            with torch.no_grad():
                predicted_ids = self.model.generate(
                    input_features,
                    language=None,  # 自动检测语言
                    task="transcribe",  # 或 "translate" 翻译成英文
                    max_length=448,
                    num_beams=1,  # 使用贪心搜索，更快
                )

            # 解码token ids到文本
            transcription = self.processor.batch_decode(
                predicted_ids, skip_special_tokens=True
            )[0]

            if transcription:
                print(f"📝 识别结果: {transcription}")
                self.transcription_text = transcription
            else:
                print("⚠️ 未识别到语音")
                self.transcription_text = ""
                
            return transcription

        except Exception as e:
            print(f"❌ 识别错误: {e}")
            import traceback
            traceback.print_exc()
            self.transcription_text = ""
            return ""


def create_api_app(voice_app):
    """创建FastAPI应用，集成VoiceTypingApp"""
    app = FastAPI(title="Voice Typing API", version="1.0.0")
    
    @app.get("/health")
    async def health():
        """健康检查端点"""
        return {"status": "healthy", "message": "Voice Typing API is running!"}
    
    @app.get("/")
    async def root():
        return {"message": "Voice Typing API is running!", "status": "ok"}
    
    @app.post("/transcribe/")
    async def transcribe_audio(file: UploadFile = File(...)):
        """接收音频文件并返回转录文本"""
        try:
            # 读取上传的文件
            contents = await file.read()
            
            # 使用soundfile读取音频数据
            audio_data, sample_rate = sf.read(io.BytesIO(contents))
            
            # 调用VoiceTypingApp的转录方法
            transcription = voice_app.transcribe_audio_data(audio_data, sample_rate)
            
            return JSONResponse(content={
                "success": True,
                "transcription": transcription,
                "filename": file.filename,
                "sample_rate": sample_rate
            })
            
        except Exception as e:
            print(f"❌ API转录错误: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )
    
    @app.post("/transcribe_base64/")
    async def transcribe_base64_audio(audio_base64: dict):
        """接收Base64编码的音频数据并返回转录文本"""
        try:
            # 从请求中提取base64音频数据和采样率
            base64_audio = audio_base64.get("audio", "")
            sample_rate = audio_base64.get("sample_rate", 16000)
            
            # 解码base64音频数据
            audio_bytes = base64.b64decode(base64_audio)
            
            # 使用soundfile读取音频数据
            audio_data, detected_sr = sf.read(io.BytesIO(audio_bytes))
            
            # 如果未指定采样率，使用检测到的采样率
            if sample_rate == 16000 and detected_sr != 16000:
                sample_rate = detected_sr
            
            # 调用VoiceTypingApp的转录方法
            transcription = voice_app.transcribe_audio_data(audio_data, sample_rate)
            
            return JSONResponse(content={
                "success": True,
                "transcription": transcription
            })
            
        except Exception as e:
            print(f"❌ API转录错误: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )
    
    @app.get("/")
    async def root():
        return {"message": "Voice Typing API is running!"}
    
    return app


def run_api_server(voice_app, host="127.0.0.1", port=8000):
    """运行FastAPI服务器"""
    app = create_api_app(voice_app)
    uvicorn.run(app, host=host, port=port)


def main():
    # 配置参数
    CONFIG = {
        # 使用你的本地模型路径
        # 在项目路径/Users/taozhiwen/MyCode/Bottao 下的 ./models
        "model_path": "./models/openai/whisper-small",  # 本地Hugging Face格式模型
        # 或者使用Hugging Face模型ID（如果本地没有）
        # "model_path": "openai/whisper-small",
        # 运行设备
        "device": None,  # None自动选择，或指定"cuda"/"cpu"
    }

    # 检查本地路径
    if CONFIG["model_path"] and os.path.exists(CONFIG["model_path"]):
        print(f"✅ 找到本地模型路径: {CONFIG['model_path']}")
        # 列出目录内容
        files = os.listdir(CONFIG["model_path"])
        print(f"目录中的文件: {files[:5]}...")  # 只显示前5个
    else:
        print(f"⚠️ 本地路径不存在，将使用Hugging Face模型")
        CONFIG["model_path"] = "openai/whisper-small"

    # 创建应用实例
    app = VoiceTypingApp(model_path=CONFIG["model_path"], device=CONFIG["device"])

    print("🚀 启动API服务...")
    run_api_server(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    # 确保安装了必要的库
    main()
