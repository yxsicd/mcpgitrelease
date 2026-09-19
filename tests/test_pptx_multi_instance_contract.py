from pathlib import Path

SOURCE = Path("web-components/pptx-presentation/src/index.js").read_text(encoding="utf-8")


def test_multi_instance_keyboard_has_explicit_active_owner():
    assert "let activePresentation=null;" in SOURCE
    assert "get active(){return activePresentation===this}" in SOURCE
    assert "activate(reason='programmatic')" in SOURCE
    assert "deactivate(reason='programmatic')" in SOURCE
    assert "if(!this.active&&document.fullscreenElement!==this)return;" in SOURCE


def test_interaction_and_fullscreen_claim_ownership():
    assert "this.activate('pointer')" in SOURCE
    assert "this._onFocusIn=()=>this.activate('focus')" in SOURCE
    assert "this.activate('fullscreen')" in SOURCE
    assert "activechange" in SOURCE


def test_restore_state_does_not_claim_ownership():
    start = SOURCE.index("async restoreState(")
    end = SOURCE.index("download(filename)", start)
    restore = SOURCE[start:end]
    assert ".activate(" not in restore
