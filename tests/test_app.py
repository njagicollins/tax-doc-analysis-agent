"""Smoke test: start the app without a browser and open every tab.

The last lines of app.py connect each tab to its page. No other test touches
them, which is how three tabs went blank in Phase 7 while every test passed.
"""

from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

from taxagent.agent.runner import resume_run, start_run
from tests.test_workflow import fake_llm, full_review, sign_off, world  # noqa: F401

APP = Path(__file__).parents[1] / "src" / "taxagent" / "app.py"
TABS = ["Runs", "Dashboard", "How it works", "Audit"]


def open_app() -> AppTest:
    st.cache_resource.clear()  # the app keeps one database connection: start fresh
    return AppTest.from_file(str(APP), default_timeout=60).run()


def assert_every_tab_shows_something(app: AppTest) -> None:
    assert not app.exception, app.exception
    assert [tab.label for tab in app.tabs] == TABS
    for tab in app.tabs:
        assert len(tab.children) > 0, f"the {tab.label} tab is empty"


def test_every_tab_works_before_any_run(world):  # noqa: F811
    assert_every_tab_shows_something(open_app())


def test_every_tab_works_after_a_signed_run(world):  # noqa: F811
    run = start_run("2026Q2", make_llm=fake_llm)
    resume_run(run["run_id"], full_review("alice"), make_llm=fake_llm)
    resume_run(run["run_id"], sign_off("bob"), make_llm=fake_llm)

    assert_every_tab_shows_something(open_app())
