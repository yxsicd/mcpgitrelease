from pathlib import Path

SOURCE = Path("web-components/pptx-presentation/src/index.js").read_text(encoding="utf-8")


def test_multi_instance_keyboard_has_explicit_active_owner():
    assert "let activePresentation=null;" in SOURCE
    assert "get active(){return activePresentation===this}" in SOURCE
    assert "activate(reason='programmatic')" in SOURCE
    assert "deactivate(reason='programmatic')" in SOURCE
    assert "if(!this.active&&document.fullscreenElement!==this)return;" in SOURCE


def test_host_policy_does_not_implicitly_claim_ownership():
    assert "this.activate('pointer')" not in SOURCE
    assert "activate('focus')" not in SOURCE
    assert "_onFocusIn" not in SOURCE


def test_fullscreen_claims_ownership_as_runtime_mechanism():
    assert "this.activate('fullscreen')" in SOURCE
    assert "activechange" in SOURCE
    toggle = SOURCE[SOURCE.index("async toggleFullscreen()"):SOURCE.index("#slideAttr(", SOURCE.index("async toggleFullscreen()"))]
    assert toggle.index("this.activate('fullscreen')") > toggle.index("this.setAttribute('data-css-fullscreen','')")


def test_restore_state_does_not_claim_ownership():
    start = SOURCE.index("async restoreState(")
    end = SOURCE.index("download(filename)", start)
    restore = SOURCE[start:end]
    assert ".activate(" not in restore
