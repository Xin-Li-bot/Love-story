import streamlit as st
import json
from streamlit_timeline import timeline
from datetime import datetime

# --- 页面配置 ---
st.set_page_config(
    page_title="我们的恋爱纪念册",
    page_icon="❤️",
    layout="wide"
)

# --- 侧边栏：音乐与设置 ---
with st.sidebar:
    st.title("💖 关于我们")
    st.info("这是专属你的恋爱网站")
    # 这里可以放一首背景音乐 (支持 mp3)
    # st.audio("love_song.mp3", format='audio/mp3')
    st.write("---")
    st.write("Made with ❤️ by BoyFriend 李欣")

# --- 标题与倒计时 ---
st.title("👩‍❤️‍👨 Love Story")
st.markdown("### 记录我们需要铭记的每一个瞬间")

# 计算在一起的天数
start_date = datetime(2022, 12, 25)  # 这里 2023, 5, 20 分别是年、月、日
 # 修改为你们在一起的日期 (年, 月, 日)
current_date = datetime.now()
days_together = (current_date - start_date).days

col1, col2, col3 = st.columns(3)
with col2:
    st.metric(label="我们已经相爱了", value=f"{days_together} 天", delta="每一天都值得珍惜")

st.write("---")

# [...](asc_slot://start-slot-13)--- 恋爱时光机 (时间轴) ---
st.header("⏳ 恋爱时光机")

# 读取 timeline.json 文件
try:
    with open('timeline.json', "r", encoding='utf-8') as f:
        data = f.read()
        timeline(data, height=500)
except FileNotFoundError:
    st.error("请确保 timeline.json 文件存在！")

st.write("---")

# [...](asc_slot://start-slot-15)--- 甜蜜瞬间 (照片墙) ---
st.header("📸 甜蜜瞬间")
st.write("这里存放我们最美的回忆...")

# 这里可以使用 st.file_uploader 让用户上传，或者直接读取本地文件夹
# [...](asc_slot://start-slot-17)为了展示效果，这里演示简单的列布局
col1, col2, col3 = st.columns(3)

with col1:
    st.image("https://images.unsplash.com/photo-1518199266791-5375a83190b7", caption="第一次旅行")
    # [...](asc_slot://start-slot-19)如果是本地图片，使用路径: st.image("images/photo1.jpg")

with col2:
    st.image("https://images.unsplash.com/photo-1621112904891-2867e0ce5854", caption="你的生日")

with col3:
    st.image("https://images.unsplash.com/photo-1529333166437-7750a6dd5a70", caption="搞怪合影")

st.write("---")

# --- 写给未来的信 ---
st.header("💌 写给未来的我们")
with st.expander("点击展开读信"):
    st.markdown("""
    亲爱的，

    当你看到这个网页的时候，我想告诉你，为你写代码是我做过最浪漫的事。
    Python 可以循环千遍，但我对你的爱一遍就足够恒久。

    ... (在这里编辑你的情书) ...
    """)

# [...](asc_slot://start-slot-21)简单的互动区
st.text_area("你想对我说什么？(虽然这里无法永久保存，但截图给我看吧！)", height=100)
if st.button("发送爱心"):
    st.balloons()
    st.success("爱心发射成功！❤️")

