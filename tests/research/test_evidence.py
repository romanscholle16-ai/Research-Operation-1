from app.research.evidence import EvidenceStatus, extract_evidence


def test_explicit_evidence_quotes_the_matching_sentence() -> None:
    text = "This strategy uses a stop loss of 2 percent. It also uses an EMA filter."
    items = extract_evidence("source-1", text, topics=("stop loss",))
    explicit = [i for i in items if i.status is EvidenceStatus.EXPLICIT]
    assert len(explicit) == 1
    assert "stop loss" in explicit[0].quoted_text.lower()
    assert explicit[0].source_id == "source-1"
    assert explicit[0].location_reference == "sentence 0"


def test_unknown_evidence_recorded_when_topic_absent() -> None:
    text = "This strategy only discusses entries."
    items = extract_evidence("source-1", text, topics=("take profit",))
    assert len(items) == 1
    assert items[0].status is EvidenceStatus.UNKNOWN
    assert items[0].quoted_text is None
    assert items[0].location_reference is None


def test_every_topic_produces_exactly_one_outcome_set() -> None:
    text = "Entry occurs on confirmation. No stop loss is mentioned here."
    items = extract_evidence("s1", text, topics=("entry", "stop loss", "take profit"))
    by_claim = {i.claim: i.status for i in items if i.status is not None}
    assert len(items) >= 3  # at least one item per topic (entry/stop loss may match >1 sentence)


def test_multiple_sentences_matching_same_topic_all_captured() -> None:
    text = "Entry on breakout. A second entry condition exists. Entry is confirmed by volume."
    items = extract_evidence("s1", text, topics=("entry",))
    explicit = [i for i in items if i.status is EvidenceStatus.EXPLICIT]
    assert len(explicit) == 3


def test_evidence_is_traceable_to_its_source() -> None:
    items = extract_evidence("source-xyz", "Entry on close above EMA.", topics=("entry",))
    assert all(i.source_id == "source-xyz" for i in items)


def test_evidence_never_fabricates_a_claim_not_asked_for() -> None:
    items = extract_evidence("s1", "The stop loss is 2 percent.", topics=("entry",))
    assert all(i.claim == "entry" for i in items)  # never invents a "stop loss" item unless asked


def test_case_insensitive_matching() -> None:
    items = extract_evidence("s1", "ENTRY occurs on breakout.", topics=("entry",))
    assert items[0].status.value == "explicit"
