#!/bin/zsh
# 每天生成小红书发布包。由 launchd 调用，也可手动执行。
export PATH="/usr/bin:/bin:/usr/sbin:/sbin"
. "$HOME/.config/daily-radar/env"
cd "$HOME/Desktop/daily-radar" || exit 1
mkdir -p 发布包
/usr/bin/python3 -m radar --publish-only >> 发布包/run.log 2>&1
