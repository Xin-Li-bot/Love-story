from datetime import datetime
import streamlit as st
from streamlit_timeline import timeline

# --- 1. 页面配置 ---
st.set_page_config(page_title="李欣 & 王雅婷 的恋爱纪念册", page_icon="❤️", layout="wide")
# 这样可以确保你的图片能通过 Web 访问
def get_image_url(photo_name):
    # 尝试使用 Streamlit 官方推荐的静态资源访问格式
    return f"app/static/{photo_name}"

# --- 2. 深度美化 (高级 CSS) ---
def local_css():
    st.markdown("""
        <style>
        /* 全局背景色与字体 */
        .stApp {
            background-color: #fff5f5;
            font-family: 'Microsoft YaHei', sans-serif;
        }

        /* 隐藏 Streamlit 默认页眉 */
        header {visibility: hidden;}

        /* 自定义卡片样式 - 毛玻璃感 */
        .custom-card {
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(10px);
            padding: 25px;
            border-radius: 20px;
            box-shadow: 0 10px 30px rgba(255, 182, 193, 0.3);
            margin-bottom: 25px;
            border: 1px solid rgba(255, 255, 255, 0.4);
        }

        /* 标题样式 */
        .main-title {
            color: #ff4b4b;
            text-align: center;
            font-weight: 800;
            font-size: 3rem;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.05);
        }

        /* 图片装饰 */
        .stImage img {
            border-radius: 15px;
            transition: transform 0.4s ease;
        }
        .stImage img:hover {
            transform: translateY(-5px);
        }

        /* 侧边栏样式 */
        section[data-testid="stSidebar"] {
            background-color: white;
            border-right: 1px solid #ffe4e6;
        }

        /* 爱心动效 */
        @keyframes heartBeat {
            0% { transform: scale(1); }
            14% { transform: scale(1.1); }
            28% { transform: scale(1); }
            42% { transform: scale(1.1); }
            70% { transform: scale(1); }
        }
        .heart-icon {
            display: inline-block;
            animation: heartBeat 2s infinite;
            color: #ff4b4b;
        }
        </style>
    """, unsafe_allow_html=True)


local_css()

# --- 3. 侧边栏：档案 ---
with st.sidebar:
    st.markdown("<h2 style='text-align:center;'>💖 爱情档案</h2>", unsafe_allow_html=True)
    st.image("static/20230318_初次相识.png", caption="我们的第一张合照")
    st.info("遇见你，是生命中最美好的意外。")
    st.write("---")
    st.markdown("📅 **重要日子**")
    st.write("💘 2022-12-25 正式在一起")
    st.write("🎂 08-06 雅婷的生日")
    st.write("---")
    st.write("Made with ❤️ by 世界上最爱你的人")

# --- 4. 头部氛围 ---
st.markdown("<h1 class='main-title'>👩‍❤️‍👨 我们的恋爱时光机 <span class='heart-icon'>❤️</span></h1>",
            unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888; font-size: 1.1rem;'>既然琴瑟起，何以笙箫默</p>",
            unsafe_allow_html=True)
st.write("")

# --- 5. 恋爱天数与倒计时卡片 ---
start_date = datetime(2022, 12, 25)
now = datetime.now()
days_together = (now - start_date).days

this_year_anniversary = datetime(now.year, 12, 25)
if now > this_year_anniversary:
    next_anniversary = datetime(now.year + 1, 12, 25)
else:
    next_anniversary = this_year_anniversary
days_to_anniversary = (next_anniversary - now).days

# 精修后的卡片 HTML
st.markdown(f"""
    <div style="background: linear-gradient(135deg, #ff758c 0%, #ff7eb3 100%); 
                padding: 40px; border-radius: 25px; text-align: center; color: white; 
                margin-bottom: 35px; box-shadow: 0 15px 35px rgba(255,117,140,0.3);">
        <div style="display: flex; justify-content: space-around; align-items: center; flex-wrap: wrap;">
            <div style="min-width: 200px; margin: 10px;">
                <p style="margin:0; font-size: 18px; opacity: 0.9;">我们已经相爱了</p>
                <h1 style="margin:0; font-size: 65px; color: white; border:none;">{days_together} <span style="font-size: 20px;">Days</span></h1>
            </div>
            <div style="width: 2px; height: 60px; background: rgba(255,255,255,0.3); @media (max-width: 600px) {{ display: none; }}"></div>
            <div style="min-width: 200px; margin: 10px;">
                <p style="margin:0; font-size: 18px; opacity: 0.9;">距离三周年纪念日</p>
                <h1 style="margin:0; font-size: 65px; color: white; border:none;">{days_to_anniversary} <span style="font-size: 20px;">Days</span></h1>
            </div>
        </div>
        <p style="margin-top:20px; margin-bottom:0; opacity: 0.7; font-size: 15px;">起始于 2022-12-25 · 永远陪伴</p>
    </div>
""", unsafe_allow_html=True)

# --- 6. 恋爱时光机 (时间轴) ---
st.markdown("### ⏳ 我们的回忆录")
st.markdown('<div class="custom-card">', unsafe_allow_html=True)
try:
    with open('timeline.json', "r", encoding='utf-8') as f:
        data = f.read()
        timeline(data, height=600)
except Exception as e:
    st.error(f"加载时间轴失败，请检查 timeline.json。错误信息: {e}")
st.markdown('</div>', unsafe_allow_html=True)

# --- 7. 甜蜜照片墙 ---
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
            st.markdown(
                f"<p style='text-align:center; color:#666; margin-top:10px; font-weight:bold;'>{photo['cap']}</p>",
                unsafe_allow_html=True)
        except:
            st.warning(f"图片丢失: {photo['url']}")
        st.markdown('</div>', unsafe_allow_html=True)

# --- 8. 互动寄语区 ---
st.markdown("### 💌 爱的留言板")
st.markdown('<div class="custom-card">', unsafe_allow_html=True)
col_l, col_r = st.columns([2, 1])

with col_l:
    note = st.text_area("在这写下你想说的话...", placeholder="亲爱的雅婷，今天也超爱你哦！", height=150)
    if st.button("按下这个按钮，发射爱心", use_container_width=True):
        st.balloons()
        st.snow()
        st.success("爱心和雪花都送给你！愿你每天都开心 ❤️")

with col_r:
    st.markdown("""
    **致雅婷：**

    亲爱的，

    Python 可以循环千遍，但我对你的爱一遍就足够恒久。

    这个小网页是我为你搭建的港湾，
    记录我们走过的每一步。

    未来的路，我也想和你一起写下去。
    """)

st.markdown('</div>', unsafe_allow_html=True)
