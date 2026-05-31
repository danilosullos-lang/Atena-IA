import threading

import modules.multi_agent_orchestrator as orchestrator_module
from modules.multi_agent_orchestrator import Agent, MultiAgentOrchestrator


class _RunningBridge:
    def is_paused(self) -> bool:
        return False


def test_failed_agent_task_requeued_once_per_attempt(monkeypatch):
    monkeypatch.setattr(orchestrator_module, "AtenaControlBridge", lambda: _RunningBridge())

    orchestrator = MultiAgentOrchestrator()
    orchestrator.max_retries = 3

    def failing_handler(task):
        orchestrator._stop_event.set()
        raise RuntimeError("boom")

    orchestrator.register_agent(
        Agent(
            "failing-agent",
            "Tester",
            ["failure_test"],
            failing_handler,
        )
    )

    task = {
        "description": "exercise retry path",
        "required_capabilities": ["failure_test"],
    }
    orchestrator.submit_task(task)

    worker = threading.Thread(target=orchestrator._worker_loop)
    worker.start()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert task["_retries"] == 1
    assert orchestrator.task_queue.qsize() == 1
    assert orchestrator.task_queue.get_nowait() is task
