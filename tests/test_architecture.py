"""Guard the data path: collector → store (Redis) → web. The web tier must never read simulator objects."""
import pathlib
import re

WEB = pathlib.Path(__file__).resolve().parents[1] / "app" / "web"
FORBIDDEN = [r"get_engine", r"sim\.engine", r"from \.\.\.?readmodel", r"\beng\.", r"collector\.publisher"]


def test_web_tier_reads_only_the_store():
    offenders = []
    for f in WEB.rglob("*.py"):
        text = f.read_text()
        for pat in FORBIDDEN:
            for m in re.finditer(pat, text):
                line = text[:m.start()].count("\n") + 1
                offenders.append(f"{f.relative_to(WEB.parent)}:{line} matches {pat!r}")
    assert not offenders, "web tier bypasses the store:\n" + "\n".join(offenders)


def test_every_page_view_is_published():
    from app.collector.publisher import ENTITIES, FAST_VIEWS, HEAVY_VIEWS
    views = set(FAST_VIEWS) | set(HEAVY_VIEWS)
    used = set()
    for f in (WEB / "routers").glob("*.py"):
        used |= set(re.findall(r'rm\.view\("([a-z_:]+)"\)', f.read_text()))
    used |= {"gpu_nodes", "inventory", "events"}                    # read through rm helpers
    assert used - views == set(), f"routers read views nobody publishes: {used - views}"
    ents = set()
    for f in (WEB / "routers").glob("*.py"):
        ents |= set(re.findall(r'rm\.entity\("([a-z_]+)"', f.read_text()))
    assert ents - set(ENTITIES) == set(), f"routers read entities nobody publishes: {ents - set(ENTITIES)}"
