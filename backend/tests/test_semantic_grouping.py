from bluepulse_backend.models import Material


def test_semantic_group_distinguishes_development_from_same_fact():
    from bluepulse_backend.grouping import CandidateFact, decide

    material = Material(zh_title="警方调度试点", zh_summary="警方调度试点开始",
                        editorial_scope="single", editorial_data={"fact": {"title": "调度试点"}})
    candidates = [
        CandidateFact("fact", "story", "警方调度试点", "警方调度试点开始", 0.55, True, False),
    ]

    def step(kind, *_args):
        if kind == "group":
            return {"decisions": [{"id": "C1", "relation": "SAME_OCCURRENCE", "confidence": .7}],
                    "selection": {"addsValue": True}}, {}
        assert kind == "groupReview"
        return {"relation": "SAME_STORY", "confidence": .92}, {}

    decision = decide(material, candidates, step)
    assert decision.fact_id is None
    assert decision.story_id == "story"
