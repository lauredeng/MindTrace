"""手写图片预处理的最小回归测试：增强后仍合法，且对比度上升。"""
import io

from PIL import Image, ImageStat

from core.ocr import provider_image, prepare_image


def _low_contrast_image():
    img = Image.new('L', (200, 120), 128)
    pix = img.load()
    for y in range(30, 90):
        for x in range(20, 180):
            pix[x, y] = 120 if (x // 6 + y // 4) % 2 else 138
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def test_provider_image_enhances_contrast_and_stays_valid():
    data = _low_contrast_image()
    payload, mime = provider_image(data)
    assert mime in ('image/png', 'image/jpeg')
    prepare_image(payload)  # 不得抛异常：格式/尺寸校验仍通过
    before = ImageStat.Stat(Image.open(io.BytesIO(data))).stddev[0]
    after = ImageStat.Stat(Image.open(io.BytesIO(payload)).convert('L')).stddev[0]
    assert after > before
