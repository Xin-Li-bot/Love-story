import os
import json
import re


def generate_timeline():
    # 注意：在 Streamlit 开启静态映射后，static 文件夹中的资源
    # 可以通过 http://.../app/static/文件名 访问
    # 在本地代码中，我们直接用相对路径
    static_dir = "static"
    if not os.path.exists(static_dir):
        print("❌ 找不到 static 文件夹")
        return

    valid_extensions = ('.png', '.jpg', '.jpeg', '.gif')
    photos = [f for f in os.listdir(static_dir) if f.lower().endswith(valid_extensions)]

    # 按照日期排序
    photos.sort()

    events = []
    for photo in photos:
        # 提取日期 (如 20221225)
        date_match = re.search(r"(\d{4})(\d{2})(\d{2})", photo)
        y, m, d = map(int, date_match.groups()) if date_match else (2024, 1, 1)

        events.append({
            "start_date": {"year": y, "month": m, "day": d},
            "text": {
                "headline": photo.split('_')[-1].split('.')[0],
                "text": f"<p>那天的回忆 ✨</p>"
            },
            "media": {
                # 关键：这里路径必须改为这种格式，Streamlit 才能识别
                "url": f"app/static/{photo}",
                "caption": "❤️"
            }
        })

    timeline_data = {
        "title": {
            "media": {"url": f"app/static/{photos[0]}" if photos else ""},
            "text": {"headline": "❤️ 我们的故事", "text": "愿每一份回忆都闪闪发光"}
        },
        "events": events
    }

    with open('timeline.json', 'w', encoding='utf-8') as f:
        json.dump(timeline_data, f, ensure_ascii=False, indent=4)

    print(f"✨ timeline.json 已更新，当前引用本地路径模式。")


if __name__ == "__main__":
    generate_timeline()