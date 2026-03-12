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
        初始化语音识别服务 - 专注于中英文识别

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

        # 定义支持的语言（中英文）
        self.supported_languages = ["zh", "en"]
        self.language_names = {
            "zh": "中文",
            "en": "英文"
        }

        # 加载Whisper模型
        self._load_model(model_path, model_size)

        # 转录控制
        self.transcription_text = ""
        self.detected_language = None

    def _load_model(self, model_path, model_size):
        """加载Whisper模型并配置中英文识别"""
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

            # 配置模型专注于中英文
            self._configure_model_for_chinese_english()

            print("✅ 模型加载完成！")

            # 测试模型
            self._test_model()

        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _configure_model_for_chinese_english(self):
        """配置模型专注于中英文识别"""
        # 获取语言token IDs
        all_lang_tokens = self.processor.tokenizer.additional_special_tokens_ids
        
        # 创建语言到token ID的映射
        self.lang_to_token_id = {}
        for token_id in all_lang_tokens:
            token = self.processor.tokenizer.decode([token_id])
            # 提取语言代码 (格式如 "<|zh|>", "<|en|>")
            if token.startswith("<|") and token.endswith("|>"):
                lang_code = token[2:-2]
                if lang_code in self.supported_languages:
                    self.lang_to_token_id[lang_code] = token_id
        
        print(f"支持的语言token映射: {self.lang_to_token_id}")
        
        # 设置强制解码器ID为None，允许灵活的语言选择
        self.model.config.forced_decoder_ids = None
        
        # 可选：抑制其他语言的输出（如果确定只识别中英文）
        # 但通常不建议，因为模型可能仍需要检测语言
        
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
                predicted_ids = self.model.generate(
                    input_features,
                    language=None,  # 自动检测
                    task="transcribe",
                    max_length=50  # 缩短测试长度
                )
                transcription = self.processor.batch_decode(
                    predicted_ids, skip_special_tokens=True
                )
            print("✅ 模型测试成功！")
            
            # 测试语言检测
            with torch.no_grad():
                outputs = self.model.generate(
                    input_features,
                    language=None,
                    task="transcribe",
                    return_dict_in_generate=True,
                    output_scores=True
                )
                # 尝试检测生成的第一个token是否为语言token
                first_token = outputs.sequences[0, 0].item()
                first_token_text = self.processor.tokenizer.decode([first_token])
                print(f"语言检测测试 - 首个token: {first_token_text}")
                
        except Exception as e:
            print(f"⚠️ 模型测试警告: {e}")

    def detect_language(self, audio_array, sample_rate):
        """检测音频的语言（中/英）"""
        try:
            # 处理音频特征
            input_features = self.processor(
                audio_array, sampling_rate=sample_rate, return_tensors="pt"
            ).input_features.to(self.device)
            
            # 强制模型输出语言token
            with torch.no_grad():
                # 使用generate但限制输出为语言token
                outputs = self.model.generate(
                    input_features,
                    max_new_tokens=1,  # 只生成第一个token
                    output_scores=True,
                    return_dict_in_generate=True
                )
                
                # 获取第一个token
                first_token = outputs.sequences[0, 0].item()
                first_token_text = self.processor.tokenizer.decode([first_token])
                
                # 解析语言
                if first_token_text.startswith("<|") and first_token_text.endswith("|>"):
                    detected_lang = first_token_text[2:-2]
                    if detected_lang in self.supported_languages:
                        return detected_lang
                
            return "unknown"
            
        except Exception as e:
            print(f"语言检测错误: {e}")
            return "unknown"

    def transcribe_audio_data(self, audio_data, sample_rate=16000, force_language=None):
        """
        将传入的音频数据转换为文字（专注于中英文）
        
        Args:
            audio_data: 音频数据
            sample_rate: 采样率
            force_language: 强制指定语言 ('zh', 'en', 或 None自动检测)
        """
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

            # 语言选择逻辑
            if force_language:
                # 强制使用指定语言
                language = force_language
                print(f"🔤 强制使用语言: {self.language_names.get(language, language)}")
            else:
                # 自动检测语言
                detected_lang = self.detect_language(audio_array, sample_rate)
                if detected_lang in self.supported_languages:
                    language = detected_lang
                    self.detected_language = detected_lang
                    print(f"🔤 检测到语言: {self.language_names.get(language, language)}")
                else:
                    # 默认使用中文（可以根据需要调整）
                    language = "zh"
                    print(f"⚠️ 未能准确检测语言，默认使用: {self.language_names['zh']}")

            # 使用processor处理音频
            print("🔄 处理音频特征...")
            input_features = self.processor(
                audio_array, sampling_rate=sample_rate, return_tensors="pt"
            ).input_features

            # 移动到指定设备
            input_features = input_features.to(self.device)

            # 生成token ids - 优化参数以提高准确性
            print(f"🔄 生成识别结果 (语言: {self.language_names.get(language, language)})...")
            with torch.no_grad():
                predicted_ids = self.model.generate(
                    input_features,
                    language=language,  # 指定检测到的语言
                    task="transcribe",  # 转录任务
                    # 优化参数以提高准确性
                    max_length=448,
                    num_beams=5,  # 增加beam search数量提高准确性
                    temperature=0.0,  # 使用确定性解码
                    do_sample=False,  # 不使用采样，保持确定性
                    length_penalty=1.0,  # 长度惩罚
                    early_stopping=True,  # 早期停止
                    no_repeat_ngram_size=3,  # 防止重复n-gram
                    # 语言特定的token抑制（可选）
                    suppress_tokens=None,
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

    def transcribe_with_language_detection(self, audio_data, sample_rate=16000):
        """带语言检测的转录（返回文本和检测到的语言）"""
        transcription = self.transcribe_audio_data(audio_data, sample_rate)
        return {
            "text": transcription,
            "language": self.detected_language,
            "language_name": self.language_names.get(self.detected_language, "未知")
        }


def create_api_app(voice_app):
    """创建FastAPI应用，集成VoiceTypingApp"""
    app = FastAPI(title="Voice Typing API - Chinese/English", version="1.0.0")
    
    @app.get("/health")
    async def health():
        """健康检查端点"""
        return {
            "status": "healthy",
            "message": "Voice Typing API (中英文识别) is running!",
            "supported_languages": voice_app.language_names
        }
    
    @app.get("/")
    async def root():
        return {
            "message": "Voice Typing API is running!",
            "status": "ok",
            "supported_languages": voice_app.language_names
        }
    
    @app.post("/transcribe/")
    async def transcribe_audio(
        file: UploadFile = File(...),
        language: str = None  # 可选参数：'zh', 'en', 或 None自动检测
    ):
        """接收音频文件并返回转录文本"""
        try:
            # 读取上传的文件
            contents = await file.read()
            
            # 使用soundfile读取音频数据
            audio_data, sample_rate = sf.read(io.BytesIO(contents))
            
            # 调用VoiceTypingApp的转录方法
            transcription = voice_app.transcribe_audio_data(
                audio_data, 
                sample_rate,
                force_language=language  # 传递语言参数
            )
            
            # 获取检测到的语言
            detected_lang = voice_app.detected_language
            
            return JSONResponse(content={
                "success": True,
                "transcription": transcription,
                "detected_language": detected_lang,
                "detected_language_name": voice_app.language_names.get(detected_lang, "未知"),
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
            language = audio_base64.get("language", None)  # 可选语言参数
            
            # 解码base64音频数据
            audio_bytes = base64.b64decode(base64_audio)
            
            # 使用soundfile读取音频数据
            audio_data, detected_sr = sf.read(io.BytesIO(audio_bytes))
            
            # 如果未指定采样率，使用检测到的采样率
            if sample_rate == 16000 and detected_sr != 16000:
                sample_rate = detected_sr
            
            # 调用VoiceTypingApp的转录方法
            transcription = voice_app.transcribe_audio_data(
                audio_data, 
                sample_rate,
                force_language=language
            )
            
            # 获取检测到的语言
            detected_lang = voice_app.detected_language
            
            return JSONResponse(content={
                "success": True,
                "transcription": transcription,
                "detected_language": detected_lang,
                "detected_language_name": voice_app.language_names.get(detected_lang, "未知")
            })
            
        except Exception as e:
            print(f"❌ API转录错误: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )
    
    @app.post("/detect_language/")
    async def detect_language(file: UploadFile = File(...)):
        """仅检测音频语言，不进行完整转录"""
        try:
            # 读取上传的文件
            contents = await file.read()
            
            # 使用soundfile读取音频数据
            audio_data, sample_rate = sf.read(io.BytesIO(contents))
            
            # 标准化音频数据
            if audio_data.dtype == np.int16:
                audio_array = audio_data.astype(np.float32) / 32768.0
            elif audio_data.dtype == np.int32:
                audio_array = audio_data.astype(np.float32) / 2147483648.0
            else:
                audio_array = audio_data.astype(np.float32)
            
            if len(audio_array.shape) > 1:
                audio_array = audio_array[:, 0]
            
            # 检测语言
            detected_lang = voice_app.detect_language(audio_array, sample_rate)
            
            return JSONResponse(content={
                "success": True,
                "detected_language": detected_lang,
                "detected_language_name": voice_app.language_names.get(detected_lang, "未知"),
                "filename": file.filename
            })
            
        except Exception as e:
            print(f"❌ 语言检测错误: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )
    
    return app


def run_api_server(voice_app, host="127.0.0.1", port=8000):
    """运行FastAPI服务器"""
    app = create_api_app(voice_app)
    print("🚀 启动中英文语音识别API服务...")
    print(f"支持的语言: {voice_app.language_names}")
    uvicorn.run(app, host=host, port=port)


def main():
    # 配置参数
    CONFIG = {
        # 使用你的本地模型路径
        "model_path": "./models/openai/whisper-small",  # 本地Hugging Face格式模型
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