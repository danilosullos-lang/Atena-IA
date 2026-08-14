from core.consequence_memory import (
    ActionRecord,
    ConsequenceEpisode,
    ConsequenceEvidence,
    ConsequenceFeedback,
    ConsequenceMemory,
    Lesson,
)


def make_episode(outcome="success"):
    return ConsequenceEpisode(
        task_id="task-1",
        goal="validar uma alteração em sandbox",
        plan=["criar patch", "rodar testes", "verificar regressão"],
        actions=[ActionRecord(name="code.run_tests", status="executed", result_summary="8 passed")],
        outcome=outcome,
        outcome_summary="testes concluídos",
        confidence_before=0.4,
        confidence_after=0.8,
        regression_checked=True,
        regression_score=0.98,
        evidence=[ConsequenceEvidence(kind="test", claim="A suíte passou", independent=True)],
        lessons=[Lesson(statement="Testar em sandbox antes de promover", applicability="alterações de código")],
    )


def test_record_feedback_evidence_metrics_and_integrity(tmp_path):
    store = ConsequenceMemory(tmp_path / "consequences.sqlite3")
    episode = make_episode()
    episode_id = store.record_episode(episode)
    store.append_feedback(episode_id, ConsequenceFeedback(source="test", label="positive", text="resultado reproduzido", score=1))
    store.append_evidence(episode_id, ConsequenceEvidence(kind="metric", claim="score preservado", supports=True, independent=True))

    loaded = store.get_episode(episode_id)
    assert loaded is not None
    assert len(loaded.feedback) == 1
    assert len(loaded.evidence) == 2
    assert loaded.content_hash
    assert store.verify_integrity() is True
    assert store.metrics().successes == 1
    assert store.metrics().feedback_rate == 1
    store.close()


def test_idempotent_record_and_lesson_consolidation(tmp_path):
    store = ConsequenceMemory(tmp_path / "consequences.sqlite3")
    first = make_episode()
    second = make_episode()
    second.episode_id = "conseq-second"
    second.task_id = "task-2"
    store.record_episode(first)
    store.record_episode(first)
    store.record_episode(second)
    lessons = store.consolidate_lessons(min_evidence=2, min_confidence=0.5)
    assert len(store.recent(20)) == 2
    assert lessons
    assert lessons[0].status == "validated"
    assert store.lessons(validated_only=True)
    store.close()


def test_blocked_outcome_is_not_success(tmp_path):
    store = ConsequenceMemory(tmp_path / "consequences.sqlite3")
    store.record_episode(make_episode("blocked"))
    metrics = store.metrics()
    assert metrics.blocked == 1
    assert metrics.successes == 0
    assert metrics.success_rate == 0
    store.close()
