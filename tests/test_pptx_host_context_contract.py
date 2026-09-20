import re
from pathlib import Path


SOURCE = Path("web-components/pptx-presentation/src/index.js").read_text(encoding="utf-8")
STABLE = Path("web-components/pptx-presentation/0.1.7/index.js").read_text(encoding="utf-8")
SKILL = Path("web-components/pptx-presentation/SKILL.md").read_text(encoding="utf-8")
SKILL_TEXT = re.sub(r"\s+", " ", SKILL)


def test_released_and_candidate_runtime_forward_host_context():
    assert "this.context=undefined" in SOURCE
    assert "mod.buildDeck(PptxGenJS,this.context)" in SOURCE
    assert "this.context=void 0" in STABLE
    assert "buildDeck(ed,this.context)" in STABLE


def test_consumer_contract_keeps_context_opaque_and_host_owned():
    assert "Host-owned context and optional capabilities" in SKILL_TEXT
    assert "forwards that value unchanged" in SKILL_TEXT
    assert "does not define a TableGit schema" in SKILL_TEXT
    assert "not an HTML attribute or configuration DSL" in SKILL_TEXT
    assert "does not interpret, clone, serialize, persist or merge it into" in SKILL_TEXT


def test_capability_authentication_stays_with_host_page():
    assert "already operating in that page's" in SKILL_TEXT
    assert "must not prompt for an additional login" in SKILL_TEXT
    assert "manufacture" in SKILL_TEXT and "Authorization" in SKILL_TEXT
    assert "turn capability availability" in SKILL_TEXT


def test_context_does_not_expand_component_state_or_auth_surface():
    observed = re.search(
        r"static get observedAttributes\(\)\{return\[(.*?)\]\}",
        SOURCE,
    )
    state = re.search(r"getState\(\)\{return \{(.*?)\}\}", SOURCE)
    assert observed and "context" not in observed.group(1)
    assert state and "context" not in state.group(1)
    assert "Authorization" not in SOURCE
