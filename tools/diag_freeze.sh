#!/usr/bin/env bash
# 界面"卡住"时的一条命令现场采集：进程还在不在 / 卡在什么系统调用 / 走的是
# Wayland 还是 XWayland / 有没有抓到 Python 栈。
#
# 用法（界面卡住时，在**另一个**终端里跑）：
#     bash tools/diag_freeze.sh
#     bash tools/diag_freeze.sh <pid>          # 已知 pid 时
#
# 为什么需要它（2026-11-28）：用户报"点一下就卡死"，而实测进程活着、单实例
# 通道 10ms 内应答——说明**主线程并不忙**，看门狗一条 [stall] 都不打。这种
# "界面死、进程活"只能当场看现场：是坐在 epoll 上空转（输入根本没到）、还是
# 卡在 futex（有锁），以及窗口到底挂在哪个平台插件上。
set -u

find_pid() {
    local p
    for p in $(pgrep -u "$(id -u)" -f "desktop" 2>/dev/null); do
        local cmd
        cmd=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null) || continue
        case "$cmd" in
            *python*" -m desktop"*) echo "$p"; return 0 ;;
        esac
    done
    return 1
}

PID=${1:-}
if [ -z "$PID" ]; then
    PID=$(find_pid) || {
        echo "没找到在跑的桌面进程（pgrep 未命中 'python -m desktop'）。"
        echo "试试：ps -eo pid,args | grep -i desktop"
        exit 1
    }
fi

echo "=== pid $PID ============================================"
tr '\0' ' ' < "/proc/$PID/cmdline"; echo
echo "启动至今：$(ps -o etime= -p "$PID" 2>/dev/null | tr -d ' ')"
echo

echo "--- 线程状态（R=跑 S=睡 D=不可中断 Z=僵尸）与等待点 ---"
for t in /proc/"$PID"/task/*; do
    tid=$(basename "$t")
    st=$(awk '{print $3}' "$t/stat" 2>/dev/null)
    wc=$(cat "$t/wchan" 2>/dev/null)
    nm=$(cat "$t/comm" 2>/dev/null)
    printf "  %-7s %-2s %-24s %s\n" "$tid" "$st" "$wc" "$nm"
done | sort -k2 | uniq -c | sort -rn | head -20
echo
echo "（主线程 tid == pid：上面若它停在 epoll_wait，说明事件循环在空转、"
echo "  没人给它送输入 → 问题在窗口/合成器层；停在 futex 则是有锁没放。）"
echo

echo "--- 图形后端（决定窗口归谁管）---"
ls -l /proc/"$PID"/fd 2>/dev/null \
    | grep -oE "(wayland-[0-9]+|X11-unix/X[0-9]+|/dev/dri/[a-z0-9]+)" \
    | sort -u | sed 's/^/  /' || echo "  （读不到 fd 表）"
echo

echo "--- 窗口与焦点（看不见的模态/丢焦点都会让"点哪儿都没反应"）---"
timeout 5 xprop -root _NET_ACTIVE_WINDOW 2>/dev/null | sed 's/^/  /'
timeout 5 xwininfo -root -tree 2>/dev/null \
    | grep -iE "古籍|python|dialog|QDialog" | head -8 | sed 's/^/  /'
echo
echo "（若这里没有任何本程序窗口，说明它不在 X 上——那 xcb/xwayland 的检查都无效。）"
echo

echo "--- X 侧到底收不收得到鼠标事件（3 秒，**请在这 3 秒里点一下那个没反应的按钮**）---"
if command -v xinput > /dev/null 2>&1; then
    EVENTS=$(timeout 3 xinput test-xi2 --root 2>/dev/null | grep -cE "ButtonPress|Motion")
    if [ "${EVENTS:-0}" -gt 0 ]; then
        echo "  收到 $EVENTS 条指针事件 → **X 侧正常**：事件进得来，问题在应用内"
        echo "  （那就是模态/弹层把输入吃了 —— 看 logs/crash.log 里的 [input] 行）"
    else
        echo "  3 秒内一条指针事件都没有 → 输入根本没到 X"
        echo "  （可能：窗口不在 X 上 / 另一个客户端拿着 XGrabPointer / 合成器层问题）"
    fi
else
    echo "  没装 xinput，跳过（sudo apt install xinput）"
fi
echo

echo "--- Python 栈 ---"
SPY=$(command -v py-spy || echo "$HOME/miniconda3/envs/py310/bin/py-spy")
if [ -x "$SPY" ]; then
    "$SPY" dump --pid "$PID" --nonblocking 2>&1 | head -80
else
    echo "  未安装 py-spy。装一次就好："
    echo "    ~/miniconda3/envs/py310/bin/pip install py-spy"
    echo "  然后重跑本脚本（必要时前面加 sudo：Ubuntu 的 ptrace_scope=1"
    echo "  只允许追踪自己的子进程）。"
    echo
    echo "  另一个零依赖的办法（要重启一次程序才生效）："
    echo "    kill -USR1 $PID     # 已注册，所有线程栈会写进"
    echo "    ~/Documents/guji/logs/crash.log"
fi
