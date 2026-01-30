# Fitness Toolkit

个人运动数据同步工具，支持从高驰(COROS)同步运动记录到佳明(Garmin China)。

## 功能特性

- **账户管理**: 安全存储 COROS 和 Garmin 账户凭据（密码使用 Fernet 加密）
- **活动下载**: 从 COROS/Garmin 下载指定日期范围的运动数据（支持 TCX/GPX/FIT 格式）
- **跨平台同步**: 从 COROS 下载 FIT 文件并上传到 Garmin China
- **Web 界面**: 基于 Flask + Alpine.js 的浏览器操作界面
- **命令行工具**: 完整的 CLI 支持（Click）
- **操作历史**: 自动记录下载和同步历史
- **定时任务**: 支持配置定时同步任务（APScheduler）

## 安装

### 环境要求

- Python 3.10+
- SQLite3

### 安装步骤

```bash
# 克隆项目
git clone https://github.com/your-username/fitness_toolkit.git
cd fitness_toolkit

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或 .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 配置加密密钥

创建 `.env` 文件并设置加密密钥：

```bash
# 生成密钥
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 创建 .env 文件
echo "FITNESS_ENCRYPTION_KEY=你生成的密钥" > .env
```

## 使用方法

### 方式一：Web 界面（推荐）

```bash
python -m fitness_toolkit web
```

访问 http://localhost:5000 即可使用 Web 界面：

- **Accounts**: 配置 COROS 和 Garmin 账户
- **Download**: 从平台下载运动数据
- **Transfer**: 从 COROS 同步运动记录到 Garmin

### 方式二：命令行

#### 配置账户

```bash
# 配置 COROS 账户
python -m fitness_toolkit config configure coros --email your@email.com

# 配置 Garmin 账户
python -m fitness_toolkit config configure garmin --email your@email.com

# 查看已配置的账户
python -m fitness_toolkit config show

# 删除账户配置
python -m fitness_toolkit config remove coros
```

#### 下载活动数据

```bash
# 下载指定日期范围的活动
python -m fitness_toolkit download coros --start 2024-01-01 --end 2024-01-31

# 指定文件格式（tcx/gpx/fit）
python -m fitness_toolkit download garmin --start 2024-01-01 --end 2024-01-31 --format gpx

# 快速同步最近7天
python -m fitness_toolkit sync coros
```

#### 跨平台同步（COROS → Garmin）

```bash
# 同步指定日期范围的活动
python -m fitness_toolkit transfer --start 2024-01-01 --end 2024-01-31

# 按运动类型过滤
python -m fitness_toolkit transfer --start 2024-01-01 --end 2024-01-31 --sport-type running --sport-type cycling

# 指定 FIT 文件保存目录
python -m fitness_toolkit transfer --start 2024-01-01 --end 2024-01-31 --save-dir ./downloads
```

## 技术栈

- **Python 3.10+**
- **Web 框架**: Flask + Alpine.js + Tailwind CSS
- **CLI 框架**: Click
- **数据库**: SQLite (WAL 模式)
- **加密**: Fernet (cryptography)
- **定时任务**: APScheduler
- **Garmin API**: garth 库
- **COROS API**: 原生 HTTP (requests)

## 项目结构

```
fitness_toolkit/
├── __main__.py            # 包入口: python -m fitness_toolkit
├── cli.py                 # Click CLI 命令
├── config.py              # 配置管理 (.env 支持)
├── crypto.py              # Fernet 密码加密
├── database.py            # SQLite 操作 (账户/历史/任务)
├── logger.py              # 日志配置
├── clients/               # 平台 API 客户端
│   ├── base.py            # BaseClient ABC
│   ├── garmin.py          # Garmin China (garth)
│   └── coros.py           # COROS Training Hub
├── services/              # 业务逻辑
│   ├── account.py         # 账户管理
│   ├── download.py        # 活动下载
│   ├── transfer.py        # COROS→Garmin 同步
│   └── scheduler.py       # 定时任务
└── web/                   # Web 应用
    ├── app.py             # Flask API 路由
    └── templates/         # Jinja2 模板 (index.html)
```

## 开发

```bash
# 运行测试
pytest

# 代码检查
ruff check .

# 代码格式化
black .
```

## 测试

项目包含完整的测试套件：

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_web_transfer.py

# 带覆盖率报告
pytest --cov=fitness_toolkit --cov-report=html
```

测试覆盖：
- 加密/解密模块 (`test_crypto.py`)
- 数据库操作 (`test_database.py`)
- Web API 端点 (`test_web_*.py`)
- 账户管理、下载、同步、定时任务

## 注意事项

- **单账户设计**: 每个平台仅支持一个账户（platform 作为主键）
- **密码加密**: 使用 Fernet 加密存储，请妥善保管 `.env` 文件中的 `FITNESS_ENCRYPTION_KEY`
- **本地服务**: Web 服务默认只绑定到 `127.0.0.1:5000`，请勿暴露到公网
- **重复检测**: 同步时自动跳过 Garmin 中已存在的活动（通过 HTTP 409 或 code 202 判断）
- **文件格式**: 同步使用 FIT 格式（TCX 有扩展名兼容性问题）
- **Garmin 中国**: 专为中国区 Garmin Connect 优化（`garmin.cn` 域名）

## 许可证

Apache License 2.0
