from taxagent.agent.diagram import STEPS, pipeline_dot, workflow_steps


def test_every_workflow_step_is_described():
    steps, _ = workflow_steps()

    # Add a step to the workflow without describing it here, and this fails
    assert set(steps) == set(STEPS)


def test_the_picture_follows_the_real_workflow_order():
    dot = pipeline_dot()

    _, arrows = workflow_steps()
    for source, target in arrows:
        if "__" not in source + target:  # the two ends are renamed, checked below
            assert f"{source} -> {target}" in dot


def test_the_picture_runs_from_the_sources_to_the_saved_result():
    dot = pipeline_dot()

    for arrow in [
        "sources -> ingest",
        "ingest -> raw",
        "raw -> extract",
        "finalize -> result",
    ]:
        assert arrow in dot


def test_people_and_ai_steps_are_marked():
    boxes = [line for line in pipeline_dot().splitlines() if "[label=" in line]
    lines = {line.split()[0]: line for line in boxes}

    assert "#F59E0B" in lines["sign_off"]  # orange: waits for a person
    assert "#9085E9" in lines["explain"]  # violet: the AI writes
    assert "#F59E0B" not in lines["compute"] and "#9085E9" not in lines["compute"]
