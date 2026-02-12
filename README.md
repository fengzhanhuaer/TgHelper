# TgHelper

TgHelper 是一个基于 Flask + SQLite + Telethon 的 Telegram 管理工具，支持：

- 首次注册/登录
- 多 TG 账号管理
- 自动发送任务（每日时间 + 随机延时）
- 本地数据库与 Cloudflare D1 备份/拉取

默认访问地址：

- http://127.0.0.1:15018

---

## 1. 从 GitHub 拉取代码

### 首次克隆

```bash
git clone https://github.com/fengzhanhuaer/TgHelper.git
cd TgHelper
```

### 已有项目更新

```bash
git pull
```

---

## 2. 安装

## Linux（一键安装 + 注册后台服务）

项目内置安装脚本 [install](install)。

```bash
cd TgHelper
chmod +x install
./install
```

脚本会自动完成：

- 安装 Python（缺失时）
- 创建 `.venv`
- 安装依赖
- 注册并启动 `tghelper.service`

常用命令：

```bash
systemctl status tghelper.service
journalctl -u tghelper.service -f
```

## Linux（从 GitHub 一键拉取 + 安装 + 注册服务）

仓库内提供了引导脚本 [install_from_github.sh](install_from_github.sh)，可自动完成：

- 从 GitHub 拉取/更新仓库
- 执行项目安装脚本
- 注册并启动 `tghelper.service`

用法：

```bash
bash install_from_github.sh <repo_url> [branch] [target_dir]
```

示例：

```bash
bash install_from_github.sh https://github.com/fengzhanhuaer/TgHelper.git main /opt/TgHelper
```

如果你希望“只用一条命令”安装，建议先下载到本地再执行本地脚本：

```bash
curl -fsSL -o install_from_github.sh https://raw.githubusercontent.com/fengzhanhuaer/TgHelper/main/install_from_github.sh && chmod +x install_from_github.sh && ./install_from_github.sh https://github.com/fengzhanhuaer/TgHelper.git main /opt/TgHelper
```

## Windows（本地运行）

### 方法 A：直接启动

双击 [TgHelper.bat](TgHelper.bat)

### 方法 B：命令行启动

```powershell
cd D:\100.Working\GithubWork\TgHelper
.\TgHelper.bat
```

---

## 3. 手动安装依赖（可选）

如果你不使用 Linux 一键脚本，也可以手动安装：

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

---

## 4. 使用方法

1. 启动服务后，打开 http://127.0.0.1:15018
2. 首次进入先注册本地管理员账号
3. 登录后进入首页：
   - 管理账号：添加 TG 账号并刷新会话
   - 自动发送：新建任务、管理任务、手动触发
   - 数据库管理：配置 Cloudflare Token，执行备份/拉取
4. 在“管理任务”页面可直接编辑：
   - 发送内容
   - 每天发送时间
   - 随机延时

---

## 5. 目录说明

- [TgHelper.py](TgHelper.py)：主程序入口与全部后端逻辑
- [templates](templates)：前端模板
- [requirements.txt](requirements.txt)：Python 依赖
- [install](install)：Linux 一键安装与后台服务注册脚本
- [install_from_github.sh](install_from_github.sh)：Linux 一键拉取仓库并自动安装脚本
- [TgHelper.bat](TgHelper.bat)：Windows 启动脚本

---

## 6. 备注

- 本地数据库文件名为 `TgHelper.db`
- 端口默认 15018
- 自动任务时间展示为 UTC+8
