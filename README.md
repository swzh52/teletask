# 🤖 Teletask — Telegram Bot 自动化管理系统

一个基于 Python 的 Telegram 机器人管理平台，支持关键词自动回复、定时消息推送，配备 Web 管理后台，无需修改代码即可完成所有配置。

---

## ✨ 功能特性

### 🔑 关键词自动回复
- 支持**包含 / 精确 / 正则**三种匹配方式
- 一个关键词可绑定**多条不同类型的回复**
- 触发模式：**随机一条** 或 **全部发送**
- 支持回复类型：文本、图片、视频、音频、文件、动图、语音、贴纸、**相册（最多9个文件）**
- 监听范围：私聊、群组、频道

### ⏰ 定时推送任务
- 支持 **Cron 表达式**（周期执行）
- 支持**一次性定时任务**（指定具体时间，执行后自动停用）
- 推送内容支持所有媒体类型，包括相册模式
- 任务执行日志记录（完成 / 执行中 / 失败）

### 🖥 Web 管理后台
- 浏览器操作，无需改代码
- 关键词和定时任务均支持**增删改查**
- 弹窗式编辑，操作流畅
- 实时显示当前时间，内置 Cron 表达式快填示例
- 概览统计卡片（触发次数、任务完成数等）

### 📁 文件库
- 管理员向 Bot 发送媒体文件，自动记录 file_id 及文件信息
- 记录上传者姓名、用户名、ID
- 支持关键词搜索，点击 file_id 一键复制
- 独立密码验证访问

### 📊 统计信息
- 关键词触发记录：用户、群组、触发时间、关键词
- 定时任务执行情况：完成 / 执行中 / 失败状态
- 封禁用户管理：一键 Ban / Unban
- 数据概览卡片

### 🔐 权限管理
- `.env` 配置多个管理员账号（Telegram user_id）
- 仅管理员可向 Bot 上传文件获取 file_id
- 普通用户触发关键词无需权限，可被 Ban 屏蔽

### 🤖 Bot 命令（管理员专属）
| 命令 | 说明 |
|------|------|
| `/start` | 查看 Bot 状态和管理员信息 |
| `/keywords` | 查看所有关键词规则列表 |
| `/task_status` | 查看定时任务状态和最近执行记录 |
| 直接发送媒体文件 | 获取 file_id 并入库 |

---

## 🗂 项目结构

```
teletask/
├── main.py          # 启动入口，同时运行 Bot 和 Web 后台
├── bot.py           # Bot 核心逻辑（消息处理、定时任务）
├── app.py           # Flask Web 管理后台
├── database.py      # SQLite 数据库操作
├── requirements.txt # Python 依赖
├── .env             # 环境变量配置（不上传 Git）
├── tgbot.db         # SQLite 数据库文件（自动生成）
└── templates/
    ├── index.html        # 主管理后台
    ├── login.html        # 登录页
    ├── files.html        # 文件库
    ├── files_login.html  # 文件库登录页
    ├── stats.html        # 统计信息
    └── stats_login.html  # 统计登录页
```

---

## 🚀 快速部署

### 环境要求
- Python 3.10+
- Ubuntu 20.04 / 22.04 / 24.04

### 第一步：克隆项目

```bash
cd /opt
git clone https://github.com/你的用户名/teletask.git
cd teletask
```

### 第二步：安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 第三步：配置环境变量

```bash
nano .env
```

```env
# Telegram Bot Token（从 @BotFather 获取）
BOT_TOKEN=123456789:ABCdefGHI...

# Web 管理后台密码
ADMIN_PASSWORD=your_password

# 代理（国内服务器需要，海外服务器留空）
PROXY=socks5://127.0.0.1:7890

# Web 后台端口
WEB_PORT=5000

# 管理员 Telegram user_id（多个用逗号分隔）
ADMIN_IDS=123456789,987654321
```

### 第四步：测试运行

```bash
python main.py
```

看到以下输出说明成功：
```
Web 管理后台启动 → http://0.0.0.0:5000
Bot 启动完成
```

### 第五步：配置后台服务

```bash
sudo nano /etc/systemd/system/teletask.service
```

```ini
[Unit]
Description=Teletask Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/teletask
ExecStart=/opt/teletask/.venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable teletask
sudo systemctl start teletask
```

### 第六步：开放端口

```bash
sudo ufw allow 22
sudo ufw allow 5000
sudo ufw enable
```

### 访问管理后台

```
http://你的服务器IP:5000
```

---

## 📖 使用指南

### 添加关键词回复

1. 登录管理后台
2. 在「关键词自动回复」区域填写关键词和匹配方式
3. 选择触发模式（随机一条 / 全部发送）
4. 添加一条或多条回复内容
5. 点击「添加关键词」

### 添加媒体类型回复

1. 在 Telegram 中私聊你的 Bot，发送图片/视频/文件
2. Bot 自动回复该文件的 `file_id`
3. 在管理后台选择对应媒体类型，粘贴 `file_id`

### 添加定时任务

1. 填写任务名称和目标 Chat ID
2. 选择「周期执行」填写 Cron 表达式，或选择「一次性」选择具体时间
3. 选择消息类型，填写内容
4. 点击「添加定时任务」

**Cron 表达式速查：**

| 表达式 | 含义 |
|--------|------|
| `0 9 * * *` | 每天早上 9 点 |
| `0 9 * * 1-5` | 工作日早上 9 点 |
| `*/30 * * * *` | 每 30 分钟 |
| `0 8,12,20 * * *` | 每天 8点、12点、20点 |
| `0 0 * * 1` | 每周一 0 点 |
| `0 10 1 * *` | 每月 1 日 10 点 |

### 获取 Chat ID

向 Telegram 的 [@get_id_bot](https://t.me/get_id_bot) 发消息，或将其拉入群组发送 `/id` 获取。

---

## 🔧 运维命令

```bash
# 查看运行状态
systemctl status teletask

# 重启服务
systemctl restart teletask

# 查看实时日志
journalctl -u teletask -f

# 查看最近 100 行日志
journalctl -u teletask -n 100

# 停止服务
systemctl stop teletask
```

### 更新代码

```bash
cd /opt/teletask
git pull
systemctl restart teletask
```

---

## 🛠 技术栈

| 组件 | 技术 |
|------|------|
| Bot 框架 | [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v21+ |
| Web 后台 | [Flask](https://flask.palletsprojects.com/) |
| 定时任务 | [APScheduler](https://apscheduler.readthedocs.io/) |
| 数据库 | SQLite（内置，无需安装） |
| 环境配置 | python-dotenv |

---

## ⚠️ 注意事项

- `.env` 文件包含 Bot Token 等敏感信息，**不要上传到 Git 仓库**
- `tgbot.db` 是数据库文件，建议定期备份
- 国内服务器需配置代理才能访问 Telegram API
- 管理后台默认监听所有 IP，建议配置防火墙或 Nginx 反代 + HTTPS

---

## 📄 License

MIT License
