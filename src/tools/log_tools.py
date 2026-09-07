"""日志收集与分析工具 - 支持远程日志获取、日志平台API查询、错误模式识别、异常检测

支持两种日志获取方式：
1. SSH 文件读取：直接读取服务器上的日志文件（Linux/Windows）
2. 日志平台 API：通过 ELK/Loki/Fluentd 等日志平台接口查询日志
"""

import re
import json
import logging
from collections import Counter
from typing import List, Optional
from datetime import datetime, timedelta

from .base import BaseTool, ToolResult, ToolParameter

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

logger = logging.getLogger(__name__)


class LogFetchTool(BaseTool):
    """远程日志获取工具 - 通过 SSH 获取服务器上的日志文件"""

    name = "log_fetch"
    description = "获取远程服务器上的日志文件内容，支持 tail/head/grep 模式。自动适配 Linux/Windows 命令。"
    parameters = [
        ToolParameter(name="host", type="string", description="服务器地址"),
        ToolParameter(name="file_path", type="string", description="日志文件路径（Linux: /var/log/syslog, Windows: C:\\Logs\\app.log）"),
        ToolParameter(name="mode", type="string", description="读取模式: tail(末尾), head(开头), grep(搜索)", required=False, default="tail"),
        ToolParameter(name="lines", type="integer", description="读取行数", required=False, default=200),
        ToolParameter(name="pattern", type="string", description="grep 搜索模式（正则表达式）", required=False),
        ToolParameter(name="since", type="string", description="起始时间过滤（如 '1 hour ago', '2024-01-01'）", required=False),
        ToolParameter(name="os_type", type="string", description="操作系统类型: linux(默认), windows", required=False, default=None),
    ]

    def __init__(self, ssh_tool=None, config=None):
        self._ssh_tool = ssh_tool
        self._config = config
        self._server_map = {}
        if config and hasattr(config, 'servers'):
            for s in config.servers:
                self._server_map[s.host] = s

    def _set_ssh_tool(self, ssh_tool):
        """延迟设置 SSH 工具（避免循环依赖）"""
        self._ssh_tool = ssh_tool

    def _get_os_type(self, host: str, os_type: str = None) -> str:
        """获取服务器操作系统类型"""
        if os_type and os_type.lower() in ('linux', 'windows'):
            return os_type.lower()
        server = self._server_map.get(host)
        if server and hasattr(server, 'os_type'):
            return server.os_type.lower()
        return 'linux'

    def execute(self, **kwargs) -> ToolResult:
        if not self._ssh_tool:
            return ToolResult(success=False, error="SSH 工具未初始化")

        host = kwargs['host']
        file_path = kwargs['file_path']
        mode = kwargs.get('mode', 'tail')
        lines = kwargs.get('lines', 200)
        pattern = kwargs.get('pattern')
        since = kwargs.get('since')
        os_type = self._get_os_type(host, kwargs.get('os_type'))

        # 1. 检查文件是否存在和大小
        if os_type == 'windows':
            check_cmd = f'powershell -Command "(Get-Item \'{file_path}\' -ErrorAction SilentlyContinue) | Select-Object Length"'
        else:
            check_cmd = f"stat -c '%s' {file_path} 2>/dev/null && wc -l < {file_path}"

        check_result = self._ssh_tool.execute(host=host, command=check_cmd, timeout=10, skip_policy=True)
        if not check_result.success:
            return ToolResult(success=False, error=f"无法访问日志文件: {file_path}")

        # 2. 构建读取命令（适配 Linux/Windows）
        if os_type == 'windows':
            if mode == 'head':
                cmd = f'powershell -Command "Get-Content \'{file_path}\' -Head {lines}"'
            elif mode == 'grep' and pattern:
                safe_pattern = pattern.replace("'", "''")
                cmd = f'powershell -Command "Select-String -Path \'{file_path}\' -Pattern \'{safe_pattern}\' | Select-Object -Last {lines}"'
            else:
                cmd = f'powershell -Command "Get-Content \'{file_path}\' -Tail {lines}"'
        else:
            if mode == 'head':
                cmd = f"head -n {lines} {file_path}"
            elif mode == 'grep' and pattern:
                safe_pattern = pattern.replace("'", "'\\''")
                cmd = f"grep -E '{safe_pattern}' {file_path} | tail -n {lines}"
            elif since:
                cmd = f"awk -v since=\"{since}\" '{{print}}' {file_path} | tail -n {lines}"
            else:
                cmd = f"tail -n {lines} {file_path}"

        # 3. 执行读取
        result = self._ssh_tool.execute(host=host, command=cmd, timeout=60, skip_policy=True)
        if result.success:
            content = result.data.get('stdout', '')
            log_lines = [l for l in content.split('\n') if l.strip()]
            return ToolResult(
                success=True,
                data={
                    "content": content,
                    "line_count": len(log_lines),
                    "file_path": file_path,
                    "mode": mode,
                },
                metadata={"host": host, "file_path": file_path, "os_type": os_type}
            )
        return ToolResult(success=False, error=result.error)


class LogPlatformQueryTool(BaseTool):
    """日志平台查询工具 - 通过 API 查询 ELK/Loki/Fluentd 等日志平台

    支持多种日志平台：
    - elasticsearch: 直接查询 ES API
    - loki: Grafana Loki 日志聚合系统
    - custom: 自定义 REST API
    """

    name = "log_platform_query"
    description = "通过日志平台 API 查询应用日志（支持 ELK/Loki/自定义API）。需要先在 config.yaml 中配置日志平台连接信息。"
    parameters = [
        ToolParameter(name="platform", type="string", description="日志平台类型: elasticsearch, loki, custom"),
        ToolParameter(name="query", type="string", description="查询语句（ES: Query DSL, Loki: LogQL）"),
        ToolParameter(name="app_name", type="string", description="应用名称/服务名", required=False),
        ToolParameter(name="time_range", type="string", description="时间范围: 1h, 6h, 24h, 7d", required=False, default="1h"),
        ToolParameter(name="limit", type="integer", description="返回条数限制", required=False, default=500),
    ]

    def __init__(self, config=None):
        self._config = config
        self._platform_configs = {}
        if config and hasattr(config, 'log_platforms'):
            for p in config.log_platforms:
                self._platform_configs[p.name] = p

    def _parse_time_range(self, time_range: str) -> tuple:
        """解析时间范围为 start/end ISO 格式"""
        now = datetime.utcnow()
        if time_range.endswith('h'):
            hours = int(time_range[:-1])
            start = now - timedelta(hours=hours)
        elif time_range.endswith('d'):
            days = int(time_range[:-1])
            start = now - timedelta(days=days)
        else:
            start = now - timedelta(hours=1)
        return start.isoformat() + 'Z', now.isoformat() + 'Z'

    def _query_elasticsearch(self, platform_config, query: str, app_name: str, time_range: str, limit: int) -> ToolResult:
        """查询 Elasticsearch"""
        if not HAS_HTTPX:
            return ToolResult(success=False, error="httpx 未安装，请执行: pip install httpx")

        base_url = getattr(platform_config, 'url', 'http://localhost:9200')
        index = getattr(platform_config, 'index', 'logs-*')
        username = getattr(platform_config, 'username', '')
        password = getattr(platform_config, 'password', '')

        start_time, end_time = self._parse_time_range(time_range)

        # 构建 ES 查询
        es_query = {
            "query": {
                "bool": {
                    "must": [
                        {"range": {"@timestamp": {"gte": start_time, "lte": end_time}}}
                    ]
                }
            },
            "sort": [{"@timestamp": {"order": "desc"}}],
            "size": limit
        }

        # 添加应用名称过滤
        if app_name:
            es_query["query"]["bool"]["must"].append(
                {"match": {"kubernetes.labels.app": app_name}}
            )

        # 添加用户自定义查询
        if query and query.strip():
            try:
                custom_query = json.loads(query)
                if "query" in custom_query:
                    es_query["query"]["bool"]["must"].append(custom_query["query"])
            except json.JSONDecodeError:
                # 如果不是 JSON，当作简单查询字符串
                es_query["query"]["bool"]["must"].append(
                    {"query_string": {"query": query}}
                )

        try:
            auth = (username, password) if username and password else None
            url = f"{base_url}/{index}/_search"
            response = httpx.post(url, json=es_query, auth=auth, timeout=30)
            response.raise_for_status()
            data = response.json()

            hits = data.get('hits', {}).get('hits', [])
            logs = []
            for hit in hits:
                source = hit.get('_source', {})
                logs.append({
                    'timestamp': source.get('@timestamp', ''),
                    'message': source.get('message', str(source)),
                    'level': source.get('level', ''),
                    'app': source.get('kubernetes', {}).get('labels', {}).get('app', ''),
                })

            return ToolResult(
                success=True,
                data={
                    "logs": logs,
                    "total": data.get('hits', {}).get('total', {}).get('value', len(logs)),
                    "platform": "elasticsearch"
                }
            )

        except Exception as e:
            return ToolResult(success=False, error=f"ES 查询失败: {type(e).__name__}: {e}")

    def _query_loki(self, platform_config, query: str, app_name: str, time_range: str, limit: int) -> ToolResult:
        """查询 Grafana Loki"""
        if not HAS_HTTPX:
            return ToolResult(success=False, error="httpx 未安装，请执行: pip install httpx")

        base_url = getattr(platform_config, 'url', 'http://localhost:3100')

        # 构建 LogQL 查询
        if app_name:
            logql = f'{{app="{app_name}"}}'
        else:
            logql = '{job=~".+", level=~"ERROR|WARN"}'

        if query and query.strip():
            logql += f' |~ "{query}"'

        # 解析时间范围为纳秒时间戳
        now = datetime.utcnow()
        if time_range.endswith('h'):
            start = now - timedelta(hours=int(time_range[:-1]))
        elif time_range.endswith('d'):
            start = now - timedelta(days=int(time_range[:-1]))
        else:
            start = now - timedelta(hours=1)

        start_ns = int(start.timestamp() * 1e9)
        end_ns = int(now.timestamp() * 1e9)

        try:
            url = f"{base_url}/loki/api/v1/query_range"
            params = {
                "query": logql,
                "start": start_ns,
                "end": end_ns,
                "limit": limit,
                "direction": "backward"
            }
            response = httpx.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            result = data.get('data', {}).get('result', [])
            logs = []
            for stream in result:
                stream_labels = stream.get('stream', {})
                for value in stream.get('values', []):
                    logs.append({
                        'timestamp': value[0],
                        'message': value[1],
                        'level': stream_labels.get('level', ''),
                        'app': stream_labels.get('app', ''),
                    })

            return ToolResult(
                success=True,
                data={
                    "logs": logs,
                    "total": len(logs),
                    "platform": "loki"
                }
            )

        except Exception as e:
            return ToolResult(success=False, error=f"Loki 查询失败: {type(e).__name__}: {e}")

    def execute(self, **kwargs) -> ToolResult:
        platform = kwargs['platform'].lower()
        query = kwargs.get('query', '')
        app_name = kwargs.get('app_name', '')
        time_range = kwargs.get('time_range', '1h')
        limit = kwargs.get('limit', 500)

        # 获取平台配置
        platform_config = self._platform_configs.get(platform)
        if not platform_config:
            return ToolResult(
                success=False,
                error=f"未找到日志平台 '{platform}' 的配置，请在 config.yaml 的 log_platforms 中配置"
            )

        if platform == 'elasticsearch':
            return self._query_elasticsearch(platform_config, query, app_name, time_range, limit)
        elif platform == 'loki':
            return self._query_loki(platform_config, query, app_name, time_range, limit)
        else:
            return ToolResult(success=False, error=f"暂不支持日志平台类型: {platform}")


class LogAnalyzeTool(BaseTool):
    """日志分析工具 - 识别错误模式、统计异常频率、时间分布、应用级问题识别"""

    name = "log_analyze"
    description = "分析日志内容，识别错误模式、统计异常频率和时间分布。支持系统日志和应用日志。"
    parameters = [
        ToolParameter(name="content", type="string", description="日志文本内容"),
        ToolParameter(
            name="error_patterns",
            type="array",
            description="要匹配的错误模式列表（正则表达式）",
            required=False,
            default=None
        ),
        ToolParameter(
            name="log_type",
            type="string",
            description="日志类型: system(系统日志), application(应用日志), database(数据库日志)",
            required=False,
            default="application"
        ),
    ]

    # 通用错误模式
    DEFAULT_PATTERNS = [
        r'ERROR',
        r'CRITICAL',
        r'FATAL',
        r'Exception',
        r'Traceback',
        r'OutOfMemory',
        r'OutOfMemoryError',
        r'Segmentation fault',
        r'Connection refused',
        r'Connection reset',
        r'Timeout',
        r'deadlock',
        r'killed',
    ]

    # 应用日志特有模式
    APP_PATTERNS = [
        r'NullPointerException',
        r'ArrayIndexOutOfBoundsException',
        r'SQLException',
        r'IOException',
        r'ClassNotFoundException',
        r'NoClassDefFoundError',
        r'StackOverflowError',
        r'404\s+Not\s+Found',
        r'500\s+Internal\s+Server\s+Error',
        r'502\s+Bad\s+Gateway',
        r'503\s+Service\s+Unavailable',
        r'request\s+timeout',
        r'connection\s+pool\s+exhausted',
        r'heap\s+space',
        r'GC\s+overhead',
    ]

    # 数据库日志特有模式
    DB_PATTERNS = [
        r'ORA-\d+',
        r'DM-\d+',
        r'ERROR:\s+',
        r'FATAL:\s+',
        r'lock\s+timeout',
        r' deadlock',
        r'checkpoint\s+starting',
        r'checkpoint\s+complete',
        r'archive\s+mode',
        r'recovery',
    ]

    # 常见时间戳格式
    TIMESTAMP_PATTERNS = [
        re.compile(r'(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2})'),       # 2024-01-01 12:00
        re.compile(r'(\d{2}/\w{3}/\d{4}:\d{2}:\d{2})'),             # 01/Jan/2024:12:00
        re.compile(r'(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})'),      # Jan  1 12:00:00
        re.compile(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)'), # 2024-01-01 12:00:00.000
    ]

    def _get_patterns(self, log_type: str, custom_patterns: list = None) -> list:
        """根据日志类型获取错误模式"""
        if custom_patterns:
            return custom_patterns

        patterns = list(self.DEFAULT_PATTERNS)
        if log_type == 'application':
            patterns.extend(self.APP_PATTERNS)
        elif log_type == 'database':
            patterns.extend(self.DB_PATTERNS)
        return patterns

    def execute(self, **kwargs) -> ToolResult:
        content = kwargs['content']
        log_type = kwargs.get('log_type', 'application')
        custom_patterns = kwargs.get('error_patterns')
        patterns = self._get_patterns(log_type, custom_patterns)

        lines = content.split('\n')
        total_lines = len([l for l in lines if l.strip()])

        # 1. 错误行统计
        error_lines = []
        pattern_counts = Counter()
        for line in lines:
            for pattern in patterns:
                try:
                    if re.search(pattern, line, re.IGNORECASE):
                        error_lines.append(line)
                        pattern_counts[pattern] += 1
                        break  # 每行只计一次
                except re.error:
                    continue

        # 2. 时间分布分析
        time_distribution = Counter()
        for line in error_lines:
            for ts_pattern in self.TIMESTAMP_PATTERNS:
                m = ts_pattern.search(line)
                if m:
                    time_distribution[m.group(1)] += 1
                    break

        # 3. 错误率计算
        error_rate = round(len(error_lines) / max(total_lines, 1) * 100, 2)

        # 4. 严重程度评估
        severity = "normal"
        if error_rate > 20:
            severity = "critical"
        elif error_rate > 10:
            severity = "high"
        elif error_rate > 5:
            severity = "medium"
        elif error_rate > 1:
            severity = "low"

        # 5. 样本错误（去重，最多返回 10 条）
        unique_errors = list(dict.fromkeys(error_lines))[:10]

        # 6. 应用级问题识别
        app_issues = []
        if log_type == 'application':
            if any('connection pool exhausted' in l.lower() for l in error_lines):
                app_issues.append("数据库连接池耗尽")
            if any('heap space' in l.lower() or 'outofmemory' in l.lower() for l in error_lines):
                app_issues.append("内存溢出（堆空间不足）")
            if any('request timeout' in l.lower() for l in error_lines):
                app_issues.append("请求超时")
            if any('404' in l for l in error_lines):
                app_issues.append("资源未找到（404）")
            if any('500' in l or '502' in l or '503' in l for l in error_lines):
                app_issues.append("服务端错误（5xx）")

        return ToolResult(
            success=True,
            data={
                "total_lines": total_lines,
                "error_line_count": len(error_lines),
                "error_rate": error_rate,
                "severity": severity,
                "pattern_counts": dict(pattern_counts.most_common()),
                "time_distribution": dict(time_distribution.most_common(20)),
                "sample_errors": unique_errors,
                "app_issues": app_issues,
                "log_type": log_type,
            }
        )
