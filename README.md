# Fitness Toolkit

本地化的运动数据同步工具，支持从高驰(COROS)同步运动记录到佳明(Garmin)。

## 功能特性

- **账户管理**: 安全存储 COROS 和 Garmin 账户凭据（密码加密存储）
- **活动下载**: 从 COROS/Garmin 下载指定日期范围的运动数据
- **跨平台同步**: 从 COROS 下载 TCX 文件并上传到 Garmin
- **Web 界面**: 提供友好的浏览器操作界面
- **命令行工具**: 支持 CLI 命令行操作

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

# 指定 TCX 文件保存目录
python -m fitness_toolkit transfer --start 2024-01-01 --end 2024-01-31 --save-dir ./downloads
```

## 项目结构

```
fitness_toolkit/
├── __init__.py            # 包初始化
├── __main__.py            # 入口点
├── cli.py                 # CLI 命令实现
├── config.py              # 配置管理
├── crypto.py              # 密码加密
├── database.py            # SQLite 数据库操作
├── logger.py              # 日志配置
├── clients/               # 平台 API 客户端
│   ├── base.py            # 基类
│   ├── garmin.py          # Garmin 客户端（使用 garth 库）
│   └── coros.py           # COROS 客户端
├── services/              # 业务逻辑层
│   ├── account.py         # 账户管理服务
│   ├── download.py        # 下载服务
│   ├── transfer.py        # 同步服务
│   └── scheduler.py       # 调度服务
└── web/                   # Web 应用
    ├── app.py             # Flask 应用
    └── templates/         # 页面模板
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

## 注意事项

- 密码使用 Fernet 加密存储，请妥善保管 `.env` 文件中的密钥
- Web 服务默认只绑定到 localhost，不要暴露到公网
- 同步时会自动跳过 Garmin 中已存在的活动（通过活动名称判断）

## 许可证

Apache License 2.0
