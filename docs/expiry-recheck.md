# 到期与任务截止重检（当前实现）

## 用途

`POST /api/spatial/expiry/recheck` 是一个由负责人手动触发的、可重复查询的到期重检入口。它在指定 `asOf` 时刻检查：

- 已核验资料的 `validUntil` 是否已经到期；
- `open`、`submitted`、`reopened` 任务的 `dueAt` 是否已经到期；
- 当前未归档、未取消计划是否因适用资料失效或最近复核基线变化而需要重新检查。

重检结果写入现有 `spatial_jobs` 持久化表，`kind` 为 `expiry_recheck`。相同 `requestId` 重试时返回同一份结果，不重复计算或生成多条记录。结果包含 `asOf`、受影响资料、任务、计划及下一步建议，便于浏览器刷新后继续查看。

## 边界

当前实现是**手动同步重检**，返回中明确标记 `trigger: manual`、`worker: not-running`。它没有假装已经接入后台 Worker、消息队列、通知渠道或自动调度；不会自动批准、取消计划、修改证据状态或创建任务。负责人需根据报告手动补证、修订或重新复核。

这是 F07/C09/D08 的可验证增量：到期语义、计划影响判断、持久 Job 和幂等重试已经有服务端闭环；真正后台 Worker/outbox、通知与自动任务生成仍列为后续未完成项。

## 示例调用

```bash
curl -X POST http://127.0.0.1:8000/api/spatial/expiry/recheck \
  -H 'Content-Type: application/json' \
  -d '{"requestId":"expiry-review-20261011-01","asOf":"2026-10-11T00:00:00+08:00"}'
```

省略 `asOf` 时使用服务端当前 UTC 时间；验收、审计和事故复盘应传入带时区的固定时间，以便重现同一结果。响应中的 `jobId` 可通过 `GET /api/spatial/jobs/{jobId}` 查询。

## 验证

`tests/test_spatial.py` 覆盖：

- 资料到期、任务逾期与受影响计划的报告字段；
- Job 持久化、终态不可变和同一 `requestId` 幂等重试；
- API 手动触发、`worker: not-running` 边界和无时区时间拒绝。
