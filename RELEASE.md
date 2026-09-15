# 第三批：本地验收与部署准备

日期：2026-09-15。范围：经期快捷操作、网页/REST/MCP 完整流程、迁移恢复和交付准备。

## 已验证

- 独立 Edge 无头浏览器实际运行 index.html 与转译 JS；使用临时 SQLite、随机本机端口启动真实 REST 和 MCP 服务。
- 网页补记开始 → 记录结束 → MCP 初始化并调用 selene_status/selene_history → 刷新 → 记录新一轮 → 网页展开上一轮历史，全链路通过。
- 验证重复点击、误点撤销，以及服务已提交但浏览器未收到响应时保留日期、以相同请求标识重试而不重复插入。
- 390px 手机视口无横向溢出，无页面 JavaScript 异常；截图保存在系统临时目录 selene-release-mobile.png。
- 旧业务库仅通过只读连接备份到临时目录演练：5 条情绪、3 条症状原记录逐行保留；迁移、重复启动、备份恢复、再次升级均通过，原库 SHA256 不变。
- 日期缺失记录仍留在旧表，不能据此声称已恢复到日历。具体规则见 LOG_DATE_MIGRATION.md。

内置浏览器未连接，本次使用安装的 Edge 和 Playwright 验收。四个外部脚本使用预下载的固定版本测试副本；尚未验证目标服务器到 CDN 的网络可用性。后台定时任务和 Memora 网络调用在此测试中被隔离；Memora 双库联动由既有回归测试覆盖，不代表生产服务已联调。

## 可复现命令

在 Selene 目录运行。普通自动化测试均使用临时数据库；旧 test_rest.py 已禁用直接写入默认 8010 服务的行为。

```text
python -m unittest discover -q
node transpile.js
node --check selene_browser.js
node test_frontend.cjs
node test_log_frontend.cjs
node test_period_frontend.cjs
git diff --check
```

真实浏览器验收另行运行，要求已安装 Edge 和 Playwright：

```text
python prepare_browser_test.py
python test_release_e2e.py
```

prepare_browser_test.py 只下载公开前端脚本到系统临时目录。浏览器测试自动启动和停止两个隔离服务；不需要先启动正式服务，也不要把测试指向正式库。测试模块导入不会自行执行浏览器测试。

本地验证版本：Python 3.11；FastAPI 0.141.1、Uvicorn 0.52.1、Pydantic 2.13.4、MCP 1.29.0、HTTPX 0.28.1、Playwright 1.62.0。运行依赖见 requirements.txt；Playwright 仅用于验收。已有依赖类型/弃用警告不影响本次测试结果。

## 本地验收后部署顺序

1. 记录目标机器的 Python 版本、启动命令、服务管理方式、REST/MCP 端口、数据库绝对路径和当前代码版本。Selene 默认库为代码目录下 selene.db；确保 REST 与 MCP/网关引用同一份 Selene 代码及库。
2. 停止所有会写此库的旧进程（含 Memora 内嵌 Selene 网关）；保存完整旧代码和数据库备份，使用 SQLite backup API，检查 PRAGMA integrity_check=ok。保留该备份路径供回退使用。
3. 部署完整受版本控制的 Selene 代码，保留业务 selene.db、backups 和运行配置。尤其不能漏掉 period_actions.py、period_api.py、web_assets.py、log_migration.py、sync_storage.py 和 selene_browser.js。安装 requirements.txt。
4. 在目标运行环境执行 db.init_db() 和 db.migrate_cycle_config()，检查迁移备份、旧表保留条数及库完整性。任何异常先停止，不带错继续启动。
5. 运行 `python selene_rest.py 8010` 或现有部署入口，二者均提供首页和脚本；MCP 独立运行时用 `python selene_server.py 8003`。REST 只运行一个实例，避免多份后台定时任务。沿用现有服务管理方式。
6. 用目标访问地址检查首页、脚本和四个外部前端依赖能加载；检查 /get_config、/get_logs，MCP 调用 selene_status 与网页日期一致。手机刷新、开始/结束、撤销和历史入口按本工单再验收；写入演练先用目标机器的隔离库。
7. Memora 配套文件和安装说明见 integration/README.md。核对网关导入路径、8004 MCP 地址及两端版本。经用户验收后再进行真实推送和记忆写入验证。

当前尚未部署，因此目标服务器、真实手机网络、生产 Memora/推送链路仍待运行环境验收。

## 回退

停止全部写库进程；先另存升级后的完整数据库，保留新增业务数据。将升级前备份恢复到新文件并检查完整性，再配套切回旧代码与旧库后启动。不要在运行中覆盖 SQLite 文件。升级前备份不含升级后新增记录，不能直接丢弃升级后库。迁移恢复细节见 LOG_DATE_MIGRATION.md。
