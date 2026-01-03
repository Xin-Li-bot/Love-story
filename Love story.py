import streamlit as st
from streamlit_timeline import timeline
from datetime import datetime
import json
import requests
import base64

# --- 1. 基础配置与 LeanCloud API ---
st.set_page_config(page_title="李欣 & 王雅婷 的恋爱纪念册", page_icon="❤️", layout="wide")

# 请确保这些信息与你 LeanCloud 后台一致
APP_ID = "rNQ4ydw7DzQ5ODonN28y1FUy-gzGzoHsz"
APP_KEY = "BduhONbH6Gh6I3VtywhWgZZJ"
# 注意：国内版必须有 REST API 服务器地址，通常在 设置 -> 应用凭证 中找到
SERVER_URL = "https://rnq4ydw7.lc-cn-n1-shared.com"


def save_message(name, content):
    """通过 REST API 保存留言"""
    url = f"{SERVER_URL}/1.1/classes/Message"
    headers = {
        "X-LC-Id": APP_ID,
        "X-LC-Key": APP_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "name": name,
        "content": content,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    try:
        return requests.post(url, headers=headers, json=data, timeout=5)
    except:
        return None


def get_messages():
    """通过 REST API 获取留言列表"""
    url = f"{SERVER_URL}/1.1/classes/Message?order=-createdAt&limit=20"
    headers = {
        "X-LC-Id": APP_ID,
        "X-LC-Key": APP_KEY
    }
    try:
        res = requests.get(url, headers=headers, timeout=5)
        return res.json().get('results', [])
    except:
        return []


# --- 2. 核心美化 CSS ---
def local_css():
    st.markdown("""
        <style>
        .stApp { background-color: #fff5f5; font-family: 'Microsoft YaHei', sans-serif; }

        /* 侧边栏及呼出按钮修复 */
        [data-testid="stHeader"] { background: rgba(0,0,0,0); }
        button[kind="headerNoPadding"] { visibility: visible !important; z-index: 9999; color: #ff4b4b !important; }

        /* 全局卡片样式 */
        .custom-card {
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(10px);
            padding: 25px;
            border-radius: 20px;
            box-shadow: 0 10px 30px rgba(255, 182, 193, 0.2);
            margin-bottom: 25px;
            border: 1px solid rgba(255, 255, 255, 0.4);
        }

        .main-title { color: #ff4b4b; text-align: center; font-weight: 800; font-size: 3rem; margin-bottom: 0; }

        @keyframes heartBeat {
            0% { transform: scale(1); }
            14% { transform: scale(1.1); }
            28% { transform: scale(1); }
            42% { transform: scale(1.1); }
            70% { transform: scale(1); }
        }
        .heart-icon { display: inline-block; animation: heartBeat 2s infinite; color: #ff4b4b; }
        </style>
    """, unsafe_allow_html=True)


local_css()

# --- 3. 侧边栏：档案与音乐 ---
with st.sidebar:
    st.markdown("<h2 style='text-align:center;'>💖 爱情档案</h2>", unsafe_allow_html=True)
    try:
        st.image("static/20230318_初次相识.png", caption="我们的第一张合照")
    except:
        st.info("请确保图片位于 static/ 目录下")

    st.markdown("---")
    st.markdown("🎵 **Merry Christmas Mr.Lawrence**")
    try:
        audio_file = open('static/love_song.mp3', 'rb')
        st.audio(audio_file.read(), format='audio/mp3')
    except:
        st.caption("💿 待上传: static/love_song.mp3")

    st.markdown("---")
    st.markdown("📅 **重要日子**")
    st.write("💘 2022-12-25 正式在一起")
    st.write("🎂 08-06 雅婷的生日")
    st.write("---")
    st.caption("Made with ❤️ by 世界上最爱你的人")

# --- 4. 头部天数看板 ---
st.markdown("<h1 class='main-title'>👩‍❤️‍👨 我们的恋爱时光机 <span class='heart-icon'>❤️</span></h1>",
            unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888;'>既然琴瑟起，何以笙箫默</p>", unsafe_allow_html=True)

start_date = datetime(2022, 12, 25)
now = datetime.now()
days_together = (now - start_date).days

# 计算下个纪念日
this_year_anniv = datetime(now.year, 12, 25)
next_anniv = this_year_anniv if now <= this_year_anniv else datetime(now.year + 1, 12, 25)
days_to_anniv = (next_anniv - now).days

st.markdown(f"""
    <div style="background: linear-gradient(135deg, #ff758c 0%, #ff7eb3 100%); 
                padding: 40px; border-radius: 25px; text-align: center; color: white; 
                margin-bottom: 35px; box-shadow: 0 15px 35px rgba(255,117,140,0.3);">
        <div style="display: flex; justify-content: space-around; align-items: center; flex-wrap: wrap;">
            <div style="min-width: 180px;">
                <p style="margin:0; opacity: 0.8;">我们已相爱</p>
                <h1 style="margin:0; font-size: 60px; color: white; border:none;">{days_together} <small style="font-size:20px;">天</small></h1>
            </div>
            <div style="min-width: 180px;">
                <p style="margin:0; opacity: 0.8;">距离四周年</p>
                <h1 style="margin:0; font-size: 60px; color: white; border:none;">{days_to_anniv} <small style="font-size:20px;">天</small></h1>
            </div>
        </div>
    </div>
""", unsafe_allow_html=True)

# --- 5. 恋爱时光机 (时间轴) ---
st.markdown("### ⏳ 我们的回忆录")
st.markdown('<div class="custom-card">', unsafe_allow_html=True)
try:
    with open('timeline.json', "r", encoding='utf-8') as f:
        timeline(f.read(), height=700)
except:
    st.error("请先运行 update_timeline.py 生成 timeline.json")
st.markdown('</div>', unsafe_allow_html=True)

# --- 6. 照片墙 ---
st.markdown("### 📸 那些美好的瞬间")
photos = [
    {"url": "static/20230318_初次相识.png", "cap": "故事的开始"},
    {"url": "static/20230503_第一次旅行.png", "cap": "想和你去全世界"},
    {"url": "static/20251226_一起看海.jpg", "cap": "最美的那一天"}
]
cols = st.columns(3)
for i, photo in enumerate(photos):
    with cols[i % 3]:
        st.markdown('<div class="custom-card" style="padding:10px;">', unsafe_allow_html=True)
        try:
            st.image(photo["url"], use_container_width=True)
            st.markdown(f"<p style='text-align:center; color:#666; margin-top:5px;'>{photo['cap']}</p>",
                        unsafe_allow_html=True)
        except:
            st.caption(f"缺失图片: {photo['url']}")
        st.markdown('</div>', unsafe_allow_html=True)

# --- 7. 互动留言区 (REST API 版) ---
st.markdown("---")
st.markdown("<h3 style='text-align: center; color: #ff4b4b;'>💌 爱的留言板</h3>", unsafe_allow_html=True)
st.markdown('<div class="custom-card">', unsafe_allow_html=True)

with st.form(key="msg_form", clear_on_submit=True):
    c1, c2 = st.columns([1, 3])
    u_name = c1.text_input("署名")
    u_content = c2.text_area("寄语", placeholder="写下你的悄悄话...", height=100)
    if st.form_submit_button("🚀 发射爱心留言"):
        if u_name and u_content:
            res = save_message(u_name, u_content)
            if res and res.status_code == 201:
                st.balloons()
                st.rerun()
            else:
                st.error("由于网络延迟，留言发射失败，请稍后再试。")
        else:
            st.warning("名字和内容都要填哦~")

# 显示留言列表
st.markdown("---")
messages = get_messages()
if messages:
    for m in messages:
        st.markdown(f"""
        <div style="background: white; padding: 15px; border-radius: 12px; margin-bottom: 12px; border-left: 5px solid #ff758c; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
            <strong style="color: #ff4b4b;">{m.get('name')}</strong> <small style="color: #999;">({m.get('time')})</small><br>
            <p style="margin-top: 5px; color: #444;">{m.get('content')}</p>
        </div>
        """, unsafe_allow_html=True)
else:
    st.write("还没有留言哦，快来写下第一条吧~")
st.markdown('</div>', unsafe_allow_html=True)

# --- 8. 结尾寄语 ---
st.markdown("<br>", unsafe_allow_html=True)
cl, cr = st.columns([2, 1])
with cl:
    st.markdown("<p style='color: #888; margin-top: 30px;'>每一份回忆，都值得被温柔对待。❤️</p>", unsafe_allow_html=True)
with cr:
    st.markdown("""
    <div style="background: #fff; padding: 20px; border-radius: 15px; border: 1px dashed #ffb6c1;">
    <strong>致雅婷：</strong><br>
    Python 可以循环千遍，但我对你的爱一遍就足够恒久。<br><br>
    未来的路，我也想和你一起写下去。
    </div>
    """, unsafe_allow_html=True)