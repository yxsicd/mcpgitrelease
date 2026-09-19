import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_maintainer_skills_are_not_in_public_skill_index():
    index = json.loads((ROOT / "metadata" / "skills.json").read_text(encoding="utf-8"))
    paths = {item["path"] for item in index["skills"]}
    assert all(not path.startswith(".agents/") for path in paths)
    assert (ROOT / ".agents" / "skills" / "pptx-presentation-maintainer" / "SKILL.md").is_file()


def test_pptx_maintainer_skill_routes_to_public_consumer_contract():
    text = (ROOT / ".agents" / "skills" / "pptx-presentation-maintainer" / "SKILL.md").read_text(encoding="utf-8")
    assert "thin Presentation Runtime for CodeAgent" in text
    assert "ordinary JavaScript" in text
    assert "imperative primitive" in text
    assert "web-components/pptx-presentation/SKILL.md" in text
