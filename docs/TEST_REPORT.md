# 网页工作区测试记录与限制

记录日期：2026-10-09。以下为发布源码前在工作环境实际重跑的结果。GitHub 远端构建的状态应另外查看对应提交的 Actions 运行，不能用本表替代某次 CI 结果。

| 检查 | 已完成的本地结果 |
| --- | --- |
| `npm run test:parity` | 30 项前端领域断言通过，生成 TypeScript/Python 对照输入 |
| `npm run build` | TypeScript 检查与 Vite 生产构建通过 |
| `python -m unittest discover -s tests -p 'test_*.py' -v` | 34 项测试通过，包含领域、SQLite、并发、幂等、API、文档提取、前后端对照及构建网站路由 |
| `python tests/smoke.py` | 原有服务 smoke 通过 |

自动化入口为 `.github/workflows/desktop-web.yml`，显示名为 **Web workspace verification**。先安装锁定依赖，再生成对照数据、构建网页、运行 Python 与旧服务检查；不使用 `--if-present` 隐藏缺失测试。产物只包含 `dist/`，不发布环境密钥、SQLite 数据库或 node_modules。

## 尚未完成的验证

当前环境没有完成真实 WebGL/GPU 画面、帧率和长时间内存验收。Three.js 编译与二维回退不等于真实三维视觉已通过验收。此前的组件/API 检查使用测试桥和存档替身，不能代替真实站点导航、浏览器刷新持久化和生产部署测试。

未调用真实模型服务；已覆盖明确的确定性回退以及辅助预审不修改工作区。没有测量真实实验室应用收益，不将合成样例或接口测试换算为化学安全、准确率或事故下降数据。

## 当前构建提示

Three.js 场景异步分块约 540 kB（未压缩），会触发 Vite 的 500 kB 提示；这是待优化事项，不是编译失败，也没有提高警告阈值掩盖它。

当前访问控制是单负责人令牌/本机模式，不是机构多账号授权。原数据库与新工作区数据库相互隔离；部署和拉取代码不应清空任何用户存档。
