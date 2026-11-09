"""Persona renderer for transforming GitHub updates into in-character bot messages."""

import logging

logger = logging.getLogger("astrbot_plugin_issue_agent")


async def render_persona_message(
    context,
    raw_message: str,
    action_type: str = "progress",
    task_title: str = "",
) -> str:
    """Rewrite a technical GitHub event into an in-character message using the bot's active LLM.

    Args:
        context: AstrBot plugin Context
        raw_message: Raw comment or PR description from GitHub Agent
        action_type: 'progress', 'decision_required', or 'completed'
        task_title: Title of the task

    Returns:
        Rendered message string.
    """
    if action_type == "decision_required":
        instruction = (
            "云端编程 Agent 提出了关键问题或待确认方案，急需主人决策。"
            "请以你的角色人设，用 1~3 句话提醒主人并概括核心要点，引导主人直接在群里回复你的决策意见。"
        )
    elif action_type == "completed":
        instruction = (
            "云端编程 Agent 已经完成了代码编写并提交了 Pull Request。"
            "请以你的角色人设，高兴且简洁地通知主人任务已完工，并附带提醒主人前往查看验收。"
        )
    else:
        instruction = (
            "云端编程 Agent 有了新的代码编写进度。"
            "请以你的角色人设，用 1~2 句话简要向主人通报最新进展，保持亲切自然，不要大段照搬技术细节。"
        )

    prompt = (
        f"【任务指示】\n{instruction}\n\n"
        f"【当前任务名称】: {task_title}\n"
        f"【原始进展内容】:\n{raw_message[:1000]}\n\n"
        f"【要求】: 直接输出你要发送给主人的回复文本，不要输出任何多余的解释或前缀。"
    )

    try:
        provider = context.get_using_provider()
        if provider:
            response = await provider.text_chat(prompt=prompt)
            if response and response.completion_text:
                return response.completion_text.strip()
    except Exception as e:
        logger.warning(f"Persona rewrite failed, falling back to clean format: {e}")

    # Fallback if LLM is unavailable or fails
    if action_type == "decision_required":
        return f"💡 **【Jules 方案待确认】**\n任务：{task_title}\n\n{raw_message}\n\n👉 请直接在群里回复你的决策意见，我将自动同步回云端！"
    elif action_type == "completed":
        return f"🎉 **【代码任务完成】**\n任务：{task_title}\n\n{raw_message}"
    else:
        return f"📌 **【Jules 最新进展】**\n任务：{task_title}\n\n{raw_message}"
