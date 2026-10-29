from nova_api.evaluation.runner import load_dataset, run_rag, run_tools


def test_datasets_are_versioned_and_nonempty():
    assert len(load_dataset("rag")) >= 10 and len(load_dataset("tools")) >= 10


def test_rag_meets_recall_gate():
    m = run_rag()
    assert m["recall_at_5"] >= 0.90  # PRD gate


def test_tool_selection_meets_gate():
    m = run_tools()
    assert m["tool_selection_accuracy"] >= 0.95 and m["argument_accuracy"] >= 0.95  # PRD gate


def test_rag_eval_is_reproducible():
    assert run_rag() == run_rag()
