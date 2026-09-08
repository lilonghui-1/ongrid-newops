"""SSH 远程执行工具 - 支持连接池、密钥/密码认证、超时控制、命令安全策略"""

import shlex
import socket
import threading
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import paramiko

from .base import BaseTool, ToolResult, ToolParameter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CommandPolicy - 只读命令安全沙箱（设计参考 ongrid cmdpolicy 概念，全新实现）
# ---------------------------------------------------------------------------

# 无条件拒绝的命令（denylist）
DENY_COMMANDS = {
    "rm", "dd", "mv", "chmod", "chown", "chgrp", "mkfs", "mkfs.ext4",
    "reboot", "shutdown", "halt", "poweroff", "init",
    "useradd", "userdel", "usermod", "passwd", "groupadd", "groupdel",
    "kill", "killall", "pkill", "nohup", "setsid",
    "sh", "bash", "zsh", "csh", "ksh", "dash", "tcsh", "fish",
    "sudo", "su", "vim", "vi", "nano", "ed", "sed", "awk", "perl", "python", "python3",
    "wget", "curl", "nc", "ncat", "telnet", "ftp", "scp", "rsync",
    "mount", "umount", "fdisk", "parted", "lvm", "pvcreate", "vgcreate", "lvcreate",
    "iptables", "ip6tables", "nft", "firewall-cmd", "ufw",
    "crontab", "at", "batch", "anacron", "systemctl"
}

# 明确允许的只读命令（read-only 白名单）
ALLOW_READONLY_COMMANDS = {
    "uptime", "uname", "date", "hostname", "who", "w", "last", "ps", "free",
    "df", "du", "ls", "stat", "cat", "head", "tail", "grep", "find", "lsof",
    "ss", "netstat", "route", "ip", "ping", "dig", "nslookup", "getent",
    "sysctl", "vmstat", "iostat", "sar", "mpstat", "pidstat", "dmesg",
    "journalctl", "crontab -l", "systemctl status", "systemctl list-units",
    "systemctl is-active", "systemctl is-enabled", "systemctl show", "service --status-all",
    "docker ps", "docker inspect", "kubectl get", "mysql", "psql", "redis-cli", "curl -I",
}

# 禁止出现在命令中的 shell 元字符（重定向/管道连接/子 shell）
DENY_SHELL_PATTERNS = [">", ">>", "<", "<<", ";", "&&", "||", "|", "$(", "`", "${"]


@dataclass
class PolicyDecision:
    """命令策略判定结果"""
    allowed: bool
    reason: str = ""


class CommandPolicy:
    """SSH 命令只读沙箱：denylist + 只读白名单 + 元字符拒绝 + 上限"""

    def __init__(self, deny: Optional[List[str]] = None,
                 stdout_cap: int = 64 * 1024,
                 timeout_default: int = 30):
        self._deny = set(deny or []) | DENY_COMMANDS
        self._stdout_cap = stdout_cap
        self._timeout_default = timeout_default

    def decide(self, command: str) -> PolicyDecision:
        """判断命令是否允许执行"""
        cmd = (command or "").strip()
        if not cmd:
            return PolicyDecision(False, "空命令")
        if len(cmd) > 8192:
            return PolicyDecision(False, "命令过长")

        # 1. shell 元字符拒绝（重定向/连接符/子 shell/反引号）
        #    注意：$、${ 检测仅针对命令文本，内部可信调用可 skip_policy 绕过
        for pattern in DENY_SHELL_PATTERNS:
            if pattern in cmd:
                return PolicyDecision(False, f"检测到禁止的 shell 元字符: {pattern!r}")

        # 2. 解析命令词（含管道拆段）
        try:
            segments = [shlex.split(seg.strip()) for seg in cmd.split("|")]
        except ValueError:
            return PolicyDecision(False, "命令解析失败（引号不闭合）")
        if not segments or not segments[0]:
            return PolicyDecision(False, "命令为空")

        # 3. 首命令 denylist
        first = segments[0][0]
        if first in self._deny:
            return PolicyDecision(False, f"命令被安全策略拒绝: {first}")

        # 4. 只读白名单：不在白名单的命令也拒绝（安全默认）
        #    支持多词条目前缀匹配（如 "systemctl list-units"、"docker ps"）
        if not self._match_whitelist(segments[0]):
            return PolicyDecision(False, f"命令不在只读白名单中: {' '.join(segments[0][:3])}")

        # 5. 管道后命令也需在只读白名单
        for seg in segments[1:]:
            if seg and not self._match_whitelist(seg):
                return PolicyDecision(False, f"管道后命令不在白名单: {' '.join(seg[:3])}")

        # 6. 白名单内命令的禁用参数（如 find -delete / -exec）
        first_args = segments[0][1:]
        if first in ("find",) and any(a in ("-delete", "-exec", "-execdir", "-ok") for a in first_args):
            return PolicyDecision(False, "find 写参数被拒绝（-delete/-exec 等）")

        return PolicyDecision(True, "只读命令，允许执行")

    @staticmethod
    def _match_whitelist(words: List[str]) -> bool:
        """白名单匹配：支持单词条目与多词前缀匹配"""
        for allowed in ALLOW_READONLY_COMMANDS:
            allowed_words = allowed.split()
            if words[:len(allowed_words)] == allowed_words:
                return True
        return False

    @staticmethod
    def is_readonly_command(command: str) -> bool:
        """判断命令是否只读（含多词条目的白名单匹配）"""
        try:
            segments = [shlex.split(seg.strip()) for seg in (command or "").split("|")]
        except ValueError:
            return False
        for seg in segments:
            if not seg:
                continue
            # 尝试多词匹配（如 "systemctl list-units"、"docker ps"）
            words = seg
            matched = False
            for allowed in ALLOW_READONLY_COMMANDS:
                allowed_words = allowed.split()
                if words[:len(allowed_words)] == allowed_words:
                    matched = True
                    break
            if not matched:
                return False
        return True

    def truncate_stdout(self, text: str) -> str:
        """截断 stdout 到上限"""
        if text and len(text) > self._stdout_cap:
            return text[: self._stdout_cap] + f"\n... (截断，共 {len(text)} 字符)"
        return text


class SSHConnectionPool:
    """SSH 连接池 - 按 host:port:username 缓存连接，线程安全"""

    _connections: dict = {}
    _lock = threading.Lock()

    @classmethod
    def get_connection(
        cls,
        host: str,
        port: int,
        username: str,
        password: str = None,
        private_key_path: str = None,
    ) -> paramiko.SSHClient:
        """获取或创建 SSH 连接（连接创建在锁外，锁内仅做缓存读写）"""
        key = f"{host}:{port}:{username}"

        if key in cls._connections:
            # 检查连接是否仍然活跃
            transport = cls._connections[key].get_transport()
            if transport and transport.is_active():
                return cls._connections[key]
            else:
                # 连接已断开，移除并重建
                try:
                    cls._connections[key].close()
                except Exception:
                    pass
                del cls._connections[key]

        # 锁外建立连接（慢操作，避免多线程串行等待）
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # 私钥路径前置校验：路径不存在时给出明确报错，避免误当成真实密钥
        # （常见配置错误：密码被填到 private_key_path / ${VAR} 未替换）
        if private_key_path:
            from pathlib import Path as _Path
            if not _Path(private_key_path).expanduser().is_file():
                raise FileNotFoundError(
                    f"SSH 私钥文件不存在: {private_key_path!r}（请检查 servers.yaml 的 "
                    f"private_key_path / 环境变量 SSH_PRIVATE_KEY_PATH；若使用密码登录，"
                    f"请改用 password 字段）"
                )

        connect_kwargs = {
            'hostname': host,
            'port': port,
            'username': username,
            'timeout': 5,
            'banner_timeout': 10,
            'auth_timeout': 10,
        }

        if private_key_path:
            try:
                pkey = paramiko.RSAKey.from_private_key_file(private_key_path)
                connect_kwargs['pkey'] = pkey
            except paramiko.ssh_exception.SSHException:
                # 尝试 Ed25519 密钥
                pkey = paramiko.Ed25519Key.from_private_key_file(private_key_path)
                connect_kwargs['pkey'] = pkey
        elif password:
            connect_kwargs['password'] = password

        client.connect(**connect_kwargs)

        # 锁内写入缓存（快操作）。若并发时已有他人建好，则复用并关闭本次新建
        with cls._lock:
            if key in cls._connections:
                try:
                    client.close()
                except Exception:
                    pass
                return cls._connections[key]
            cls._connections[key] = client
            logger.info(f"SSH connection established: {key}")
            return client

    @classmethod
    def close_all(cls):
        """关闭所有连接"""
        with cls._lock:
            for key, client in cls._connections.items():
                try:
                    client.close()
                    logger.info(f"SSH connection closed: {key}")
                except Exception:
                    pass
            cls._connections.clear()

    @classmethod
    def close(cls, host: str, port: int, username: str):
        """关闭指定连接"""
        key = f"{host}:{port}:{username}"
        with cls._lock:
            if key in cls._connections:
                try:
                    cls._connections[key].close()
                except Exception:
                    pass
                del cls._connections[key]


class SSHExecuteTool(BaseTool):
    """SSH 远程命令执行工具"""

    name = "ssh_execute"
    description = "在远程服务器上执行 Shell 命令并返回输出结果。支持 sudo 权限提升。"
    parameters = [
        ToolParameter(name="host", type="string", description="服务器地址"),
        ToolParameter(name="command", type="string", description="要执行的 Shell 命令"),
        ToolParameter(name="timeout", type="integer", description="超时时间(秒)", required=False, default=30),
        ToolParameter(name="username", type="string", description="SSH 用户名（可选，默认使用配置中的用户）", required=False),
        ToolParameter(name="use_sudo", type="boolean", description="是否使用 sudo 执行", required=False, default=False),
        ToolParameter(name="skip_policy", type="boolean", description="内部使用：跳过命令安全沙箱（仅限系统内部可信调用，如 Web 平台监控采集）", required=False, default=False),
    ]

    def __init__(self, config=None):
        self._config = config
        self._server_map = {}
        self._policy = CommandPolicy()
        if config and hasattr(config, 'servers'):
            for s in config.servers:
                self._server_map[s.host] = s

    def _find_server(self, host: str):
        """查找服务器配置"""
        return self._server_map.get(host)

    def execute(self, **kwargs) -> ToolResult:
        host = kwargs['host']
        command = kwargs['command']
        timeout = kwargs.get('timeout', 30)
        use_sudo = kwargs.get('use_sudo', False)

        # 命令安全策略：只读沙箱（sudo 命令直接拒绝，写操作拒绝）
        # skip_policy=True 仅供系统内部可信调用（Web 平台监控/服务管理），不受沙箱限制
        if not kwargs.get('skip_policy', False):
            if use_sudo:
                return ToolResult(success=False, error="安全策略拒绝: 禁止 sudo 执行", metadata={"host": host})
            decision = self._policy.decide(command)
            if not decision.allowed:
                return ToolResult(
                    success=False,
                    error=f"命令被安全策略拒绝: {decision.reason}",
                    metadata={"host": host, "command": command},
                )

        server = self._find_server(host)

        try:
            # 获取连接
            if server:
                conn = SSHConnectionPool.get_connection(
                    host=server.host,
                    port=server.port,
                    username=kwargs.get('username') or server.username,
                    password=server.password,
                    private_key_path=server.private_key_path,
                )
            else:
                # 没有配置时尝试使用默认参数
                conn = SSHConnectionPool.get_connection(
                    host=host,
                    port=22,
                    username=kwargs.get('username', 'root'),
                )

            # 执行命令
            stdin, stdout, stderr = conn.exec_command(command, timeout=timeout)

            # 并行读取 stdout 和 stderr 防止缓冲区阻塞
            out_lines = []
            err_lines = []

            def _read_stream(stream, lines):
                try:
                    for line in stream:
                        lines.append(line.rstrip('\n\r'))
                except Exception:
                    pass

            t_out = threading.Thread(target=_read_stream, args=(stdout, out_lines))
            t_err = threading.Thread(target=_read_stream, args=(stderr, err_lines))
            t_out.start()
            t_err.start()
            t_out.join(timeout=timeout + 5)
            t_err.join(timeout=timeout + 5)

            exit_code = stdout.channel.recv_exit_status()

            stdout_text = self._policy.truncate_stdout("\n".join(out_lines))
            return ToolResult(
                success=(exit_code == 0),
                data={
                    "stdout": stdout_text,
                    "stderr": "\n".join(err_lines)[:16 * 1024],
                    "exit_code": exit_code,
                },
                metadata={"host": host, "command": command, "policy": "readonly-sandbox"}
            )

        except paramiko.AuthenticationException as e:
            return ToolResult(success=False, error=f"SSH 认证失败: {e}", metadata={"host": host})
        except socket.gaierror:
            return ToolResult(
                success=False,
                error=f"无法解析主机名: {host}（请检查 servers.yaml 中的 host 配置或 DNS/hosts）",
                metadata={"host": host},
            )
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e), metadata={"host": host})
        except paramiko.SSHException as e:
            return ToolResult(success=False, error=f"SSH 连接错误: {e}", metadata={"host": host})
        except Exception as e:
            return ToolResult(success=False, error=f"命令执行失败: {type(e).__name__}: {e}", metadata={"host": host})


class BashExecuteTool(BaseTool):
    """本地 Bash 只读执行工具（subprocess，shell=False，受 CommandPolicy 约束）"""

    name = "bash_execute"
    description = "在 Agent 本地主机执行只读命令（受命令安全策略约束），返回输出"
    parameters = [
        ToolParameter(name="command", type="string", description="要执行的本地只读命令"),
        ToolParameter(name="timeout", type="integer", description="超时时间(秒)", required=False, default=30),
    ]

    def __init__(self, config=None):
        import subprocess as _sp
        self._sp = _sp
        self._policy = CommandPolicy()

    def execute(self, **kwargs) -> ToolResult:
        command = kwargs.get("command", "")
        timeout = float(kwargs.get("timeout", 30))
        decision = self._policy.decide(command)
        if not decision.allowed:
            return ToolResult(success=False, error=f"命令被安全策略拒绝: {decision.reason}")
        try:
            import subprocess
            import shlex

            argv = shlex.split(command)
            proc = subprocess.run(
                argv, shell=False, capture_output=True, text=True, timeout=timeout,
            )
            stdout = self._policy.truncate_stdout(proc.stdout)
            return ToolResult(
                success=proc.returncode == 0,
                data={
                    "stdout": stdout,
                    "stderr": proc.stderr[:16 * 1024],
                    "exit_code": proc.returncode,
                },
                metadata={"policy": "readonly-sandbox", "command": command},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error=f"命令超时（>{timeout}s）")
        except Exception as e:
            return ToolResult(success=False, error=f"本地命令执行失败: {type(e).__name__}: {e}")
