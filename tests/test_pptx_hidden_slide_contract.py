from pathlib import Path

SOURCE = Path("web-components/pptx-presentation/src/index.js").read_text(encoding="utf-8")


def test_hidden_slides_are_mapped_out_of_public_navigation():
    assert "this._slideMap=[]" in SOURCE
    assert "this._viewer.presentationData?.slides" in SOURCE
    assert "slide?.hidden?[]:[index]" in SOURCE
    assert "const physical=this._slideMap[n]" in SOURCE
    assert "await this._viewer.renderSlide(physical)" in SOURCE
