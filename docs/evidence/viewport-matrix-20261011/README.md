# AegisLab 三档桌面视口验收记录

- **日期**：2026-10-11（Asia/Shanghai）
- **页面**：`http://127.0.0.1:5173/?page=space&view=space&lab=lab-201&object=equipment%3AB-01&date=2026-10-09`
- **入口**：实际运行的 Vite 开发服务器，不是概念图或静态导出。
- **浏览器检查**：Chrome DevTools MCP 连接的 Chromium，`devicePixelRatio=1`。
- **工作区数据**：服务端返回 `示例数据 · 非现场记录`；本次仅读，不写入数据库。
- **代码基线**：`HEAD=9cf12f2`；采集时工作树另有后续未提交代码改动，见同日 `git status`。

## 验收操作

1. 打开页面并等待 `/api/spatial` 返回 200。
2. 依次设置浏览器视口为 1440×900、1600×1000、1920×1080。
3. 每档执行可访问性树快照、页面脚本几何检查和真实页面截图。
4. 几何检查确认 `body.scrollWidth === innerWidth`、`body.scrollHeight === innerHeight`，并确认 `canvas` 和主标题存在。
5. `npm run build` 与 `npm run test:parity` 在同一工作树执行。

## 结果

| 视口 | 页面尺寸 | body 尺寸 | 横向溢出 | Canvas | 关键页面 | 截图 |
| --- | ---: | ---: | --- | --- | --- | --- |
| 1440×900 | 1440×900 | 1440×900 | 否 | 存在 | AegisLab / 有机分析与前处理实验室 · 201 | [space-1440x900.png](./space-1440x900.png) |
| 1600×1000 | 1600×1000 | 1600×1000 | 否 | 存在 | AegisLab / 有机分析与前处理实验室 · 201 | [space-1600x1000.png](./space-1600x1000.png) |
| 1920×1080 | 1920×1080 | 1920×1080 | 否 | 存在 | AegisLab / 有机分析与前处理实验室 · 201 | [space-1920x1080.png](./space-1920x1080.png) |

脚本返回的三档摘要（原始输出）为：

```json
{"innerWidth":1440,"innerHeight":900,"bodyScrollWidth":1440,"bodyScrollHeight":900,"rootOverflow":false,"title":"AegisLab · 实验安全协同工作台","hasWorkspace":true,"buttons":80}
{"innerWidth":1600,"innerHeight":1000,"bodyScrollWidth":1600,"bodyScrollHeight":1000,"rootOverflow":false,"title":"AegisLab · 实验安全协同工作台","hasWorkspace":true,"buttons":80}
{"innerWidth":1920,"innerHeight":1080,"bodyScrollWidth":1920,"bodyScrollHeight":1080,"rootOverflow":false,"title":"AegisLab · 实验安全协同工作台","hasWorkspace":true,"buttons":80}
```

可访问性树在三档均能看到五个业务入口（空间、计划、协同、资料、资源）、空间／关系／时间切换、三维 Canvas、对象清单及右侧资源详情。页面网络请求中 `/api/spatial` 为 200；开发服务器热更新资源返回 304 属正常缓存行为。

## 构建与领域回归

```text
npm run build                 PASS
npm run test:parity           PASS — 30 browser-domain tests
```

构建仍报告 Three.js 场景 chunk 大于 500 kB 的性能提示；这不是本次视口验收的通过条件，后续应按 W07/W08 继续做模型分包和真实 GPU 性能记录。

## 边界

- 本记录证明三档桌面视口在当前开发环境能渲染、无页面级横向溢出且关键入口可见；不等价于 16 GB 集显设备的 30 FPS，也不替代窄屏、WebGL 禁用、键盘、权限或完整端到端写入测试。
- 截图中的“示例数据 · 非现场记录”是应用明确标识，不是现场部署或安全认证证据。
