from saalr_core.rag.qa import RetrievedChunk, build_qa_prompt


def test_build_qa_prompt_grounds_and_includes_chunks():
    chunks = [
        RetrievedChunk("theta-time-decay", "Theta is the daily erosion of value.", 0.1),
        RetrievedChunk("greeks-delta", "Delta measures directional exposure.", 0.3),
    ]
    system, user = build_qa_prompt("What is theta?", chunks)
    assert "ONLY" in system and "OptionsAcademy" in system  # grounding instruction
    assert "What is theta?" in user
    assert "Theta is the daily erosion of value." in user
    assert "Delta measures directional exposure." in user
    assert "theta-time-decay" in user and "greeks-delta" in user


def test_build_qa_prompt_no_chunks():
    system, user = build_qa_prompt("anything", [])
    assert "ONLY" in system  # grounding instruction still present
    assert "Question: anything" in user and "Excerpts:" in user  # well-formed with no excerpts
