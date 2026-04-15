"""
analyzer.py — Claude API を使ってニュースを分析・ブリーフィングを生成するモジュール

処理フロー:
  1. 各カテゴリの記事リストを受け取る
  2. Claude に「最重要記事の選定」を依頼（内部ログ用）
  3. 選定された記事について詳細分析・学び・模擬ディスカッションを生成
  4. HTML メール本文を組み立てて返す
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import anthropic

from .news_fetcher import Article

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

# ──────────────────────────────────────────────
# 記事選定プロンプト
# ──────────────────────────────────────────────
SELECTION_SYSTEM = """あなたは優秀なニュースキュレーターです。
提供された記事リストの中から、今日のビジネスパーソンが最も読むべき記事を1本選定してください。
選定基準：社会的影響度、経済・ビジネスへの関連性、話題性・速報性、情報の具体性。
必ず以下の JSON のみを返してください（他のテキストは不要）:
{"selected_index": 0, "reason": "選定理由（50文字以内）"}"""

# ──────────────────────────────────────────────
# 分析プロンプト
# ──────────────────────────────────────────────
ANALYSIS_SYSTEM = """あなたは日本語ビジネスニュースの専門アナリストです。
与えられた記事について、以下の構成で深い分析を行い、HTMLで出力してください。

出力形式の指示:
- 各セクションの見出しは <h3> タグを使用
- 箇条書きは <ul><li> タグを使用
- 重要な語句は <strong> タグで強調
- 段落は <p> タグで囲む
- 全体を <div class="article-analysis"> で囲む
- 記事の見出しとURLは含めない（呼び出し元で追加します）

出力すべきセクション:
1. 【要約】5〜8行。何が起きたか・背景・関係者・影響範囲を網羅
2. 【時系列の文脈】この出来事に至る経緯を2〜3行で補足
3. 【構造分析】
   - なぜ今このタイミングで起きたのか（トリガーと構造的要因）
   - 誰が得をし、誰が損をするのか（ステークホルダー分析）
   - この動きが加速／反転する条件（シナリオ分岐）
4. 【ビジネスパーソンへの学び】
   - 経営判断・戦略への示唆
   - 自分の仕事・キャリアへの応用（抽象化した原則）
   - 思考フレームワークとの接続（ポーターの5F、OODA、ゲーム理論など、適切なものがあれば）
5. 【模擬ディスカッション】
   - 論点の提示（このニュースから導かれる本質的な問いを1つ）
   - 賛成派の主張（根拠・データ・ロジックを添えて3〜5行）
   - 反対派の主張（同上）
   - 第三の視点（賛否の二項対立を超えた高次の視点）
   - あなたならどう考える？（読者に思考を促すクロージングの問いかけ）"""


@dataclass
class BriefingSection:
    category_name: str
    article: Article
    selection_reason: str
    html_analysis: str


def _select_best_article(
    client: anthropic.Anthropic,
    articles: list[Article],
    model: str,
    category_name: str,
) -> tuple[Article, str]:
    """記事リストから最重要記事を1本選定し、(記事, 選定理由) を返す。"""
    if len(articles) == 1:
        return articles[0], "唯一の取得記事"

    articles_text = "\n".join(
        f"[{i}] {a.title} ({a.source})\n    {a.summary[:200]}"
        for i, a in enumerate(articles)
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=256,
            system=SELECTION_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": f"カテゴリ：{category_name}\n\n記事リスト:\n{articles_text}",
                }
            ],
        )
        raw = response.content[0].text.strip()
        # JSON のみ抽出（前後に余計なテキストがある場合に備える）
        start = raw.find("{")
        end = raw.rfind("}") + 1
        data = json.loads(raw[start:end])
        idx = int(data.get("selected_index", 0))
        reason = data.get("reason", "")
        idx = max(0, min(idx, len(articles) - 1))
        logger.info("カテゴリ「%s」選定: [%d] %s — %s", category_name, idx, articles[idx].title, reason)
        return articles[idx], reason
    except Exception as e:
        logger.warning("記事選定でエラー、先頭記事を使用: %s", e)
        return articles[0], "自動選定（フォールバック）"


def _analyze_article(
    client: anthropic.Anthropic,
    article: Article,
    model: str,
    max_tokens: int,
    thinking_config: Optional[dict],
) -> str:
    """記事を分析し、HTML 文字列を返す。"""
    user_content = (
        f"タイトル: {article.title}\n"
        f"URL: {article.url}\n"
        f"ソース: {article.source}\n"
        f"概要: {article.summary}\n"
        f"カテゴリ: {article.category}"
    )

    create_params: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": ANALYSIS_SYSTEM,
        "messages": [{"role": "user", "content": user_content}],
    }

    if thinking_config:
        create_params["thinking"] = thinking_config

    response = client.messages.create(**create_params)

    # thinking ブロックを除いてテキストブロックだけ結合
    html_parts = [
        block.text
        for block in response.content
        if block.type == "text"
    ]
    return "".join(html_parts)


def _generate_integrated_insight(
    client: anthropic.Anthropic,
    sections: list[BriefingSection],
    model: str,
) -> str:
    """3本の記事を横断した統合的な洞察（今日の一言）を生成する。"""
    summaries = "\n".join(
        f"・{s.category_name}: {s.article.title}"
        for s in sections
    )
    try:
        response = client.messages.create(
            model=model,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "以下の3本のニュースを横断した、今日のビジネスパーソンへの"
                        "統合的な洞察を1〜2文（100文字以内）で述べてください。\n\n"
                        f"{summaries}"
                    ),
                }
            ],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning("統合的洞察の生成に失敗: %s", e)
        return "本日も3つの視点からニュースをお届けしました。それぞれの動きが、どのように連動しているかを意識してみてください。"


def generate_briefing(
    articles_by_category: dict[str, list[Article]],
    claude_config: dict,
) -> dict:
    """
    全カテゴリのニュースを受け取り、ブリーフィングデータを生成して返す。

    Returns:
        {
            "sections": [BriefingSection, ...],
            "integrated_insight": str,
            "generated_at": datetime,
        }
    """
    api_key_env = None  # anthropic.Anthropic() は環境変数 ANTHROPIC_API_KEY を自動参照
    client = anthropic.Anthropic()

    model = claude_config.get("model", "claude-opus-4-6")
    max_tokens = claude_config.get("max_tokens", 8000)
    thinking_config = claude_config.get("thinking", {"type": "adaptive"})

    sections: list[BriefingSection] = []

    category_order = ["politics", "economy", "business"]
    for cat_key in category_order:
        articles = articles_by_category.get(cat_key, [])
        if not articles:
            logger.warning("カテゴリ「%s」: 記事なし、スキップ", cat_key)
            continue

        category_name = articles[0].category  # Article に格納済み

        # Step 1: 最重要記事の選定
        best_article, reason = _select_best_article(
            client=client,
            articles=articles,
            model=model,
            category_name=category_name,
        )

        # Step 2: 深掘り分析
        logger.info("カテゴリ「%s」: 分析開始 — %s", category_name, best_article.title)
        try:
            html_analysis = _analyze_article(
                client=client,
                article=best_article,
                model=model,
                max_tokens=max_tokens,
                thinking_config=thinking_config,
            )
        except Exception as e:
            logger.error("カテゴリ「%s」: 分析失敗 — %s", category_name, e)
            html_analysis = f"<p>分析中にエラーが発生しました: {e}</p>"

        sections.append(BriefingSection(
            category_name=category_name,
            article=best_article,
            selection_reason=reason,
            html_analysis=html_analysis,
        ))

    # Step 3: 統合的洞察
    integrated_insight = ""
    if sections:
        integrated_insight = _generate_integrated_insight(
            client=client,
            sections=sections,
            model=model,
        )

    return {
        "sections": sections,
        "integrated_insight": integrated_insight,
        "generated_at": datetime.now(JST),
    }
