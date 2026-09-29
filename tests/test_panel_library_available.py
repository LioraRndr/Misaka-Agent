"""Whether the panel can run is decided by loading its terminal library, not by finding the file."""
from misaka.ui.panel import ghostty


def test_a_build_this_system_cannot_load_counts_as_unavailable(tmp_path, monkeypatch):
    # A glibc build on a musl system is present and still refuses to load; so does this.
    build = tmp_path / "libghostty-vt.so"
    build.write_bytes(b"not a shared library")
    monkeypatch.setenv("MISAKA_GHOSTTY_VT", str(build))
    monkeypatch.setattr(ghostty, "_LIB", None)
    reason = ghostty.unavailable()
    assert reason and "libghostty-vt is not available" in reason


def test_the_shipped_build_loads_on_this_platform(monkeypatch):
    monkeypatch.delenv("MISAKA_GHOSTTY_VT", raising=False)
    monkeypatch.setattr(ghostty, "_LIB", None)
    assert ghostty.unavailable() is None
