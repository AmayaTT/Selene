# Selene 🌙

温柔、懂生理周期的经期伴侣应用。Selene 会记录你的经期，根据周期阶段给你发恰到好处的提醒与科普——不是冷冰冰的健康告警，是有人惦记着你的那种温柔。

- 数据 100% 自己掌控（默认本地 SQLite，也可接你自己的 MySQL / PostgreSQL）
- 提醒可选（默认不推，配好才推），隐私第一

---

## ✨ 功能特性

- **经期记录**：记录开始日期、流量、疼痛、情绪、身体症状
- **周期预测**：根据历史数据预测下次经期与排卵窗口
- **阶段感知**：自动识别经期/卵泡期/排卵期/黄体期，给对应阶段的提醒与科普
- **多维日志**：情绪、症状、身体状态独立记录，支持按日回溯
- **Web 界面**：响应式前端，日历、趋势、科普一目了然
- **提醒推送**：经期临近 / 到了 / 阶段切换时推送温柔提醒（可配置）
- **隐私优先**：数据全存本地，推送只发出文案，不上传敏感原始数据
- **可插拔存储**：默认 SQLite 零依赖，可切换 MySQL / PostgreSQL 等（见下文）

## 🧰 技术栈

- **后端**：Python + FastAPI + Uvicorn（标准库为主，结构清晰）
- **前端**：原生 HTML / JS（单页应用，无构建依赖也能跑）
- **存储**：默认 SQLite（本地单文件），预留万能接口可换数据库
- **提醒**：内置调度器，可选接入 ServerChan（微信推送）

---

## 🚀 快速开始

### 环境要求

- Python 3.9+
- 无需 Node（前端是原生 JS，构建脚本可选）

### 安装与运行

```bash
# 1. 克隆仓库
git clone https://github.com/AmayaTT/Selene.git
cd Selene

# 2. （可选）建虚拟环境
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动服务
python selene_rest.py

# 5. 浏览器打开
# http://localhost:8010
```

> 依赖里只有 FastAPI / Uvicorn / Pydantic。前端是原生 JS，不需要 Node。

---

## 🔔 微信推送设置教程（ServerChan）

Selene 的主动提醒通过 **Server酱（ServerChan）** 推送到你的微信。需要**你自己注册、拿你自己的 SendKey**，然后把 Key 填给 Selene。全程如下：

### 第 1 步：注册并绑定微信

1. 浏览器打开 **https://sct.ftqq.com**（Server酱官网）
2. 用 GitHub 登录（注册即登录）
3. 用微信**扫码**，关注公众号 **「Server酱」**——推送就是发到这个公众号
4. 登录后进入控制台，找到你的 **SendKey**，形如：`SCT123456AbCdEfGhIjKlMnOpQr`

> ⚠️ SendKey 是你的私密凭据，**不要**提交进代码或仓库，也不要发给别人。填进 Selene 后会存本地数据库。

### 第 2 步：把 SendKey 填给 Selene

服务**运行中**的话，用一条命令写入（端口默认 8010）：

```bash
curl -X POST http://localhost:8010/reminder_config \
  -H "Content-Type: application/json" \
  -d '{"serverchan_key":"SCT123456AbCdEfGhIjKlMnOpQr","enabled":true,"times":"08:30,21:00"}'
```

如果没装 curl（Windows），也可以直接改本地数据库：

```bash
python -c "import db; db.set_config('serverchan_key','SCT123456AbCdEfGhIjKlMnOpQr'); db.set_config('remind_enabled','1'); db.set_config('remind_times','08:30,21:00')"
```

### 第 3 步：测试推送通道

```bash
curl -X POST http://localhost:8010/reminder_test
```

成功的话，你的微信会收到一条 Selene 的测试关怀。收不到就检查第 1 步的公众号是否关注成功。

### 配置项一览

| 配置 key | 含义 | 示例 |
|---|---|---|
| `serverchan_key` | 你的 Server酱 SendKey | `SCT...` |
| `remind_enabled` | 总开关 | `1` 开 / `0` 关 |
| `remind_times` | 每天推送的时间点（逗号分隔） | `08:30,21:00` |

> 提醒**默认关闭**，只有填了 Key 才会推。不填 Key 完全不影响 Selene 的记录功能——这是"能选"的哲学。

---

## 🗄️ 接入其他数据库（万能接口示例）

Selene 默认用本地 SQLite（单文件 `selene.db`，零依赖）。但如果你想接入 **MySQL / PostgreSQL**（比如多端共享、上云、或已有数据库），项目里已经预留了**万能存储接口**——不需要改业务逻辑，只换存储实现。

### 接口在哪

看 **`storage.py`**，它定义了 `StorageInterface`（抽象契约，列出全部存储方法），并提供三个实现：

| 实现 | 说明 |
|---|---|
| `SQLiteStorage` | 默认，直接复用 `db.py`，行为不变 |
| `MySQLStorage` | 示例，用 `pymysql` |
| `PostgresStorage` | 示例，用 `psycopg2` |

### 三步切换成 MySQL

**① 装驱动**

```bash
pip install pymysql
```

**② 建表**（在 MySQL 里执行附录一的 SQL）

**③ 切换**

在 `selene_rest.py` 的启动处（`if __name__ == "__main__":` 之前）加两行：

```python
import storage
storage.use_mysql(host="127.0.0.1", user="root", password="你的密码", database="selene")
```

> 启动后业务代码通过 `storage.STORE` 读写，自动走 MySQL。

### 切 PostgreSQL

```bash
pip install psycopg2-binary
```

建表用附录二，切换用：

```python
import storage
storage.use_postgres(host="127.0.0.1", user="postgres", password="你的密码", database="selene")
```

### 接入你自己的任意数据库

只要实现 `StorageInterface` 的抽象方法（抄 `MySQLStorage` 的骨架，把 SQL 换成目标数据库的语法），再写一个 `use_xxx()` 函数把 `storage.STORE` 换成你的实例即可。业务层完全不用动。

---

## 附录一：MySQL 建表 SQL

```sql
CREATE TABLE periods (
  id INT AUTO_INCREMENT PRIMARY KEY,
  start_date VARCHAR(10) NOT NULL,
  end_date VARCHAR(10),
  flow INT DEFAULT 2,
  pain INT DEFAULT 0,
  mood VARCHAR(255) DEFAULT '',
  body_note TEXT,
  note TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE config (
  k VARCHAR(64) PRIMARY KEY,
  value TEXT
);

CREATE TABLE mood_log (
  day INT PRIMARY KEY,
  score INT,
  date VARCHAR(10) DEFAULT ''
);

CREATE TABLE symptom_log (
  day INT PRIMARY KEY,
  symptoms TEXT,
  date VARCHAR(10) DEFAULT ''
);

CREATE TABLE care_log (
  id INT AUTO_INCREMENT PRIMARY KEY,
  day INT,
  date VARCHAR(10),
  score INT,
  memory_id INT,
  related_count INT DEFAULT 0,
  memora_ok INT DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE feed_log (
  id INT AUTO_INCREMENT PRIMARY KEY,
  date VARCHAR(10),
  kind VARCHAR(10),
  memory_id INT,
  ok INT DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 附录二：PostgreSQL 建表 SQL

```sql
CREATE TABLE periods (
  id SERIAL PRIMARY KEY,
  start_date VARCHAR(10) NOT NULL,
  end_date VARCHAR(10),
  flow INT DEFAULT 2,
  pain INT DEFAULT 0,
  mood VARCHAR(255) DEFAULT '',
  body_note TEXT,
  note TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE config (
  k VARCHAR(64) PRIMARY KEY,
  value TEXT
);

CREATE TABLE mood_log (
  day INT PRIMARY KEY,
  score INT,
  date VARCHAR(10) DEFAULT ''
);

CREATE TABLE symptom_log (
  day INT PRIMARY KEY,
  symptoms TEXT,
  date VARCHAR(10) DEFAULT ''
);

CREATE TABLE care_log (
  id SERIAL PRIMARY KEY,
  day INT,
  date VARCHAR(10),
  score INT,
  memory_id INT,
  related_count INT DEFAULT 0,
  memora_ok INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE feed_log (
  id SERIAL PRIMARY KEY,
  date VARCHAR(10),
  kind VARCHAR(10),
  memory_id INT,
  ok INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🗂️ 数据存储（默认 SQLite）

- 所有数据存在本地 `selene.db`（SQLite 单文件），不会上传。
- 备份：直接复制 `selene.db` 文件即可。
- 删除即清空，建议定期备份。

## 🤝 开源说明

本项目以 **MIT** 协议开源。欢迎 fork / PR / issue。

> 作者维护一个「伴侣定制版」，包含面向特定关系的私密表达；开源分支统一使用中性版文案，保护使用者的隐私边界。

## 📄 License

[MIT](LICENSE)

---

Selene，写给每一个值得被认真对待的女性。🌙
