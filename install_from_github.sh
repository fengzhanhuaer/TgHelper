#!/usr/bin/env bash
set -euo pipefail

# 用法:
#   bash install_from_github.sh <repo_url> [branch] [target_dir]
# 示例:
#   bash install_from_github.sh https://github.com/your-org/TgHelper.git main /opt/TgHelper

REPO_URL="${1:-}"
BRANCH="${2:-main}"
TARGET_DIR="${3:-/opt/TgHelper}"

if [[ -z "$REPO_URL" ]]; then
  echo "[ERROR] 缺少仓库地址。"
  echo "[USAGE] bash install_from_github.sh <repo_url> [branch] [target_dir]"
  exit 1
fi

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "[ERROR] 该脚本仅支持 Linux。"
  exit 1
fi

SUDO=""
if [[ "${EUID}" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    echo "[ERROR] 需要 root 权限或 sudo。"
    exit 1
  fi
fi

install_tool_if_missing() {
  local tool_name="$1"
  local apt_pkg="$2"
  local dnf_pkg="$3"
  local yum_pkg="$4"
  local pacman_pkg="$5"

  if command -v "$tool_name" >/dev/null 2>&1; then
    return 0
  fi

  echo "[INFO] 未检测到 $tool_name，尝试自动安装..."
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update
    $SUDO apt-get install -y "$apt_pkg"
  elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y "$dnf_pkg"
  elif command -v yum >/dev/null 2>&1; then
    $SUDO yum install -y "$yum_pkg"
  elif command -v pacman >/dev/null 2>&1; then
    $SUDO pacman -Sy --noconfirm "$pacman_pkg"
  else
    echo "[ERROR] 无法识别包管理器，请手动安装 $tool_name。"
    exit 1
  fi
}

install_tool_if_missing git git git git git
install_tool_if_missing bash bash bash bash bash

if [[ -d "$TARGET_DIR/.git" ]]; then
  echo "[INFO] 检测到已存在仓库，执行更新: $TARGET_DIR"
  $SUDO git -C "$TARGET_DIR" fetch --all --prune
  $SUDO git -C "$TARGET_DIR" checkout "$BRANCH"
  $SUDO git -C "$TARGET_DIR" pull --ff-only origin "$BRANCH"
else
  echo "[INFO] 克隆仓库到: $TARGET_DIR"
  $SUDO mkdir -p "$(dirname "$TARGET_DIR")"
  $SUDO git clone -b "$BRANCH" "$REPO_URL" "$TARGET_DIR"
fi

if [[ ! -f "$TARGET_DIR/install" ]]; then
  echo "[ERROR] 仓库中缺少安装脚本: $TARGET_DIR/install"
  exit 1
fi

echo "[INFO] 执行项目安装脚本..."
$SUDO chmod +x "$TARGET_DIR/install"
$SUDO bash "$TARGET_DIR/install"

echo "[OK] 完成。服务状态："
$SUDO systemctl status tghelper.service --no-pager -l || true
