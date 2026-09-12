import pandas as pd

from app.gemini_analysis import StockAnalysis, build_analysis_prompt


def test_structured_output_schema_and_prompt() -> None:
    analysis = StockAnalysis.model_validate({
        "ticker": "TEST.T",
        "company_name": "テスト会社",
        "summary": "変化を追加調査する",
        "why_research_today": "出来高が増えたため",
        "inbound_relevance_score": 4,
        "inbound_relevance_reason": "入力上の関連度が高い",
        "positive_factors": [],
        "negative_factors": [],
        "scenarios": [],
        "counter_arguments": [],
        "additional_data_needed": ["一次情報"],
        "warnings": ["売買推奨ではない"],
        "conclusion": "new_research_candidate",
        "confidence": "low",
    })
    assert analysis.inbound_relevance_score == 4

    row = pd.Series({
        "ticker": "TEST.T", "code": "0000", "name": "テスト会社",
        "category": "ホテル", "as_of_date": "2026-09-01", "signals": ["出来高急増"],
    })
    prompt = build_analysis_prompt(row, {})
    assert "株価予測や売買推奨ではなく" in prompt
    assert '"ticker": "TEST.T"' in prompt

