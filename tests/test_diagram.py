from taxagent.agent.diagram import STEPS, describe, pipeline, workflow_order


def test_every_workflow_step_is_described():
    # Add a step to the workflow without describing it, and this fails
    assert set(workflow_order()) == set(STEPS)


def test_the_steps_are_in_the_order_the_workflow_runs_them():
    assert workflow_order() == [
        "extract",
        "human_review",
        "compute",
        "explain",
        "summarize",
        "sign_off",
        "finalize",
    ]


def test_the_picture_runs_from_the_sources_to_the_saved_result():
    names = [box["name"] for box in pipeline()]

    assert names[:4] == ["sources", "ingest", "raw", "extract"]
    assert names[-2:] == ["finalize", "result"]


def test_people_and_ai_steps_are_marked():
    kinds = {box["name"]: box["kind"] for box in pipeline()}

    waits_for_a_person = {name for name, kind in kinds.items() if kind == "human"}
    written_by_ai = {name for name, kind in kinds.items() if kind == "ai"}
    assert waits_for_a_person == {"human_review", "sign_off"}
    assert written_by_ai == {"explain", "summarize"}
    assert kinds["compute"] == "code"  # the math is never the AI's job


def test_every_box_says_what_it_does_and_what_it_is_built_with():
    for box in pipeline():
        assert box["title"] and box["what"] and box["tools"]


def test_only_workflow_steps_are_inside_the_workflow():
    inside = [box["name"] for box in pipeline() if box["in_workflow"]]

    assert inside == workflow_order()


def test_a_step_can_be_looked_up_by_name_for_the_trace():
    step = describe("compute")

    assert (step["title"], step["kind"]) == ("Compute", "code")
    assert step["tools"] == ["plain Python", "Decimal"]
