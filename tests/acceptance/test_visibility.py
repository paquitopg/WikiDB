"""Visibility matrix and baseline security on a provisioned dev wiki (U4, U5; AE1-AE9, R6-R11, R17, R22)."""

from wikidb.client import PageRef

DENIED = (401, 403)


def test_ae1_sector_agent_finds_nothing_of_another_sector(world):
    a = world["agents"]["test-agent-a"]
    assert a.search("zorglubB") == []
    assert a.get(world["pages"]["b_secteur"]).status_code in DENIED


def test_ae2_synthesis_agent_reads_but_cannot_edit_a_sector_sheet(world):
    s1 = world["agents"]["test-agent-s1"]
    sheet = world["pages"]["b_secteur"]
    assert s1.get(sheet).status_code == 200
    assert s1.search("zorglubB") != []
    assert s1.put(sheet, "Modifié", "x").status_code in DENIED


def test_ae3_sector_agent_sees_synthesis_perimeter_but_not_synthesis_bureau_sector(world):
    a = world["agents"]["test-agent-a"]
    assert a.get(world["pages"]["s1_synthese"]).status_code == 200
    assert a.get(world["pages"]["s1_secteur"]).status_code in DENIED
    assert a.search("zorglubS") == []


def test_ae4_synthesis_perimeter_sheet_is_read_only_for_other_bureaux(world):
    a = world["agents"]["test-agent-a"]
    assert a.put(world["pages"]["s1_synthese"], "Modifié", "x").status_code in DENIED


def test_owner_bureau_edits_its_own_sheets(world):
    a = world["agents"]["test-agent-a"]
    assert a.put(world["pages"]["a_secteur"], "Mesure fictive A secteur zorglubA", "Mise à jour.").status_code \
        in (200, 201, 202)


def test_ae5_link_to_a_hidden_sheet_does_not_reveal_its_title(world):
    a2 = world["agents"]["test-agent-a2"]
    html = a2.view_html(world["pages"]["a_links_b"]).text
    assert "Mesure fictive A avec lien" in html
    assert "zorglubB" not in html


def test_ae7_listed_agent_without_bureau_sees_common_area_and_synthesis_only(world):
    agent = world["agents"]["test-agent-nobureau"]
    assert agent.get(world["pages"]["s1_synthese"]).status_code == 200
    assert agent.get(PageRef(("Glossaire",))).status_code == 200
    assert agent.get(world["pages"]["a_secteur"]).status_code in DENIED
    assert agent.get(PageRef(("Bureaux", "A"))).status_code in DENIED


def test_ae9_signed_in_user_absent_from_hr_listing_sees_nothing(world):
    outsider = world["agents"]["test-outsider"]
    for page in (world["pages"]["s1_synthese"], PageRef(("Glossaire",)), PageRef(("Main",))):
        assert outsider.get(page).status_code in DENIED, page
    assert outsider.search("zorglubT") == []


def test_private_bureau_space_is_closed_to_other_bureaux_including_synthesis(world):
    assert world["agents"]["test-agent-a"].get(PageRef(("Bureaux", "A"))).status_code == 200
    for name in ("test-agent-b", "test-agent-s1"):
        assert world["agents"][name].get(PageRef(("Bureaux", "A"))).status_code in DENIED, name


def test_guest_sees_no_content(world):
    guest = world["agents"]["guest"]
    assert guest.get(world["pages"]["s1_synthese"]).status_code in DENIED
    assert guest.search("zorglubT") == []


def test_guest_cannot_register_a_local_account(world, base_url, robot):
    guest = world["agents"]["guest"]
    name = "test-selfregistered"
    guest.session.post(f"{base_url}/bin/register/XWiki/XWikiRegister",
                       data={"xwikiname": name, "register_password": "Xx-123456789",
                             "register2_password": "Xx-123456789", "register_first_name": "Self",
                             "register_email": "self@example.org", "template": "XWiki.XWikiUserTemplate"},
                       headers={"Accept": "text/html"})
    assert not robot.page_exists(PageRef(("XWiki",), name))


def test_ae8_non_admin_page_code_does_not_run(world):
    a = world["agents"]["test-agent-a"]
    page = PageRef(("Bureaux", "A"), "ScriptTest")
    assert a.put(page, "Essai de script", "{{velocity}}RESULTAT-$mathtool.add(40, 2){{/velocity}}").status_code \
        in (200, 201, 202)
    rendered = a.plain(page)
    assert "RESULTAT-42" not in rendered


def test_agents_cannot_join_groups_or_edit_application_code(world, base_url):
    a = world["agents"]["test-agent-a"]
    group = PageRef(("XWiki",), "GroupeSynthese")
    body = {"className": "XWiki.XWikiGroups", "properties": [{"name": "member", "value": "XWiki.test-agent-a"}]}
    r = a.session.post(f"{base_url}/rest/wikis/xwiki{group.path()}/objects", json=body)
    assert r.status_code in DENIED
    assert a.put(PageRef(("Mesures",)), "Fiches mesures", "détourné").status_code in DENIED
    assert a.put(PageRef(("WikiDB", "Code"), "BureauClass"), "x", "x").status_code in DENIED
