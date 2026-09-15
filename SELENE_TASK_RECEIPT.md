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
