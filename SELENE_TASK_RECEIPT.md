# Selene bug 工单回执：phase 判断逻辑错误

日期：2026-09-15

## 已修改

- 修复 `selene_status` 使用的 `cycle.current_phase`：有 `end_date` 时，开始日到结束日（含首尾）判断为 menstrual。
- 结束日之后按距预测下次经期天数判断：大于 14 为 follicular，8 至 14 为 ovulation，小于 8 为 luteal。
- 未填写结束日期时保留原有估算；保留原有无记录及周期日超出有效范围的 unknown 处理。
- 接口字段与存储结构不变。

## 验证

- `python -m unittest test_cycle -v`：4 项测试通过，包括日期边界、提前结束、缺失结束日期兼容及直接调用 selene_status。
- 指定案例：start=2026-08-21，end=2026-08-26，模拟 today=2026-09-11；接口返回 phase=luteal、days_left=7、next_date=2026-09-18（单条记录使用默认 28 天周期）。
- `git diff --check` 通过。该修改为 Python 后端，无 npm 构建步骤。
- 测试使用模拟数据，未写入真实数据库。

## 下一步与卡点

- 本地修复完成，待甲方验收；尚未部署到运行中的服务。
- 无阻塞。接口测试时依赖库出现 Pydantic 类型定义警告，不影响本次测试通过。

## 后续四项修复（2026-09-15，甲方已授权）

- 网页保存经期日期时，在同一事务中更新 periods；同一开始日期重复保存不重复新增，保留疼痛、备注等字段。网页读取最新 periods，反映 MCP 的修改。新开始日期保留为新一轮历史记录。
- 加入服务启动时的一次性旧配置导入：仅在没有经期记录或旧网页开始日期更新时导入，不覆盖同日及更新的 MCP 记录，不复活已删除的记录。
- get_periods 改为先取最近 N 条，再按开始日期升序返回，解决第 13 条之后被忽略的问题。
- 网页实际阶段使用后端 phaseByDay，通过 React Context 提供给各组件；日期不再按周期取余数。日历阶段按实际开始日期计算，预测使用已保存的周期长度。手动设置周期长度时，MCP 与网页使用同一长度；未设置则按历史平均计算。
- 到达预测日期且未记录新经期时，提醒模块及 MCP 文案进入 due_check，不依赖 phase=unknown；phase 本身继续遵守上一份工单。
- 同步更新 REST 部署副本与浏览器 JS 产物；无真实数据库改写、无外部推送、无部署。

验证：`python -m unittest test_cycle test_status_sync -q`（10 项通过）；`node transpile.js`、`node test_frontend.cjs`、`node --check selene_browser.js`、`git diff --check` 通过。前端执行检查为 Node 模拟环境，未做真实浏览器视觉验收。

下一步：甲方验收及部署后联调。原有 Pydantic 依赖警告仍存在，无本次修复阻塞。
