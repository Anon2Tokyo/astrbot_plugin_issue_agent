"""Issue Agent 协同桥 (astrbot_plugin_issue_agent)

通过自然语言与人机双向交互，将 IM 消息自动转化为 GitHub Issue 并调度云端 AI Coding Agent（如 Google Jules、Devin 等）。
支持权限控制、后台异步跟踪、人机交互决策回传与 Bot 人设转述。
"""

import asyncio
import os
import sys

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Plain
from astrbot.api.star import Context, Star, register

# 确保插件目录在 sys.path 中
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from github_client import GitHubClient  # noqa: E402
from persona_renderer import render_persona_message  # noqa: E402
from task_context import TaskContext, TaskManager  # noqa: E402


@register(
    "astrbot_plugin_issue_agent",
    "soyorin",
    "将 IM 消息转化为 GitHub Issue 调度云端 Coding Agent（Jules/Devin等），支持双向人机决策与人设转述",
    "v1.0.0",
    "https://github.com/Anon2Tokyo/astrbot_plugin_issue_agent",
)
class IssueAgentPlugin(Star):
    """AstrBot plugin that bridges IM conversations with GitHub-based AI coding agents."""

    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.task_manager = TaskManager()
        self.github_client = GitHubClient(
            token=self.config.get("github_token", ""),
        )

    def is_admin(self, sender_id: str) -> bool:
        """Check if the sender is authorized to trigger and control coding agents."""
        admin_ids_cfg = str(self.config.get("admin_ids", "")).strip()
        if not admin_ids_cfg:
            # If not configured, allow by default or log warning
            logger.warning(
                "[IssueAgent] 未配置 admin_ids，默认允许操作。建议在配置中指定管理员 ID。"
            )
            return True
        allowed_ids = [
            i.strip() for i in admin_ids_cfg.replace("，", ",").split(",") if i.strip()
        ]
        return str(sender_id).strip() in allowed_ids

    def _get_target_repo(self, repo_param: str) -> str:
        """Resolve the target repository from parameter or default config."""
        repo = repo_param.strip() or self.config.get("default_repo", "").strip()
        if not repo or "/" not in repo:
            raise ValueError("未指定有效的目标 GitHub 仓库 (格式必须为 owner/repo)")
        return repo

    @filter.llm_tool(name="dispatch_coding_agent")
    async def dispatch_coding_agent(
        self,
        event: AstrMessageEvent,
        task_title: str,
        task_description: str,
        target_repo: str = "",
    ) -> str:
        """将用户的编程需求、Bug 修复或新功能开发任务分派给云端 Coding Agent（如 Google Jules 等）。

        Args:
            task_title (str): 任务简明标题，例如 '为 AstrBot 开发天气查询插件' 或 '修复内存泄漏 Bug'
            task_description (str): 详细的需求描述、实现步骤要求或技术指引
            target_repo (str): 目标 GitHub 仓库 (owner/repo)，若用户未明确指定仓库名则留空使用默认仓库
        """
        sender_id = str(event.get_sender_id())
        if not self.is_admin(sender_id):
            return "权限不足：当前仅管理员有权向云端 Coding Agent 分派编程任务。"

        token = self.config.get("github_token", "").strip()
        if not token:
            return "分派失败：尚未在 AstrBot 管理面板配置 GitHub Token (github_token)。"

        try:
            repo = self._get_target_repo(target_repo)
        except ValueError as e:
            return f"分派失败：{e}"

        agent_label = self.config.get("agent_label", "jules").strip() or "jules"

        # 构造 Issue 正文（包含需求说明以及由 AstrBot 自动分派的元信息）
        issue_body = (
            f"### 📋 任务描述\n\n{task_description}\n\n"
            f"---\n"
            f"*🤖 Dispatched by AstrBot Issue Agent Bridge*\n"
            f"*Initiator: `{sender_id}` | Target Agent Label: `{agent_label}`*"
        )

        try:
            issue_resp = await self.github_client.create_issue(
                repo=repo,
                title=f"[{agent_label.upper()}] {task_title}",
                body=issue_body,
                labels=[agent_label],
            )
        except Exception as exc:
            logger.error(f"[IssueAgent] 创建 GitHub Issue 失败: {exc}", exc_info=True)
            return f"创建云端任务失败，GitHub 接口报错: {exc}"

        issue_number = issue_resp.get("number", 0)
        issue_url = issue_resp.get("html_url", "")
        task_id = f"{repo}#{issue_number}"

        task = TaskContext(
            task_id=task_id,
            repo=repo,
            issue_number=issue_number,
            issue_url=issue_url,
            title=task_title,
            prompt=task_description,
            initiator_id=sender_id,
            unified_msg_origin=event.unified_msg_origin,
        )
        self.task_manager.add_task(task)

        # 启动后台非阻塞监听与决策状态机协程
        asyncio.create_task(self._track_task_lifecycle(task))

        return (
            f"成功创建任务！已向仓库 {repo} 提交 Issue #{issue_number} 并打上 [{agent_label}] 标签。"
            f"Issue 链接: {issue_url}。云端 Agent 已接单，正在后台沙箱中分析代码，有新进展或方案待确认时我会主动向您汇报！"
        )

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def intercept_decision_reply(self, event: AstrMessageEvent):
        """监听普通聊天消息。如果当前管理员有一个正在等待人机决策的任务，自动将回复同步回 Issue。"""
        sender_id = str(event.get_sender_id())
        pending_task = self.task_manager.find_pending_approval_task_for_user(sender_id)
        if not pending_task:
            return

        user_text = event.message_str.strip()
        # 忽略控制命令前缀
        if user_text.startswith("/") or user_text.startswith("!"):
            return

        # 判定为对正在等待的 Agent 任务进行人机决策回复
        logger.info(
            f"[IssueAgent] 捕获用户 {sender_id} 对任务 {pending_task.task_id} 的决策意见: {user_text}"
        )

        try:
            comment_body = (
                f"**[Decision Feedback from Admin via IM]**\n\n"
                f"{user_text}\n\n"
                f"*Synced by AstrBot Issue Agent Bridge*"
            )
            await self.github_client.add_comment(
                repo=pending_task.repo,
                issue_number=pending_task.issue_number,
                body=comment_body,
            )
        except Exception as e:
            logger.error(f"[IssueAgent] 同步决策评论到 GitHub 失败: {e}", exc_info=True)
            yield event.plain_result(f"⚠️ 同步决策到 GitHub 失败: {e}")
            return

        # 唤醒后台协程
        pending_task.provide_decision(user_text)

        yield event.plain_result(
            f"✅ 已将您的决策意见同步回 GitHub #{pending_task.issue_number}，云端 Agent 正在继续推进！"
        )
        event.stop_event()

    async def _track_task_lifecycle(self, task: TaskContext):
        """后台轮询 GitHub 任务进展与 PR 状态，驱动决策状态机。"""
        poll_interval = max(int(self.config.get("poll_interval", 20)), 10)
        enable_persona = bool(self.config.get("enable_persona_rewrite", True))
        auto_at = bool(self.config.get("auto_at_admin", True))

        logger.info(f"[IssueAgent] 启动后台监控协程: {task.task_id}")

        decision_keywords = [
            "?",
            "？",
            "确认",
            "选择",
            "which",
            "confirm",
            "approve",
            "option",
            "方案",
        ]

        while True:
            await asyncio.sleep(poll_interval)
            try:
                # 1. 检查 Issue 状态（如果已 Closed 则退出跟踪）
                issue_info = await self.github_client.get_issue(
                    task.repo, task.issue_number
                )
                if issue_info.get("state") == "closed":
                    logger.info(
                        f"[IssueAgent] 任务 {task.task_id} 对应的 Issue 已关闭，监控结束。"
                    )
                    self.task_manager.remove_task(task.task_id)
                    break

                # 2. 检查是否有新评论
                comments = await self.github_client.get_issue_comments(
                    task.repo, task.issue_number
                )
                for comment in comments:
                    cid = comment.get("id", 0)
                    if cid <= task.last_comment_id:
                        continue
                    task.last_comment_id = cid

                    body = comment.get("body", "")
                    # 忽略自己同步上去的评论
                    if "Synced by AstrBot" in body or "Dispatched by AstrBot" in body:
                        continue

                    # 判断是否包含需要人工确认的问题或方案
                    needs_decision = any(kw in body.lower() for kw in decision_keywords)

                    if needs_decision:
                        task.set_waiting_approval()
                        action_type = "decision_required"
                    else:
                        task.status = "WORKING"
                        action_type = "progress"

                    # 润色或生成通知内容
                    if enable_persona:
                        styled_msg = await render_persona_message(
                            self.context,
                            raw_message=body,
                            action_type=action_type,
                            task_title=task.title,
                        )
                    else:
                        styled_msg = (
                            f"【Issue #{task.issue_number} 新动态】\n{body[:500]}"
                        )

                    # 推送消息到原聊天会话
                    msg_chain = []
                    if auto_at and task.initiator_id:
                        msg_chain.append(
                            At(
                                qq=int(task.initiator_id)
                                if task.initiator_id.isdigit()
                                else task.initiator_id
                            )
                        )
                        msg_chain.append(Plain(" "))
                    msg_chain.append(Plain(styled_msg))

                    await self.context.send_message(task.unified_msg_origin, msg_chain)

                    # 如果进入等待决策状态，挂起协程直到用户回复
                    if needs_decision:
                        logger.info(
                            f"[IssueAgent] 任务 {task.task_id} 进入等待用户决策状态，挂起协程。"
                        )
                        await task.decision_event.wait()
                        logger.info(
                            f"[IssueAgent] 收到用户决策，任务 {task.task_id} 恢复运行。"
                        )

                # 3. 检查是否有新的关联 PR 提交
                prs = await self.github_client.check_pull_requests(
                    task.repo, task.issue_number
                )
                for pr in prs:
                    pr_url = pr.get("html_url", "")
                    if pr_url and pr_url not in task.known_pr_urls:
                        task.known_pr_urls.add(pr_url)
                        task.status = "PR_SUBMITTED"

                        pr_title = pr.get("title", "")
                        raw_msg = f"已创建 Pull Request: {pr_title}\nPR 链接: {pr_url}"

                        if enable_persona:
                            notify_text = await render_persona_message(
                                self.context,
                                raw_message=raw_msg,
                                action_type="completed",
                                task_title=task.title,
                            )
                        else:
                            notify_text = f"🎉 任务已完成！\n{raw_msg}"

                        msg_chain = []
                        if auto_at and task.initiator_id:
                            msg_chain.append(
                                At(
                                    qq=int(task.initiator_id)
                                    if task.initiator_id.isdigit()
                                    else task.initiator_id
                                )
                            )
                            msg_chain.append(Plain(" "))
                        msg_chain.append(Plain(notify_text))

                        await self.context.send_message(
                            task.unified_msg_origin, msg_chain
                        )

            except Exception as loop_err:
                logger.warning(f"[IssueAgent] 后台跟踪循环发生异常: {loop_err}")
                await asyncio.sleep(poll_interval)

    @filter.command_group("agent")
    def agent_group(self):
        """Issue Agent 协同桥管理指令组"""
        pass

    @agent_group.command("tasks")
    async def list_tasks(self, event: AstrMessageEvent):
        """查看当前正在后台跟踪的所有云端 Agent 任务"""
        tasks = self.task_manager.all_active_tasks()
        if not tasks:
            yield event.plain_result("当前没有正在运行的云端 Agent 任务。")
            return

        lines = ["📌 当前正在运行的 Agent 任务列表："]
        for tid, t in tasks.items():
            lines.append(f"- [{t.status}] {tid}: {t.title}\n  链接: {t.issue_url}")
        yield event.plain_result("\n".join(lines))

    @agent_group.command("cancel")
    async def cancel_task(self, event: AstrMessageEvent, task_id: str):
        """停止对指定任务的后台监听: /agent cancel <owner/repo#number>"""
        if not self.is_admin(str(event.get_sender_id())):
            yield event.plain_result("权限不足：仅管理员可取消任务。")
            return

        task = self.task_manager.get_task(task_id.strip())
        if not task:
            yield event.plain_result(f"未找到 ID 为 '{task_id}' 的活跃任务。")
            return

        self.task_manager.remove_task(task_id.strip())
        yield event.plain_result(f"已停止对任务 {task_id} 的后台跟踪。")
