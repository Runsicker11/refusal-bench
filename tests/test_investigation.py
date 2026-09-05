"""The loop and the warehouse, together.

Still no API key: ScriptedModel supplies the reasoning, run_sql supplies real
answers from real data. This is the first point where the agent's evidence is
something it actually found rather than something a fixture handed it.
"""

from refusal_bench.graph import investigate
from refusal_bench.model import ModelResponse, ScriptedModel, ToolCall
from refusal_bench.tools import make_run_sql


def test_agent_gathers_real_evidence_from_the_warehouse(con):
    model = ScriptedModel([
        ModelResponse(tool_call=ToolCall("run_sql", {
            "query": "select brand, count(*) as n from products group by brand order by brand"
        })),
        ModelResponse(tool_call=ToolCall("run_sql", {
            "query": "select count(*) as n from marketplace_orders"
        })),
        ModelResponse(text="Baseline carries more SKUs than Crosscourt."),
    ])
    out = investigate(model, {"run_sql": make_run_sql(con)}, "why is one brand outselling the other?")

    assert out["stop_reason"] == "concluded"
    assert len(out["evidence"]) == 2
    assert "Baseline" in out["evidence"][0]["result"]
    assert "6000" in out["evidence"][1]["result"]

    # The second prompt must carry the first result, or this is not an
    # investigation -- it is two unrelated queries.
    assert "Baseline" in model.calls[1]


def test_a_rejected_query_does_not_end_the_run(con):
    """The agent should be able to recover from writing bad SQL."""
    model = ScriptedModel([
        ModelResponse(tool_call=ToolCall("run_sql", {"query": "drop table orders"})),
        ModelResponse(tool_call=ToolCall("run_sql", {"query": "select count(*) as n from orders"})),
        ModelResponse(text="6422 orders"),
    ])
    out = investigate(model, {"run_sql": make_run_sql(con)}, "how many orders?")

    assert out["evidence"][0]["result"].startswith("rejected:")
    assert "6422" in out["evidence"][1]["result"]
    assert out["stop_reason"] == "concluded"
    assert con.execute("select count(*) from orders").fetchone()[0] == 6422
