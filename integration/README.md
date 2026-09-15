# Selene ↔ Memora 联动修复

## 本地改动与配套文件

本次同时修改了 `Selene/` 与相邻 `Memora/` 的代码。Memora 目录未初始化 Git，因此在 Selene 仓库中额外保存：

- `selene_gateway.py`：与本地 Memora 网关一致的完整文件，部署目标为 `Memora/selene_gateway.py`。
- `memora_server.patch`：Memora 服务端的增量补丁，包含来源记录、重试去重和同步结果。

配套部署时先停止两端旧服务，并备份 Selene 与 Memora 数据库，再更新两端代码。部署前在 Memora 目录检查补丁：

```text
git apply --check --ignore-space-change /path/to/Selene/integration/memora_server.patch
```

确认版本匹配后应用补丁并替换网关，再启动两端服务。当前本地 Memora 文件已经修改，无需再次应用。应用过的版本可用 `git apply --reverse --check --ignore-space-change ...` 验证。此处未执行部署或改动真实数据库。

## 同步约定

- 网页/人工记录标记 `manual`。自动识别不会覆盖人工或来源不明的旧评分。
- 自动情绪标记 `memora`；自动与人工症状合并标记 `mixed`。人工明确的空症状、状态良好不会被自动推翻。
- `log_sources` 保存当前记录来源、关联记忆 ID；`memora_sync_events` 保留每次已处理记忆的结果。`/get_logs` 新增 `logSources`，旧字段保留。
- 每次同步按 `event_date` 保存，历史日期参考当时的经期；没有经期记录也可保存情绪，辅助周期日为 0。非法日期不回退到今天。
- 否定词过滤对应情绪/症状；混合且矛盾的情绪跳过估算。调用者明确提供 `mood` 时优先使用。规则识别无法覆盖所有自然语言表达，网页将自动评分标为“自动估算”，可人工修改。
- Selene 发往 Memora 的消息带 `source=selene`，不会再次回写；旧版 `【Selene…` 前缀也阻止回流。
- Memora `memory_origins` 保存来源及唯一 `source_key`。同一来源事件重复请求返回同一记忆 ID，不再新增记忆。
- Selene 的来源键包含持久化数据库标识；每日按日期、月报按月份、关怀按内容生成稳定键，支持超时后重试。

## 联动行为

- Memora 网关复用独立 Selene 工具实现，周期设置及逾期提醒一致。
- 网页低情绪保存成功后再异步触发关怀，失败不影响原记录；进入首页读取近期相关记忆，不高频轮询。
- 出站症状仅保留白名单，自定义症状不随关怀/每日摘要传到 Memora。
- 只有确认远端返回成功及记忆 ID 才标记发送成功。失败的每日摘要可在次日继续重试。
- 月报生成上个月内容，支持跨年、错过整点后补发及已失败旧月报重试。
- MCP 客户端兼容 JSON/SSE；会话失效时重建；传输超时返回失败，由稳定来源键保护后续重试。

## 验证

在 Selene 目录运行：

```text
python -m unittest test_cycle test_status_sync test_log_dates test_memora_integration test_memora_client -q
node transpile.js
node --check selene_browser.js
node test_frontend.cjs
node test_log_frontend.cjs
```

联动测试使用临时双数据库及模拟 HTTP，不连接真实 Memora、不写真实记录、不发送外部消息。覆盖评分保护、否定句、症状合并、历史补记、回流阻断、超时后去重、月份切换、网关一致性、会话恢复以及部署版静态页面。

当前没有可连接浏览器，视觉验收及真实部署环境联调仍需在部署时进行。
