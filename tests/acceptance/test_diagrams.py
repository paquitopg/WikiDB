"""Diagrams (draw.io Diagram Application) follow the rights of their space and load offline (U12; R21, R22, R26)."""

import re
import secrets
from urllib.parse import urlsplit

import pytest

from test_measures import client_for
from wikidb.client import PageRef

DENIED = (401, 403)
DIAGRAM_CLASS = "Diagram.DiagramClass"
EMPTY_DIAGRAM = '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel>'


@pytest.fixture
def diagram(world, robot):
    """A diagram created by an agent of A in A's private space, the way the diagram macro creates one."""
    a = world["agents"]["test-agent-a"]
    page = PageRef(("Bureaux", "A"), f"Flux-{secrets.token_hex(3)}")
    writer = client_for(a)
    writer.put_page(page, "Flux de données zorglubD", EMPTY_DIAGRAM)
    writer.add_object(page, DIAGRAM_CLASS, {})
    yield page
    robot.delete_page(page)


def test_diagram_is_editable_by_its_bureau_without_script_right(world, diagram):
    a2 = world["agents"]["test-agent-a2"]
    assert a2.get(diagram).status_code == 200
    assert a2.put(diagram, "Flux de données zorglubD", EMPTY_DIAGRAM.replace('id="1"', 'id="1" value="v2"')) \
        .status_code in (200, 201, 202)


def test_other_bureaux_get_nothing_from_the_diagram(world, diagram):
    for name in ("test-agent-b", "test-agent-s1"):
        agent = world["agents"][name]
        assert agent.get(diagram).status_code in DENIED, name
        assert "zorglubD" not in agent.view_html(diagram).text


def test_agents_cannot_create_diagrams_in_the_application_space(world):
    a = world["agents"]["test-agent-a"]
    assert a.put(PageRef(("Diagram",), "Detourne"), "Diagramme", EMPTY_DIAGRAM).status_code in DENIED


def test_diagram_editor_loads_resources_from_the_wiki_only(world, diagram, base_url):
    a = world["agents"]["test-agent-a"]
    path = "/".join(diagram.spaces) + "/" + diagram.name
    r = a.session.get(f"{a.base_url}/bin/edit/{path}", headers={"Accept": "text/html"})
    assert r.status_code == 200
    assert "draw" in r.text.lower() or "mxgraph" in r.text.lower()
    own = urlsplit(base_url).netloc
    sources = re.findall(r'(?:src|href)="(https?://[^"/]+)', r.text)
    assert {urlsplit(s).netloc for s in sources} <= {own}, sources
