在线体验：https://ai-wardrobe-itfa.onrender.com

| 模块 | 说明 |
|---|---|
| 账号体系 | 注册 / 登录，密码 SHA256 加盐哈希存储，不存明文 |
| 身体数据 | 性别、身高、体重、肩宽 / 胸围 / 腰围 / 臀围，作为搭配的身材约束 |
| 衣橱录入 | 支持拍照、相册两种入口；服务端自动压缩后入库 |
| 多维标签 | 6 类分类（上装/下装/连衣裙/外套/鞋子/配饰）、8 种材质、5 种版型、10 种颜色 |
| 衣橱管理 | 按分类筛选浏览、删除（同时清理图片文件） |
| AI 搭配 | 输入温度 + 天气 + 场景（通勤/约会/设计感…）+ 自由补充，由豆包生成「主推 + 备选」两套方案 |
| 容错降级 | 大模型不可用时自动切换规则推荐引擎，用户侧永远不白屏 |

技术栈
- 后端：Python 3.12 / Flask
- 数据层：MySQL（生产）/ SQLite（本地零配置），自研统一访问层一套代码双引擎
- 图片处理：Pillow（上传即压缩）
- 大模型：火山方舟 · 豆包（Chat Completions API，支持预置模型名或 ep-xxx 推理接入点）
- 部署：Render（Gunicorn + 环境变量注入密钥）

## 项目结构

```
v3-wardrobe/
├── app.py                  # 路由层 + 业务逻辑 + 大模型调用
├── db.py                   # 数据库抽象层（MySQL / SQLite 双引擎）
├── requirements.txt        # 依赖清单
├── templates/              # 页面模板
│   ├── base.html           # 公共布局 + 底部导航
│   ├── auth.html           # 注册 / 登录
│   ├── profile.html        # 身体数据
│   ├── add.html            # 添加衣服（拍照 / 相册双入口）
│   ├── wardrobe.html       # 我的衣橱
│   └── outfit.html         # 今日穿搭 + AI 结果
└── static/uploads/         # 用户衣服图片
```


1.图片压缩实测：

| 原始体积 | 压缩后 | 降幅 |
|---|---|---|
| 3068 KB | 112 KB | 96% |
| 2092 KB | 51 KB | 98% |
| 2428 KB | 73 KB | 97% |

2.环境变量说明：

| 环境变量 | 作用 | 缺省行为 |
|---|---|---|
| `MYSQL_HOST` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DB` | 切换 MySQL | 不设置则用 SQLite |
| `ARK_API_KEY` | 豆包 API Key | 不设置则使用内置规则推荐 |
| `ARK_MODEL` | 模型名或接入点 ID | 默认 `doubao-1-5-pro-32k-250115` |

3.Render部署配置：

| 配置项 | 值 |
|---|---|
| Root Directory | `v3-wardrobe` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn -w 2 -b 0.0.0.0:$PORT app:app` |
| 环境变量 | `ARK_API_KEY`、`ARK_MODEL`、`PYTHON_VERSION=3.12.6` |

后续规划
- 当前版本已经采集身高、体重、三围等身体数据并注入 Prompt，但存在一个体验断层：用户填完数据后，页面没有任何反馈，也感知不到它如何影响搭配结论。下一步的迭代重点，就是把“数据”真正变成“个性化体验”，
让身体数据可感知。
- 搭配方案收藏与历史记录
- 拍照自动识别分类 / 颜色 / 材质（多模态模型），降低录入成本（当前最大摩擦点）
- 每日天气自动获取，省去手填温度
