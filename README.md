# AegisLab

**实验安全协同工作台 · 浏览器网页系统**

把实验计划、设备、使用时段和检查依据连接到同一个工作区。空间、关系与时间共用同一份数据，条件变化后重新计算检查结果，并保留人工记录。

本项目是通过网址访问的 **Web 网站**，不是桌面安装程序。没有 Electron、Tauri、移动端、PWA 安装包，也不需要使用者安装客户端。

## 本次代码中的主要能力

| 工作面 | 实际操作 |
| --- | --- |
| 空间 | 可配置实验室和设备；Three.js 场景、对象选取、缩放与聚焦；WebGL 不可用时二维回退 |
| 关系 | 计划—资源—资料的可点击关联；同一实体与右侧详情联动 |
| 时间 | 并发预约、维护窗口、按日期查看；交叠的时间条分行展示 |
| 计划 | TXT / Markdown、DOCX、文本层 PDF 导入；原文行号、确认、资源安排、版本与辅助预审 |
| 方案 | 独立候选、约束重检、保存、提交为新修订；基线改变后拒绝应用旧方案 |
| 协同与资料 | 任务进度、原文证据、明确核验；上传或任务完成不会自动使证据通过 |
| 复核与记录 | 服务端重新检查条件，记录当前版本资源复核；事实变化使旧记录不再适用；JSON 导出 |

检查范围是已登记的资源前置条件，不是完整化学安全认证。模型只辅助解释，不执行文档中的命令、不自动批准实验。完整终版规划中尚未实现的部分见 [实现状态](docs/IMPLEMENTATION_STATUS.md)。

## 本地开发：打开网页

使用 Node.js 22.12 或更新的 22.x，以及 Python 3.12。以下依赖是开发/部署环境依赖，不是给最终使用者安装的客户端。

```bash
npm ci
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
test -f .env || cp .env.example .env
```

已有 `.env` 时不要覆盖。新网页建议令 `VITE_API_BASE_URL` 留空，由 Vite 的 `/api` 代理连接本机 API；不要把模型密钥放进任何 `VITE_*` 变量。

第一个终端：

```bash
source .venv/bin/activate
uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000 --reload
```

第二个终端：

```bash
npm run dev
```

在浏览器打开 `http://127.0.0.1:5173/`。这是网页地址，不是安装入口。初次打开是空工作区，可建立自己的实验室，也可主动导入明确标记的示例。没有 API 时可编辑独立的浏览器草稿，但不能记录服务端正式复核。

Windows 可用 `.venv\Scripts\Activate.ps1` 激活虚拟环境；其余 Python 与 npm 命令相同。

## 构建后：同源网站服务

```bash
npm run build
AEGIS_SERVE_WEB=1 uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/`。FastAPI 同时提供构建后的网页和 API。另一个正在占用 8000 端口的开发 API 应先停止。

公网部署必须通过 HTTPS 和访问控制；设置 `AEGIS_WORKSPACE_TOKEN` 后，打开网页，在“设置”输入该令牌连接服务端。令牌只保留在页面内存。当前访问控制是单一工作区负责人模式，不是机构 SSO、多角色授权或多租户隔离。未配置令牌时只允许本机请求，不建议直接暴露端口。

## 模型连接

在服务端 `.env` 中填写自己控制的 `LABSAFETY_LLM_BASE_URL`、`LABSAFETY_LLM_MODEL` 和 `LABSAFETY_LLM_API_KEY`。三个值都配置后才启用模型请求；没有预置第三方网关或猜测的模型名。选择一项计划的“SOP 辅助预审”后按需触发。模型不可用时明确显示确定性回退，不伪装成在线 AI 结果。

## 测试

```bash
npm run test:parity
npm run build
python -m unittest discover -s tests -p 'test_*.py' -v
python tests/smoke.py
```

前端的规则计算与后端校验有对照测试。后端覆盖持久化、并发修订、幂等、资料提取、访问控制和网站同源路由。测试范围与尚未完成的浏览器验收见 [测试说明](docs/TEST_REPORT.md)。

## 数据与迁移

网页新存档使用 `AEGIS_SPATIAL_DB_PATH`；旧审查库使用 `LABSAFETY_DB_PATH`，两者不会互相覆盖。停止服务后备份 SQLite 文件，恢复时保持配置路径一致。JSON 导出用于记录查看和人工迁移，**当前没有完成自动导入恢复与旧库全量迁移**。

旧界面和接口保留用于迁移检查，入口为 `legacy.html`，不在新产品导航中展示。历史 `eval/` 仍是独立的合成基线，不能当作本次网页的真实应用效果指标。示例工作区不是现场实验数据或安全结论。

[本地 Codex 接手说明](docs/CODEX_HANDOFF.md) · [实现状态](docs/IMPLEMENTATION_STATUS.md) · [测试记录与限制](docs/TEST_REPORT.md)
