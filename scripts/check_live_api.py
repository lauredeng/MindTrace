"""Opt-in real DeepSeek check. Never reads or prints API keys."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.ai import ai_ready, ask_ai
from core.ocr import recognize_image

parser = argparse.ArgumentParser(description='真实 DeepSeek 接口检查；--image 会发送图片至服务。')
parser.add_argument('--image', type=Path)
args = parser.parse_args()
if not ai_ready():
    print('SKIPPED: 服务端未启用。请通过环境变量或 Streamlit Secrets 配置；.env 仅在 development 模式后备使用。未调用任何 API。')
    sys.exit(0)
try:
    answer = ask_ai('请简短回答。', '请回复“连接成功”。')
    print('Text API returned: ' + answer)
    if args.image:
        result = recognize_image(args.image.read_bytes())
        print('真实图片转写草稿（仍需人工确认）：')
        print(json.dumps(result, ensure_ascii=False, indent=2))
except (RuntimeError, ValueError, OSError) as exc:
    print('FAILED: ' + str(exc))
    sys.exit(1)

