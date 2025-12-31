课设系统说明文档

> 本版为结构完整的 Markdown 说明文档，覆盖需求、设计、实现、测试与总结，后续可按段落继续扩写。
> 项目代码位于 `main.py`、`algo.py`、`static/` 前端文件夹，后端采用 FastAPI + SQLite，前端为类 B 站风格的静态页（HTML/CSS/JS）。

## 1 问题描述及需求分析

### 1.1 问题描述

设计并实现一个仿 B 站的在线视频平台，支持用户注册登录、权限区分（管理员/普通用户）、视频上传与播放、点赞收藏投币、弹幕与评论、搜索与推荐、后台管理、个人中心资料修改与头像上传、分区标签体系、历史/稍后再看（可拓展）、消息与高能弹幕显示等核心体验。

### 1.2 相关文献资料

- FastAPI 官方文档：https://fastapi.tiangolo.com/（异步接口、依赖注入、安全、CORS）
- SQLite 官方文档：https://www.sqlite.org/docs.html（轻量级嵌入式数据库，适合课程项目快速开发）
- Starlette CORS 中间件说明：https://www.starlette.io/middleware/#corsmiddleware（跨域响应头配置）
- Uvicorn ASGI Server：https://www.uvicorn.org/（服务启动参数、性能建议）
- Nginx 官方文档：https://nginx.org/en/docs/（反向代理、静态资源、缓存与压缩）
- AC 自动机多模式匹配原理（参考文章示例：https://cp-algorithms.com/string/aho_corasick.html）
- 前端交互与布局参考（B 站风格）：官方站点与社区设计文章（示例：https://web.dev/learn/css/，https://developer.mozilla.org/zh-CN/docs/Learn/JavaScript）

### 1.3 需求分析

- 输入：
  - 用户侧：注册/登录（用户名、密码）、个人资料（昵称、签名、性别/地区、头像上传）、互动行为（点赞/收藏/投币）、弹幕与评论内容、搜索关键词。
  - 内容侧：视频文件及元数据（标题、简介、封面、分区、标签）、可选的分区/标签维护、过滤词维护。
- 处理：
  - 鉴权与权限：登录发放 token，区分普通用户/管理员，接口按角色授权。
  - 内容存储：视频/封面上传保存到 `static/uploads`，元数据入库；播放页按 ID 读取。
  - 弹幕：发送时记录播放时间，写库；拉取时按时间排序；敏感词用 AC 自动机过滤；暂停时前端暂停弹幕动画；统计高能时刻。
  - 评论：发布/删除（本人或管理员），楼中楼一层，分页返回。
  - 互动：点赞/收藏/投币写关系表并更新视频热度。
  - 搜索与推荐：标题/标签关键词搜索；推荐按热度；最新按时间。
  - 后台：用户封禁/重置、视频下架/删除、评论删除、统计（用户数、视频数、热门 TopN）。
  - 资料与头像：个人中心上传头像（保存 URL），修改昵称/签名等。
  - 安全与校验：输入校验、文件类型/大小限制、CORS 配置、防未登录操作、基础限流可扩展。
- 输出：
  - 统一 JSON：`code/message/data`。
  - 页面：视频列表、详情、弹幕流/高能列表、评论列表、个人资料、后台管理表格、搜索结果。
  - 错误提示：登录态失效、权限不足、上传失败（权限或类型）、敏感词提示等。

## 2 总体设计

### 2.1 算法设计思路

- 弹幕敏感词：使用 AC 自动机（`algo.py`）预处理关键词，发送弹幕时 O(n) 过滤。
- 推荐/排序：基础版本按照热度（播放+互动加权）与时间排序，接口 `/api/recommend`、`/api/videos?order=new`。
- 弹幕时间轴：发送时记录视频当前播放时间，播放时按时间拉取并渲染，暂停时暂停弹幕动画。

### 2.2 总体设计图（文字描述）

- 前端静态资源：`static/index.html`、`video.html`、`profile.html`、`style.css`、`app.js`、`home.js`、`script.js`。Nginx 直接服务静态文件，反代 `/api` 到 Uvicorn。
- 后端 API：FastAPI（`main.py`），路由分为认证、用户、视频、弹幕、评论、后台管理、过滤词配置等。
- 数据层：SQLite 本地文件（`data.db`），通过简单的表结构实现用户、视频、互动、弹幕、评论等。
- 算法模块：`algo.py` 提供 AC 自动机的构建与过滤接口。

## 3 详细设计

### 3.1 相关数据定义

表 3-1 数据定义（核心字段与含义）


| 变量/表                                                                                                    | 说明                           | 类型/示例 |
| ---------------------------------------------------------------------------------------------------------- | ------------------------------ | --------- |
| users(id, username, password, role, avatar, nickname, signature)                                           | 用户表，角色区分 admin/user    | INT/STR   |
| videos(id, title, desc, cover, tags, area, plays, likes, coins, favorites, user_id, created_at, file_path) | 视频元数据                     | INT/STR   |
| danmaku(id, video_id, user_id, content, time, color, created_at)                                           | 弹幕时间轴                     | INT/STR   |
| comments(id, video_id, user_id, content, parent_id, created_at)                                            | 评论楼层                       | INT/STR   |
| favorites(id, user_id, video_id)                                                                           | 收藏关系                       | INT       |
| likes(id, user_id, video_id)                                                                               | 点赞关系                       | INT       |
| history(id, user_id, video_id, progress, created_at)                                                       | 历史记录                       | INT/STR   |
| filter_words(text)                                                                                         | 敏感词集合，用于 AC 自动机构建 | TEXT      |
| DEFAULT_AVATAR                                                                                             | 默认头像                       | data URI  |
| APP_SECRET                                                                                                 | 签名密钥/会话加密              | env       |

### 3.2 各函数的功能设计

#### 3.2.1 主要后端函数/路由模块


| 路由/函数                           | 功能描述                 | 关键参数                             | 返回           |
| ----------------------------------- | ------------------------ | ------------------------------------ | -------------- |
| `/api/auth/register`                | 注册用户                 | username, password                   | token/用户信息 |
| `/api/auth/login`                   | 登录获取 token           | username, password                   | token/用户信息 |
| `/api/auth/me`                      | 获取当前登录信息         | Header: Authorization                | 用户信息       |
| `/api/user/profile` PUT             | 更新头像/昵称/签名/地区  | multipart/form-data                  | 更新后信息     |
| `/api/videos/upload`                | 上传视频+封面元数据      | file, cover, title, tags, area, desc | 视频ID         |
| `/api/videos/{id}` GET              | 视频详情（含 UP 主信息） | id                                   | 视频对象       |
| `/api/videos/{id}/danmaku` GET/POST | 获取/发送弹幕            | video_id, time, content              | 列表/成功      |
| `/api/videos/{id}/comments`         | 发表评论/删评论          | content, parent_id                   | 列表/成功      |
| `/api/like` `/api/fav` `/api/coin`  | 点赞/收藏/投币           | video_id                             | 成功           |
| `/api/recommend`                    | 热度推荐                 | -                                    | 视频列表       |
| `/api/videos?order=new`             | 最新投稿                 | -                                    | 视频列表       |
| `/api/admin/*`                      | 用户封禁/视频下架/统计   | 需 admin 角色                        | 结果/统计      |
| `/api/filter/words`                 | 设置/获取敏感词          | words                                | 过滤结果       |

#### 3.2.2 函数间调用关系（示例）

- 认证依赖：所有需要登录的接口通过 `Depends(auth_user)` 校验 token。
- 弹幕发送：`auth_user` -> `ac_filter(content)` -> 数据库写入 -> 前端轮询/渲染。
- 视频详情：`get_video` -> 关联查询 UP 主信息 -> 返回前端用于展示头像/昵称。
- 过滤词设置：`set_filter_words` (algo) -> 构建 AC 自动机 -> 保存词表。

#### 3.2.3 关键算法改进

- AC 自动机在服务启动时加载敏感词，发送弹幕时只做 O(n) 匹配替换，避免逐词扫描。
- 弹幕暂停：前端在视频 pause 时暂停动画（CSS/JS 控制）；播放恢复时继续滚动。
- 高能弹幕：按同一时间窗弹幕数统计，标注高能时刻列表（侧边栏显示）。
