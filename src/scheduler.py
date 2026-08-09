"""定时任务调度器 - 基于 APScheduler"""

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .tools.base import ToolRegistry
from .utils.logger import get_logger
from .utils.helpers import truncate_text

logger = get_logger("scheduler")


class OpsScheduler:
    """运维定时任务调度器

    支持的定时任务：
    - inspection: 服务器/数据库巡检
    - log_analysis: 日志分析
    """

    def __init__(self, master_agent, config):
        self.master_agent = master_agent
        self.config = config
        self.scheduler = BackgroundScheduler(
            timezone='Asia/Shanghai',
            job_defaults={
                'coalesce': True,       # 合并错过的任务
                'max_instances': 1,     # 同一任务最多1个实例
                'misfire_grace_time': 300,  # 错过执行窗口5分钟内仍然执行
            }
        )

    def setup(self):
        """根据配置注册定时任务"""
        schedule_config = self.config.schedule

        # 服务器巡检任务
        inspection_cfg = schedule_config.get('inspection', {})
        if inspection_cfg.get('enabled', False):
            cron_expr = inspection_cfg.get('cron', '0 */6 * * *')
            self._add_cron_job(
                self._run_inspection,
                cron_expr,
                'inspection',
                '服务器巡检',
            )

        # 日志分析任务
        log_analysis_cfg = schedule_config.get('log_analysis', {})
        if log_analysis_cfg.get('enabled', False):
            cron_expr = log_analysis_cfg.get('cron', '0 */2 * * *')
            self._add_cron_job(
                self._run_log_analysis,
                cron_expr,
                'log_analysis',
                '日志分析',
            )

    def _add_cron_job(self, func, cron_expr: str, job_id: str, job_name: str):
        """添加 cron 定时任务"""
        try:
            parts = cron_expr.strip().split()
            if len(parts) != 5:
                logger.error(f"无效的 cron 表达式: {cron_expr}")
                return

            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )

            self.scheduler.add_job(
                func,
                trigger=trigger,
                id=job_id,
                name=job_name,
                replace_existing=True,
            )
            logger.info(f"定时任务已注册: [{job_name}] cron={cron_expr}")
        except Exception as e:
            logger.error(f"注册定时任务失败 [{job_name}]: {e}")

    def _run_inspection(self):
        """定时巡检任务"""
        logger.info("=" * 50)
        logger.info(f"定时巡检任务开始 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
        logger.info("=" * 50)

        try:
            servers = [s for s in self.config.servers if s.host]
            if not servers:
                logger.warning("没有配置服务器，跳过巡检")
                return

            server_list = ", ".join([f"{s.name or s.host}" for s in servers])
            task = f"请对所有服务器进行完整巡检。服务器列表: {server_list}"

            # 在新的事件循环中运行异步任务
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(self.master_agent.run(task))
                report = result.get('final_report', '巡检完成')

                # 发送巡检报告通知
                self._notify_report("运维巡检报告", report, "info")

                # 如果有异常，发送告警邮件
                if self._has_issues(report):
                    self._send_email_alert("运维巡检告警", report, "warning")

                logger.info("定时巡检任务完成")
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"定时巡检任务失败: {e}")
            self._notify_report("巡检任务失败", f"错误: {type(e).__name__}: {e}", "error")
            self._send_email_alert("巡检任务失败", f"错误: {type(e).__name__}: {e}", "error")

    def _run_log_analysis(self):
        """定时日志分析任务"""
        logger.info("=" * 50)
        logger.info(f"定时日志分析任务开始 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
        logger.info("=" * 50)

        try:
            servers = [s for s in self.config.servers if s.host]
            if not servers:
                logger.warning("没有配置服务器，跳过日志分析")
                return

            server_list = ", ".join([s.name or s.host for s in servers])
            task = (
                f"分析以下服务器的最新日志，识别错误和异常。\n"
                f"服务器: {server_list}\n"
                f"重点检查: /var/log/syslog, /var/log/nginx/error.log"
            )

            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(self.master_agent.run(task))
                report = result.get('final_report', '日志分析完成')

                # 只在有异常时发送通知和邮件告警
                if self._has_issues(report):
                    self._notify_report("日志分析告警", report, "warning")
                    self._send_email_alert("日志分析告警", report, "warning")
                logger.info("定时日志分析任务完成")
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"定时日志分析任务失败: {e}")
            self._notify_report("日志分析任务失败", f"错误: {type(e).__name__}: {e}", "error")
            self._send_email_alert("日志分析任务失败", f"错误: {type(e).__name__}: {e}", "error")

    def _notify_report(self, title: str, content: str, level: str):
        """发送报告通知（企业微信/钉钉）"""
        notify_tool = ToolRegistry.get("send_notification")
        if not notify_tool:
            logger.warning("通知工具未注册，跳过通知发送")
            return

        try:
            truncated = truncate_text(content, 2000)
            notify_tool.execute(
                title=title,
                content=truncated,
                level=level,
                channel="all",
            )
        except Exception as e:
            logger.error(f"发送通知失败: {e}")

    def _send_email_alert(self, title: str, content: str, level: str = "warning"):
        """发送告警邮件"""
        email_tool = ToolRegistry.get("send_email")
        if not email_tool:
            logger.warning("邮件工具未注册，跳过邮件告警")
            return

        try:
            # 转换为 HTML 格式
            html_body = content.replace("\n", "<br>")
            result = email_tool.send_alert(
                subject=title,
                body=html_body,
                level=level,
            )
            if result["success"]:
                logger.info(f"告警邮件已发送: {title}")
            else:
                logger.warning(f"告警邮件发送失败: {result['message']}")
        except Exception as e:
            logger.error(f"发送告警邮件异常: {e}")

    def _has_issues(self, report: str) -> bool:
        """检查报告中是否有异常"""
        if not report:
            return False
        issue_keywords = ['异常', '告警', '错误', 'error', 'warning', 'critical', '失败']
        return any(kw in report.lower() for kw in issue_keywords)

    def start(self):
        """启动调度器"""
        self.setup()
        self.scheduler.start()
        logger.info("调度器已启动")

    def stop(self):
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("调度器已停止")

    def get_jobs(self) -> list:
        """获取所有已注册的定时任务"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
        return jobs
