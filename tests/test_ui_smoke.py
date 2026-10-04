"""Executes every Streamlit page script against a stub `streamlit` module.

Catches import errors, NameErrors and broken wiring. It cannot judge layout: run `streamlit run app.py` for that.
"""
from __future__ import annotations

import runpy
import sys
import types
from pathlib import Path

from tests.helpers import ROOT, TempState, fixture

PAGES = sorted([ROOT / "app.py"] + list((ROOT / "pages").glob("*.py")))


class Stop(Exception):
    pass


_ST = None  # the active stub; containers (columns, tabs, sidebar...) delegate widget calls to it


def _any(*a, **k):
    return Ctx()


class Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        if _ST is not None and name in ST.__dict__ and not name.startswith("_"):
            return getattr(_ST, name)
        return _any

    def __bool__(self):
        return False


class ST(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state, self.secrets = {}, types.SimpleNamespace(get=lambda k, d=None: d)
        self.press, self.checked, self.sidebar = set(), set(), self
        self.__path__ = []

    def columns(self, spec, **k):
        return [Ctx() for _ in range(spec if isinstance(spec, int) else len(spec))]

    def tabs(self, labels):
        return [Ctx() for _ in labels]

    def button(self, label, *a, **k):
        return label in self.press

    def checkbox(self, label, value=False, **k):
        return bool(value) or any(c in label for c in self.checked)

    def selectbox(self, label, options, index=0, key=None, **k):
        options = list(options)
        v = self.session_state.get(key, options[index]) if key else options[index]
        if key:
            self.session_state[key] = v
        return v

    def multiselect(self, label, options, default=None, **k):
        return list(default or [])

    def radio(self, label, options, **k):
        return list(options)[0]

    def slider(self, label, min_value=None, max_value=None, value=None, **k):
        return value if value is not None else min_value

    def text_input(self, label, value="", **k):
        return value

    def text_area(self, label, value="", **k):
        return value

    def file_uploader(self, *a, **k):
        return None

    def data_editor(self, data, **k):
        return data

    def download_button(self, *a, **k):
        return False

    def stop(self):
        raise Stop

    def rerun(self):
        raise Stop

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _any


def _run(stub: ST, page: Path):
    sys.modules.pop("src.ui", None)
    try:
        runpy.run_path(str(page), run_name="__main__")
    except Stop:
        pass


def _install():
    global _ST
    stub = _ST = ST()
    comp, v1 = types.ModuleType("streamlit.components"), types.ModuleType("streamlit.components.v1")
    v1.html = _any
    comp.v1, stub.components = v1, comp
    saved = {k: sys.modules.get(k) for k in ("streamlit", "streamlit.components", "streamlit.components.v1")}
    sys.modules.update({"streamlit": stub, "streamlit.components": comp, "streamlit.components.v1": v1})
    return stub, saved


def _restore(saved):
    for k, v in saved.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v
    sys.modules.pop("src.ui", None)


def test_every_page_runs_with_defaults():
    stub, saved = _install()
    try:
        with TempState():
            for page in PAGES:
                stub.session_state.clear()
                _run(stub, page)
    finally:
        _restore(saved)
    assert len(PAGES) == 12


def test_content_queue_and_approvals_flow():
    stub, saved = _install()
    try:
        with TempState() as tmp:
            stub.session_state["engine"] = "offline"
            stub.press = {"Generate drafts"}
            _run(stub, ROOT / "pages" / "6_Content_Queue.py")
            assert (tmp / "drafts.json").exists()
            stub.press, stub.checked = {"Build patch"}, {"I have read"}
            stub.session_state.update(site_files={"index.html": fixture("kunergy_home.html")}, site_zip=None, site_prefix="", site_src="zip")
            _run(stub, ROOT / "pages" / "8_Approvals.py")
            patch = stub.session_state["patch"]
            assert "index.html" in patch.files and "assets/kunergy-premium.css" in patch.files
            assert not patch.qa.passed  # offline scaffolds contain [NEEDS CLIENT FACT] and are blocked
    finally:
        _restore(saved)
