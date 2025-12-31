课设视频站（FastAPI + SQLite + 前端静态页）

仿 B 站风格的小型视频站，支持注册登录、管理员权限、视频上传/播放、点赞/收藏/投币、弹幕（含敏感词过滤、高能时刻）、评论、搜索推荐、个人资料与头像上传、后台管理等。前端为纯静态 HTML/CSS/JS，后端 FastAPI + SQLite，Nginx 提供静态资源与 /api 反代。

## 目录结构

- `main.py`：FastAPI 后端入口
- `algo.py`：AC 自动机敏感词过滤
- `static/`：前端静态页、样式、脚本
- `REPORT.md`：原始说明文档（含编码问题）
- `REPORT_UPDATED.md`：更新版说明文档（推荐阅读）

## 快速运行

```bash
cd /www/wwwroot/qiuyu.online
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install fastapi uvicorn[standard] python-multipart

# 启动（开发）
APP_SECRET=change-me ./venv/bin/uvicorn main:app --app-dir /www/wwwroot/qiuyu.online --host 0.0.0.0 --port 9000
```

Nginx 反代示例（80 -> 静态；/api -> 127.0.0.1:9000）：

```nginx
server {
    listen 80;
    server_name qiuyu.online;
    location /static/ { alias /www/wwwroot/qiuyu.online/static/; try_files $uri =404; }
    location /api/    { proxy_pass http://127.0.0.1:9000; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; }
    location /        { proxy_pass http://127.0.0.1:9000; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; }
}
```

## 部署守护（示例）

- systemd：`/etc/systemd/system/qiuyu.service` 里 ExecStart 写绝对路径 `.../venv/bin/uvicorn main:app ...`
- 宝塔进程守护：命令建议用 `/bin/bash -lc 'cd /path && APP_SECRET=... /path/venv/bin/uvicorn main:app --app-dir /path --host 0.0.0.0 --port 9000 >> /path/pm.log 2>&1'`

## 主要功能

- 用户/权限：注册、登录、退出、个人资料与头像上传，管理员区分
- 视频：上传/封面/标签/分区，播放页，热度/最新列表
- 弹幕：时间轴发送与显示，敏感词过滤（AC 自动机），暂停同步，高能时刻标注
- 评论：发布/删除（本人或管理员），分页，楼中楼一层
- 互动：点赞、收藏、投币
- 搜索与推荐：标题/标签搜索，热度/最新排序
- 后台：用户/视频/评论管理，基础统计

## 架构图生成

- Mermaid 在线：https://mermaid.live/ （见 `REPORT_UPDATED.md` 里的示例代码）
- Graphviz 在线：https://dreampuf.github.io/GraphvizOnline/

## 其他

- 默认头像数据 URI 已内置（`static/app.js` 的 `DEFAULT_AVATAR`）
- 弹幕敏感词可通过 `/api/filter/words` 维护并热更新
- 如需更多细节，参考 `REPORT_UPDATED.md`
