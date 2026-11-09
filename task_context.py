"""TaskContext state management for astrbot_plugin_issue_agent."""

import asyncio
import time


class TaskContext:
    """Represents an ongoing coding agent task bound to a GitHub Issue."""

    def __init__(
        self,
        task_id: str,
        repo: str,
        issue_number: int,
        issue_url: str,
        title: str,
        prompt: str,
        initiator_id: str,
        unified_msg_origin: str,
    ):
        self.task_id = task_id
        self.repo = repo
        self.issue_number = issue_number
        self.issue_url = issue_url
        self.title = title
        self.prompt = prompt
        self.initiator_id = initiator_id
        self.unified_msg_origin = unified_msg_origin

        self.created_at = time.time()
        self.status = "SUBMITTED"  # SUBMITTED, PLANNING, WAITING_APPROVAL, WORKING, PR_SUBMITTED, DONE
        self.last_comment_id = 0
        self.known_pr_urls: set = set()

        # Human-in-the-loop decision sync
        self.decision_event = asyncio.Event()
        self.user_decision: str | None = None

    def set_waiting_approval(self):
        """Mark task as waiting for user response and clear decision event."""
        self.status = "WAITING_APPROVAL"
        self.decision_event.clear()
        self.user_decision = None

    def provide_decision(self, decision_text: str):
        """Provide user feedback to unlock the waiting worker."""
        self.user_decision = decision_text
        self.status = "WORKING"
        self.decision_event.set()


class TaskManager:
    """In-memory manager for active TaskContext instances."""

    def __init__(self):
        self._tasks: dict[str, TaskContext] = {}

    def add_task(self, task: TaskContext):
        self._tasks[task.task_id] = task

    def get_task(self, task_id: str) -> TaskContext | None:
        return self._tasks.get(task_id)

    def find_pending_approval_task_for_user(self, user_id: str) -> TaskContext | None:
        """Find the latest task currently waiting for approval from this user."""
        candidates = [
            t
            for t in self._tasks.values()
            if t.initiator_id == str(user_id) and t.status == "WAITING_APPROVAL"
        ]
        if candidates:
            # Sort by creation time descending (most recent first)
            candidates.sort(key=lambda t: t.created_at, reverse=True)
            return candidates[0]
        return None

    def remove_task(self, task_id: str):
        self._tasks.pop(task_id, None)

    def all_active_tasks(self) -> dict[str, TaskContext]:
        return dict(self._tasks)
