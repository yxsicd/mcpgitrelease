import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def load_json(path):
    return json.loads(text(path))


class AgentFirstWebComponentCompositionTests(unittest.TestCase):
    def test_agent_composition_is_discoverable_from_every_public_entrypoint(self):
        root_skill = text("SKILL.md")
        registry_skill = text("web-components/SKILL.md")
        runtime_skill = text("web-components/mcpgit-runtime/SKILL.md")
        presentation_skill = text("web-components/pptx-presentation/SKILL.md")

        self.assertIn("agent-composition: ./web-components/AGENT_COMPOSITION.md", root_skill)
        self.assertIn("composition: ./AGENT_COMPOSITION.md", registry_skill)
        self.assertIn("composition: ../AGENT_COMPOSITION.md", runtime_skill)
        self.assertIn("composition: ../AGENT_COMPOSITION.md", presentation_skill)

    def test_recipe_uses_stable_discovery_and_composes_without_new_runtime_api(self):
        recipe = text("web-components/AGENT_COMPOSITION.md")

        self.assertIn("channels/stable.json", recipe)
        self.assertIn("loadComponent('mcpgit-runtime')", recipe)
        self.assertIn("loadComponent('pptx-presentation')", recipe)
        self.assertIn("runtime.connect({ endpoint: '/mcp' })", recipe)
        self.assertIn("presentation.context = {", recipe)
        self.assertIn("mcpgit: client", recipe)
        self.assertIn("presentation.src = './deck.js'", recipe)
        self.assertIn("mcpgit.skills.list()", recipe)
        self.assertIn("mcpgit.at({", recipe)
        self.assertIn("mcpgit.call(", recipe)
        self.assertIn("does not add a runtime API", recipe)

        self.assertNotIn("mcpgit-runtime-v0.1.2", recipe)
        self.assertNotIn("pptx-presentation-v0.1.8", recipe)

    def test_stable_registry_and_catalog_keep_both_composed_components_consistent(self):
        channel = load_json("web-components/channels/stable.json")
        registry_path = (ROOT / "web-components" / "channels" / channel["registry"]).resolve()
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        catalog = load_json("web-components/catalog.json")
        catalog_by_id = {item["id"]: item for item in catalog["components"]}

        for component_id in ("mcpgit-runtime", "pptx-presentation"):
            released = registry["components"][component_id]
            catalog_item = catalog_by_id[component_id]
            manifest = load_json(catalog_item["manifest"])
            self.assertEqual(catalog_item["version"], released["version"])
            self.assertEqual(released["version"], manifest["version"])
            self.assertEqual(catalog_item["integrity"], released["integrity"])
            self.assertEqual(released["integrity"], manifest["artifact"]["integrity"])

    def test_recipe_respects_host_owned_auth_and_projection_policy_boundary(self):
        recipe = text("web-components/AGENT_COMPOSITION.md")

        self.assertIn("Do not put Basic credentials, Authorization headers", recipe)
        self.assertIn("the host owns authentication", recipe)
        self.assertIn("the projection owns repositories, table schemas, business facts", recipe)
        self.assertIn("does not discover privileged objects from ambient", recipe)


if __name__ == "__main__":
    unittest.main()
