# Love-story · 恋爱纪念时光轴

一个记录两个人故事的纪念网站：时间轴、照片墙、留言板与背景音乐。

## 技术栈

- **后端**：FastAPI（`main.py`），SQLite 存储，`timeline.json` 提供时间轴数据
- **前端**：单文件 `index.html`（Tailwind CDN + Lucide 图标 + canvas-confetti），无需构建
- **数据管理**：`init_db.py` 初始化数据库，`update_timeline.py` 更新时间轴
- **可选**：`Love story.py`（Streamlit 版本）、LeanCloud 留言、`photos/` 照片资源

## 本地运行

```bash
pip install -r requirements.txt
python init_db.py         # 首次初始化数据库
uvicorn main:app --host 0.0.0.0 --port 8000
```

浏览器访问 `http://localhost:8000` 即可。

---

## ✨ Apple Design 流畅交互重构

本项目前端参考了 Apple《Designing Fluid Interfaces》(WWDC 2018) 的设计原则
（实践来源：[emilkowalski/skills · apple-design](https://github.com/emilkowalski/skills)），
对 `index.html` 的动画与交互进行了系统性重构。

**核心目标**：让网页交互接近原生 App 的流畅度与自然感，同时**零新增依赖、零构建步骤**，
不引入 Motion/Framer Motion 等需要打包的库——因此对服务器**内存零增量**，适配低配环境。

### 落地的设计原则

| 模块 | 对应原则 | 实现方式 |
| --- | --- | --- |
| **弹簧引擎** | 弹簧行为 | 内联 ~2KB 原生 RAF 引擎，采用 Apple 的 `damping` + `response` 双参数模型，支持注入初速度与随时 retarget |
| **按钮反馈** | 响应速度 < 100ms | `:active { transform: scale(0.96); 60ms }` + `touch-action: manipulation` 消除移动端点击延迟 |
| **Lightbox 滑动** | 手势速度 / 速度接力 / 动量投影 / 橡皮筋 | Pointer Events 实现 1:1 跟手拖拽，松手后按投影距离决定翻页，首/尾边缘带橡皮筋阻尼 |
| **Modal / Lightbox** | 可中断性 / 材质化登场 | 由 `display` 硬切换改为 `opacity + visibility + backdrop-blur + scale` 过渡，动画可随时被打断 |
| **抽屉菜单** | 进出对称 | 顶部滑入 / 沿原路径退回，使用自然缓动曲线而非瞬时显隐 |
| **动效降级** | 尊重系统偏好 | `prefers-reduced-motion` 从「全部砍到 0.01ms」改为柔和的透明度交叉淡入，并停用易致眩晕的循环动画 |

### 关键性能指标

- **响应速度**：所有按压反馈在 100ms 内触发
- **可中断性**：任何进行中的动画都能被新手势/点击立即接管
- **手势速度**：滑动位移与手指速度 1:1 匹配，松手后按物理动量续动
- **弹簧行为**：使用临界/欠阻尼弹簧曲线，避免生硬的线性过渡

> 本次重构遵循「只增不减」原则：所有原有功能（时间轴、后台管理、留言、音乐播放、图片缩放）完全保留，仅新增更细腻的交互体验。
