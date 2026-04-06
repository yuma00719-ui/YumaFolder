"""
main.py — Morning Briefing System エントリポイント

実行方法:
    python main.py              # 通常実行（ニュース取得 → 分析 → メール送信）
    python main.py --test-email # メール送信テスト（ダミーデータ）
    python main.py --test-news  # ニュース取得テスト（取得結果を表示、メール送信なし）
"""

import argparse
import logging
import os
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml
from dotenv import load_dotenv

# プロジェクトルートを sys.path に追加
sys.path.insert(0, str(Path(__file__).parent))

from modules.news_fetcher import fetch_all_categories, Article
from modules.analyzer import generate_briefing, BriefingSection
from modules.email_sender import send_briefing_email, send_error_notification

JST = timezone(timedelta(hours=9))


def setup_logging(log_dir: str, level_str: str, keep_days: int) -> None:
    """ログ設定（ファイル + コンソール）。"""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    today = datetime.now(JST).strftime("%Y%m%d")
    log_file = log_path / f"briefing_{today}.log"

    level = getattr(logging, level_str.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # 古いログを削除
    try:
        from datetime import timedelta as td
        cutoff = datetime.now(JST).date() - td(days=keep_days)
        for old_log in log_path.glob("briefing_*.log"):
            try:
                date_part = old_log.stem.replace("briefing_", "")
                file_date = datetime.strptime(date_part, "%Y%m%d").date()
                if file_date < cutoff:
                    old_log.unlink()
            except (ValueError, OSError):
                pass
    except Exception:
        pass


def load_config() -> dict:
    """config.yaml を読み込む。"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_env() -> dict:
    """.env を読み込み、必要な環境変数を返す。"""
    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)

    required = {
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        "GMAIL_ADDRESS": os.getenv("GMAIL_ADDRESS"),
        "GMAIL_APP_PASSWORD": os.getenv("GMAIL_APP_PASSWORD"),
        "TO_EMAIL": os.getenv("TO_EMAIL"),
    }

    missing = [k for k, v in required.items() if not v]
    if missing:
        raise EnvironmentError(
            f"以下の環境変数が設定されていません: {', '.join(missing)}\n"
            ".env ファイルを確認してください（.env.example を参照）"
        )

    return required


def run_test_email(config: dict, env: dict) -> None:
    """ダミーデータでメール送信テストを行う。"""
    logger = logging.getLogger(__name__)
    logger.info("=== テストメール送信モード ===")

    dummy_article = Article(
        title="テスト: 日本銀行が政策金利を0.5%に引き上げ",
        url="https://www.nhk.or.jp/news/test",
        summary="日本銀行は本日の金融政策決定会合で、政策金利を0.25%から0.5%に引き上げることを決定しました。",
        published=datetime.now(JST),
        source="NHKニュース（テスト）",
        category="経済",
    )

    dummy_section = BriefingSection(
        category_name="経済",
        article=dummy_article,
        selection_reason="テスト用ダミー記事",
        html_analysis="""<div class="article-analysis">
<h3>【要約】</h3>
<p>これはテスト送信です。実際の実行時はここに Claude API による詳細分析が入ります。</p>
<h3>【構造分析】</h3>
<ul><li>テスト項目 A</li><li>テスト項目 B</li></ul>
<h3>【ビジネスパーソンへの学び】</h3>
<p>テスト送信が正常に届いていれば、システムは正常動作しています。</p>
<h3>【模擬ディスカッション】</h3>
<p><strong>論点:</strong> このシステムはあなたの朝の情報収集を効率化できるか？</p>
</div>""",
    )

    send_briefing_email(
        gmail_address=env["GMAIL_ADDRESS"],
        gmail_app_password=env["GMAIL_APP_PASSWORD"],
        to_email=env["TO_EMAIL"],
        sections=[dummy_section],
        integrated_insight="テスト送信が成功しました。明日からの朝7時の自動配信をお楽しみに。",
        generated_at=datetime.now(JST),
        smtp_host=config["email"]["smtp_host"],
        smtp_port=config["email"]["smtp_port"],
    )
    logger.info("テストメール送信完了")


def run_test_news(config: dict, env: dict) -> None:
    """ニュース取得テストを行い、結果をコンソールに表示する（メール送信なし）。"""
    logger = logging.getLogger(__name__)
    logger.info("=== ニュース取得テストモード ===")

    retry = config.get("retry", {})
    articles_by_category = fetch_all_categories(
        news_sources_config=config["news_sources"],
        retry_max=retry.get("max_attempts", 3),
        retry_wait=retry.get("wait_seconds", 5),
    )

    for cat_key, articles in articles_by_category.items():
        print(f"\n{'='*60}")
        print(f"カテゴリ: {cat_key} — {len(articles)} 件")
        print("=" * 60)
        for i, a in enumerate(articles, 1):
            print(f"  [{i}] {a.title}")
            print(f"      {a.url}")
            if a.published:
                print(f"      {a.published.strftime('%Y/%m/%d %H:%M')}")
            print()


def run_main(config: dict, env: dict) -> None:
    """通常の実行フロー。"""
    logger = logging.getLogger(__name__)
    logger.info("=== Morning Briefing 開始 ===")

    retry = config.get("retry", {})
    retry_max = retry.get("max_attempts", 3)
    retry_wait = retry.get("wait_seconds", 5)

    # ── Step 1: ニュース取得
    logger.info("Step 1: ニュース取得中...")
    articles_by_category = fetch_all_categories(
        news_sources_config=config["news_sources"],
        retry_max=retry_max,
        retry_wait=retry_wait,
    )

    total = sum(len(v) for v in articles_by_category.values())
    logger.info("取得完了: 合計 %d 件", total)

    if total == 0:
        raise RuntimeError("全カテゴリでニュースを取得できませんでした")

    # ── Step 2: Claude API による分析
    logger.info("Step 2: Claude API 分析中...")
    briefing = generate_briefing(
        articles_by_category=articles_by_category,
        claude_config=config["claude"],
    )

    sections: list[BriefingSection] = briefing["sections"]
    integrated_insight: str = briefing["integrated_insight"]
    generated_at: datetime = briefing["generated_at"]

    logger.info("分析完了: %d セクション生成", len(sections))

    if not sections:
        raise RuntimeError("分析結果が空でした（全セクションでエラー）")

    # ── Step 3: メール送信
    logger.info("Step 3: メール送信中...")
    send_briefing_email(
        gmail_address=env["GMAIL_ADDRESS"],
        gmail_app_password=env["GMAIL_APP_PASSWORD"],
        to_email=env["TO_EMAIL"],
        sections=sections,
        integrated_insight=integrated_insight,
        generated_at=generated_at,
        smtp_host=config["email"]["smtp_host"],
        smtp_port=config["email"]["smtp_port"],
        retry_max=retry_max,
        retry_wait=retry_wait,
    )

    logger.info("=== Morning Briefing 完了 ===")


def main() -> int:
    parser = argparse.ArgumentParser(description="Morning Briefing System")
    parser.add_argument("--test-email", action="store_true", help="テストメールを送信")
    parser.add_argument("--test-news", action="store_true", help="ニュース取得テスト（メールなし）")
    args = parser.parse_args()

    # 設定読み込み
    config = load_config()
    log_cfg = config.get("logging", {})
    setup_logging(
        log_dir=log_cfg.get("log_dir", "logs"),
        level_str=log_cfg.get("level", "INFO"),
        keep_days=log_cfg.get("keep_days", 30),
    )

    logger = logging.getLogger(__name__)

    try:
        env = load_env()
    except EnvironmentError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    try:
        if args.test_email:
            run_test_email(config, env)
        elif args.test_news:
            run_test_news(config, env)
        else:
            run_main(config, env)
        return 0

    except Exception as e:
        tb = traceback.format_exc()
        logger.error("致命的なエラーが発生しました:\n%s", tb)

        # エラー通知メールを送信
        try:
            send_error_notification(
                gmail_address=env["GMAIL_ADDRESS"],
                gmail_app_password=env["GMAIL_APP_PASSWORD"],
                to_email=env["TO_EMAIL"],
                error_message=f"{e}\n\n{tb}",
                smtp_host=config["email"]["smtp_host"],
                smtp_port=config["email"]["smtp_port"],
            )
        except Exception as mail_err:
            logger.error("エラー通知メールも失敗: %s", mail_err)

        return 1


if __name__ == "__main__":
    sys.exit(main())
