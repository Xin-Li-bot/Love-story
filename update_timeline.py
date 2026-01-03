import os
import json
import re
import base64
from PIL import Image
from io import BytesIO


def get_base64_image(file_path):
    """将图片读取、压缩并转为 Base64 字符串"""
    try:
        img = Image.open(file_path)
        # 统一转为 RGB 模式防止 PNG 报错
        img = img.convert("RGB")
        # 关键：大幅缩小尺寸（时间轴预览图 600px 足够），保证 JSON 不会过大
        img.thumbnail((600, 600))

        buffered = BytesIO()
        # 质量设为 60，兼顾清晰度与体积
        img.save(buffered, format="JPEG", quality=60)
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return f"data:image/jpeg;base64,{img_str}"
    except Exception as e:
        print(f"❌ 处理图片 {file_path} 出错: {e}")
        return ""


def generate_timeline():
    static_dir = "static"
    if not os.path.exists(static_dir):
        print("❌ 找不到 static 文件夹")
        return

    valid_extensions = ('.png', '.jpg', '.jpeg', '.gif')
    photos = [f for f in os.listdir(static_dir) if f.lower().endswith(valid_extensions)]
    photos.sort()

    events = []
    for photo in photos:
        # 匹配日期
        date_match = re.search(r"(\d{4})(\d{2})(\d{2})", photo)
        y, m, d = map(int, date_match.groups()) if date_match else (2024, 1, 1)

        # 提取标题
        headline = photo.split('_')[-1].split('.')[0]

        print(f"正在处理: {photo}...")
        img_data = get_base64_image(os.path.join(static_dir, photo))

        events.append({
            "start_date": {"year": y, "month": m, "day": d},
            "text": {
                "headline": headline,
                "text": f"<p>那天的回忆 ✨</p>"
            },
            "media": {
                "url": img_data,  # 存入编码数据
                "caption": "❤️"
            }
        })

    timeline_data = {
        "title": {
            "media": {"url": get_base64_image(os.path.join(static_dir, photos[0])) if photos else ""},
            "text": {"headline": "❤️ 我们的故事", "text": "愿每一份回忆都闪闪发光"}
        },
        "events": events
    }

    with open('timeline.json', 'w', encoding='utf-8') as f:
        json.dump(timeline_data, f, ensure_ascii=False, indent=2)

    print(f"✅ timeline.json 已生成（Base64 模式）。即使中文文件名也能显示了！")


if __name__ == "__main__":
    generate_timeline()