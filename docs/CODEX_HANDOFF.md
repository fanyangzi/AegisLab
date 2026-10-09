# 本地 Codex：拉取仓库并启动网页

目标仓库为 `fanyangzi/AegisLab`。这是普通浏览器网页，不是桌面 App，不需要安装客户端；不做 Electron、Tauri、移动端或安装型 PWA。历史分支名 `feat/desktop-spatial-workspace` 只表示电脑浏览器视图。

## 1. 获取代码

先检查 `git remote -v`、`git status` 和当前分支，保护未提交工作；禁止 `reset --hard`，不得覆盖已有 `.env` 或数据库。新代码直接通过 Git 交付，不再应用之前的 ZIP 或补丁。

```bash
git fetch origin
git switch main
git pull --ff-only origin main
```

若正在检查尚未合并的重构分支，则切换 `feat/desktop-spatial-workspace`，并从同名远端分支快进拉取。仓库根目录 `index.html` 应引用 `/src/web/main.tsx`；代码包括 `src/web/Workspace.tsx` 与 `backend/app/spatial.py`，不应仍只有依赖配置改动。

## 2. 安装、验证和启动

按根目录 README 创建 Python 虚拟环境并安装依赖。Node 使用 22.12 或更新的 22.x。已有 `.env` 不要覆盖，模型密钥不放入 `VITE_*`。网页开发建议 `VITE_API_BASE_URL` 留空，通过 Vite `/api` 代理访问 API。

```bash
npm ci
python -m pip install -r backend/requirements-dev.txt
npm run test:parity
npm run build
python -m unittest discover -s tests -p 'test_*.py' -v
python tests/smoke.py
```

第一个终端执行 `uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000 --reload`，第二个终端执行 `npm run dev`。浏览器打开 `http://127.0.0.1:5173/`。初次为空工作区：可以建立自己的实验室，也可以主动导入持续标记的示例数据。

构建后同源服务：`AEGIS_SERVE_WEB=1 uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000`，浏览器访问 `http://127.0.0.1:8000/`；先停止占用同一端口的开发服务。

## 3. 必须补做的浏览器验收

在 1440×900、1600×1000、1920×1080 电脑浏览器检查三维设备、选取、旋转、缩放、聚焦、标签与连线。编译通过不能替代真实 WebGL 画面和性能验收；当前交付尚未完成真实 GPU 验收。

切换空间、关系、时间后，应保持对象与计划对应。保存候选不修改正式计划，提交候选产生新修订。更换设备后原文仍引用旧设备时必须保留待确认；未知证据不能被当成满足。

记录合格计划的服务端复核后，修改设备状态，应显示旧复核不再适用。任务完成不能自动验证资料。建立另一间实验室、另一台设备、另一份计划，确认业务不依赖样例。

实际检查刷新、关闭重开、两个标签页并发、断线和令牌错误。浏览器草稿与服务端存档必须隔离，断线不得静默回退并覆盖数据。部署前保护新旧 SQLite 数据库，公网需要 HTTPS 和访问控制。

## 4. 实施边界

整份 v5 产品规划尚未全部实现。机构多用户权限、完整化学知识图谱、专家验证安全规则包、原始二进制资料长期存储与全量历史恢复仍未完成，详见 `IMPLEMENTATION_STATUS.md`。

修复真实测试或视觉问题后，用清楚的 Git 提交记录修改。不能删除失败断言来伪造通过，也不能将静态概念图或预设动画当成三维业务实现。
