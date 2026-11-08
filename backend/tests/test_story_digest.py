from datetime import UTC, datetime

from sqlalchemy.orm import Session

from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.editorial_models import Story
from bluepulse_backend.models import FactGroup, FactReport, Material, Source


def test_digest_is_hidden_when_input_evidence_changes(tmp_path):
    from bluepulse_backend.story_digest import digest_context, load_digest, save_digest

    now = datetime.now(UTC)
    engine = make_engine(f"sqlite:///{tmp_path / 'digest.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = Source(slug="fixture", name="Source", excerpt_allowed=True, allowed_hosts=["example.test"])
        story = Story(title="警务通信")
        session.add_all([source, story])
        session.flush()
        fact = FactGroup(story_id=story.id, title=story.title, anchor_at=now, identity_key="fixture")
        session.add(fact)
        session.flush()
        for index in (1, 2):
            article = Material(source_id=source.id, canonical_url=f"https://example.test/{index}",
                               source_url=f"https://example.test/{index}", source_title=f"Evidence {index}",
                               source_body="Evidence. " * 50, zh_summary=f"新进展 {index}", content_hash=str(index),
                               language="en", body_status="full_text", relevant=True, public=True,
                               grouping_status="complete", published_at=now)
            session.add(article)
            session.flush()
            session.add(FactReport(material_id=article.id, fact_id=fact.id, revision=1))
        session.flush()
        key, reports = digest_context(session, story.id, now)
        assert len(reports) == 2
        assert save_digest(session, story.id, key, "当前两条公开报道记录了警务通信进展。", now)
        assert load_digest(session, story.id, now).digest.startswith("当前")
        article.withdrawn = True
        session.flush()
        assert load_digest(session, story.id, now) is None
