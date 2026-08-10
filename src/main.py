"""运维 Agent 主入口 - CLI 交互模式 / 守护进程模式 / Web 管理平台模式 / 单次执行模式"""

import asyncio
import signal
import sys
import argparse

from .utils.config_loader import ConfigLoader
from .utils.logger import setup_logging, get_logger
from .tools import register_all_tools
from .tools.base import ToolRegistry
from .tools.ssh_tools import SSHConnectionPool
from .agent.master_agent import MasterAgent
from .scheduler import OpsScheduler

logger = get_logger("main")


class OpsAgentApp:
    """运维 Agent 应用"""

    def __init__(self, config_dir: str = "config"):
        # 1. 加载配置
        self.config_loader = ConfigLoader.get_instance()
        self.config = self.config_loader.load(config_dir)

        # 2. 初始化日志
        setup_logging(self.config.log_level)

        # 3. 注册所有工具
        register_all_tools(self.config)
        logger.info(f"工具注册完成: {ToolRegistry.get_names()}")

        # 4. 创建 Master Agent
        self.master_agent = MasterAgent(self.config)

        # 5. 创建调度器
        self.scheduler = OpsScheduler(self.master_agent, self.config)

    async def run_cli(self):
        """CLI 交互模式"""
        print()
        print("=" * 60)
        print("  🔧 运维 Agent - 交互模式")
        print("  输入运维任务描述，按 Enter 执行")
        print("  输入 'quit' 或 'exit' 退出")
        print("  输入 'help' 查看帮助")
        print("=" * 60)
        print()

        while True:
            try:
                user_input = input("🤖 > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                break

            if not user_input:
                continue

            if user_input.lower() in ('quit', 'exit', 'q'):
                print("再见！")
                break

            if user_input.lower() == 'help':
                self._print_help()
                continue

            if user_input.lower() == 'tools':
                print(f"\n已注册工具 ({len(ToolRegistry.get_names())}):")
                for name in ToolRegistry.get_names():
                    tool = ToolRegistry.get(name)
                    print(f"  - {name}: {tool.description}")
                print()
                continue

            if user_input.lower() == 'servers':
                if self.config.servers:
                    print(f"\n已配置服务器 ({len(self.config.servers)}):")
                    for s in self.config.servers:
                        dbs = ", ".join([d.type for d in s.databases]) if s.databases else "无"
                        print(f"  - {s.name or s.host} ({s.host}:{s.port}) [{', '.join(s.tags)}] DB: {dbs}")
                    print()
                else:
                    print("\n未配置服务器\n")
                continue

            if user_input.lower() == 'jobs':
                jobs = self.scheduler.get_jobs()
                if jobs:
                    print(f"\n定时任务 ({len(jobs)}):")
                    for job in jobs:
                        print(f"  - [{job['id']}] {job['name']}")
                        print(f"    下次执行: {job['next_run']}")
                        print(f"    触发器: {job['trigger']}")
                    print()
                else:
                    print("\n未注册定时任务\n")
                continue

            # 执行任务
            print("\n⏳ 正在处理任务...")
            try:
                result = await self.master_agent.run(user_input)
                report = result.get('final_report', '任务完成')

                print("\n" + "=" * 60)
                print(report)
                print("=" * 60 + "\n")
            except Exception as e:
                logger.error(f"任务执行失败: {e}")
                print(f"\n❌ 错误: {e}\n")

    async def run_once(self, task: str):
        """执行单次任务"""
        logger.info(f"执行单次任务: {task}")
        result = await self.master_agent.run(task)
        report = result.get('final_report', '任务完成')
        print(report)
        return result

    def start(self, mode: str = "cli"):
        """启动应用

        Args:
            mode: 运行模式 (cli/daemon/web)
        """
        # 设置事件循环策略
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 注册信号处理
        def signal_handler(sig, frame):
            logger.info("接收到终止信号，正在关闭...")
            self._shutdown()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            if mode == "cli":
                loop.run_until_complete(self.run_cli())
            elif mode == "daemon":
                self.scheduler.start()
                logger.info("守护进程模式已启动，按 Ctrl+C 退出")
                print(f"\n🔧 运维 Agent 守护进程已启动")
                print(f"   已注册定时任务: {len(self.scheduler.get_jobs())}")
                print(f"   按 Ctrl+C 退出\n")
                loop.run_forever()
            elif mode == "web":
                from .web.app import create_app
                from .web.core.config_manager import AppConfigManager
                import uvicorn
                AppConfigManager.init_app(self)
                app = create_app(self)
                uvicorn.run(app, host=self.config.web.host, port=self.config.web.port)
            else:
                logger.error(f"未知的运行模式: {mode}")
                print(f"错误: 未知的运行模式 '{mode}'，请使用 'cli'、'daemon' 或 'web'")
                sys.exit(1)
        finally:
            self._shutdown()
            loop.close()

    def _shutdown(self):
        """优雅关闭"""
        logger.info("正在关闭应用...")
        self.scheduler.stop()
        SSHConnectionPool.close_all()
        logger.info("应用已关闭")


def _print_help():
    """打印帮助信息"""
    print("""
可用命令:
  help          显示此帮助信息
  tools         查看已注册的工具
  servers       查看已配置的服务器
  jobs          查看定时任务
  quit/exit     退出程序

任务示例:
  巡检服务器 192.168.1.10
  诊断数据库连接异常
  分析 192.168.1.10 的 nginx 错误日志
  对所有服务器进行巡检
  检查 Redis 内存使用情况
""")


def main():
    """主入口函数"""
    parser = argparse.ArgumentParser(
        description="🔧 运维 Agent - 智能服务器/数据库巡检、故障诊断、日志分析、自愈处理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python -m src.main                          # CLI 交互模式
  python -m src.main --mode daemon            # 守护进程模式
  python -m src.main --mode web               # Web 管理平台模式
  python -m src.main --task "巡检所有服务器"    # 单次执行任务
  python -m src.main --config /etc/ops-agent  # 指定配置目录
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["cli", "daemon", "web"],
        default="cli",
        help="运行模式: cli(交互模式, 默认), daemon(守护进程模式), web(Web 管理平台模式)"
    )
    parser.add_argument(
        "--task",
        type=str,
        help="执行单次任务（非交互模式）"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config",
        help="配置文件目录（默认: config）"
    )

    args = parser.parse_args()

    try:
        app = OpsAgentApp(config_dir=args.config)

        if args.task:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(app.run_once(args.task))
            finally:
                app._shutdown()
                loop.close()
        else:
            app.start(args.mode)

    except Exception as e:
        logger.error(f"应用启动失败: {e}")
        print(f"\n❌ 应用启动失败: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
