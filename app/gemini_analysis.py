from __future__ import annotations

import json
import logging
import time
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from app.market_data import driver_subset_for_category
from app.storage import to_jsonable


logger = logging.getLogger(__name__)


class AnalysisFactor(BaseModel):
    title: str = Field(description="短い見出し")
    description: str = Field(description="入力データに基づく簡潔な説明")
    factor_type: Literal["fact", "interpretation", "general_risk"]
    impact: Literal["positive", "negative", "neutral"]
    evidence_fields: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    name: Literal["bull", "base", "bear"]
    description: str
    conditions: list[str] = Field(default_factory=list)


class StockAnalysis(BaseModel):
    ticker: str
    company_name: str
    summary: str = Field(description="トップ画面用の120文字以内の要約")
    why_research_today: str
    inbound_relevance_score: int = Field(ge=1, le=5)
    inbound_relevance_reason: str
    positive_factors: list[AnalysisFactor]
    negative_factors: list[AnalysisFactor]
    scenarios: list[Scenario]
    counter_arguments: list[str] = Field(default_factory=list)
    additional_data_needed: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    conclusion: Literal[
        "new_research_candidate",
        "continue_monitoring",
        "caution",
        "insufficient_information",
    ]
    confidence: Literal["high", "medium", "low"]


def create_client(api_key: str | None) -> Any | None:
    if not api_key:
        logger.info("GEMINI_API_KEY 未設定のためAI分析を省略します")
        return None
    from google import genai

    return genai.Client(api_key=api_key)


def build_analysis_prompt(row: pd.Series, drivers: dict[str, dict]) -> str:
    fields = [
        "ticker",
        "code",
        "name",
        "category",
        "as_of_date",
        "close",
        "return_1d_pct",
        "return_5d_pct",
        "return_20d_pct",
        "return_60d_pct",
        "distance_ma20_pct",
        "distance_ma60_pct",
        "rsi14",
        "rsi_state",
        "volatility20_pct",
        "volume_ratio",
        "inbound_weight",
        "attention_score",
        "change_score",
        "rank",
        "previous_rank",
        "rank_change",
        "signals",
    ]
    stock_data = {field: row.get(field) for field in fields}
    input_data = to_jsonable({"stock": stock_data, "external_drivers": drivers})
    return f"""
あなたは日本の観光・インバウンド関連株を扱う調査支援アナリストです。
目的は株価予測や売買推奨ではなく、「なぜ今日この銘柄を追加調査すべきか」を説明することです。

厳守事項:
- 下記JSONにない企業固有の事実やニュースを作らない。
- 数値を変更・再計算しない。
- fact（入力上の事実）、interpretation（解釈）、general_risk（一般論）を区別する。
- 強気・弱気材料を両方示し、定量順位への反対材料も挙げる。
- RSIが70超なら短期過熱、30未満なら売られ過ぎという状態を明示する。
- 円安は訪日需要にプラスとなり得る一方、輸入・燃料コストにはマイナスとなり得る。
- 結論は調査優先度であり、利益や値動きを保証しない。
- 情報不足は additional_data_needed に明示する。

入力JSON:
{json.dumps(input_data, ensure_ascii=False, indent=2)}
""".strip()


def analyze_stock(
    client: Any,
    row: pd.Series,
    drivers: dict[str, dict],
    *,
    model: str,
    retry_count: int = 3,
) -> StockAnalysis | None:
    from google.genai import types

    prompt = build_analysis_prompt(row, drivers)
    for attempt in range(1, retry_count + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                    response_schema=StockAnalysis,
                ),
            )
            parsed = getattr(response, "parsed", None)
            if isinstance(parsed, StockAnalysis):
                analysis = parsed
            elif parsed is not None:
                analysis = StockAnalysis.model_validate(parsed)
            else:
                analysis = StockAnalysis.model_validate_json(response.text)
            if analysis.ticker != row["ticker"] or analysis.company_name != row["name"]:
                raise ValueError("Geminiの銘柄識別子が入力と一致しません")
            return analysis
        except Exception as exc:  # API errors are intentionally isolated per stock
            logger.warning(
                "Gemini分析失敗: %s（%s/%s）%s",
                row["ticker"],
                attempt,
                retry_count,
                exc,
            )
            if attempt < retry_count:
                time.sleep(attempt * 3)
    return None


def analyze_targets(
    client: Any | None,
    targets: pd.DataFrame,
    driver_summary: dict[str, dict],
    *,
    model: str,
    retry_count: int,
) -> dict[str, StockAnalysis]:
    if client is None:
        return {}
    results: dict[str, StockAnalysis] = {}
    for _, row in targets.iterrows():
        relevant_drivers = driver_subset_for_category(row["category"], driver_summary)
        analysis = analyze_stock(
            client,
            row,
            relevant_drivers,
            model=model,
            retry_count=retry_count,
        )
        if analysis is not None:
            results[row["ticker"]] = analysis
    return results

