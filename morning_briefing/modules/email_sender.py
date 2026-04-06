"""
email_sender.py — Gmail SMTP を使ってブリーフィングメールを送信するモジュール

送信フロー:
  1. ブリーフィングデータから HTML メール本文を組み立てる
  2. Gmail SMTP (TLS/STARTTLS) で送信
  3. 失敗時はエラー通知メールを送信
"""

import logging
import smtplib
import time
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from .analyzer import BriefingSection

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]

# ──────────────────────────────────────────────
# HTML テンプレート
# ──────────────────────────────────────────────
HTML_HEADER = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{
    font-family: 'Helvetica Neue', Arial, 'Hiragino Kaku Gothic ProN', 'Hiragino Sans',
                 Meiryo, sans-serif;
    font-size: 15px;
    line-height: 1.7;
    color: #222;
    background: #f7f7f7;
    margin: 0;
    padding: 0;
  }}
  .container {{
    max-width: 720px;
    margin: 20px auto;
    background: #fff;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 2px 12px rgba(0,0,0,0.1);
  }}
  .header {{
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    color: #fff;
    padding: 28px 32px;
  }}
  .header h1 {{
    margin: 0 0 6px 0;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 0.05em;
  }}
  .header .date {{
    font-size: 14px;
    color: #a0aec0;
  }}
  .body {{
    padding: 24px 32px;
  }}
  .category-section {{
    margin-bottom: 40px;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    overflow: hidden;
  }}
  .category-header {{
    padding: 14px 20px;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.05em;
  }}
  .cat-politics   {{ background: #ebf8ff; border-left: 5px solid #3182ce; color: #2b6cb0; }}
  .cat-economy    {{ background: #f0fff4; border-left: 5px solid #38a169; color: #276749; }}
  .cat-business   {{ background: #fffff0; border-left: 5px solid #d69e2e; color: #744210; }}
  .article-header {{
    padding: 16px 20px 8px;
    border-bottom: 1px solid #e2e8f0;
  }}
  .article-header h2 {{
    margin: 0 0 6px 0;
    font-size: 18px;
    font-weight: 700;
    line-height: 1.4;
  }}
  .article-header a {{
    color: #2b6cb0;
    text-decoration: none;
  }}
  .article-header a:hover {{ text-decoration: underline; }}
  .article-meta {{
    font-size: 12px;
    color: #718096;
  }}
  .article-analysis {{
    padding: 16px 20px;
  }}
  .article-analysis h3 {{
    font-size: 14px;
    font-weight: 700;
    color: #4a5568;
    margin: 20px 0 8px;
    padding: 4px 10px;
    background: #f7fafc;
    border-left: 3px solid #a0aec0;
    border-radius: 0 4px 4px 0;
  }}
  .article-analysis p {{
    margin: 8px 0;
    color: #444;
  }}
  .article-analysis ul {{
    margin: 8px 0;
    padding-left: 22px;
    color: #444;
  }}
  .article-analysis li {{
    margin-bottom: 6px;
  }}
  .article-analysis strong {{
    color: #2d3748;
    font-weight: 700;
  }}
  .insight-box {{
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: #fff;
    padding: 20px 24px;
    border-radius: 8px;
    margin-top: 8px;
  }}
  .insight-box h2 {{
    font-size: 15px;
    margin: 0 0 10px;
    opacity: 0.85;
  }}
  .insight-box p {{
    font-size: 16px;
    font-weight: 600;
    margin: 0;
    line-height: 1.6;
  }}
  .footer {{
    text-align: center;
    font-size: 12px;
    color: #a0aec0;
    padding: 16px;
    border-top: 1px solid #e2e8f0;
  }}
</style>
</head>
<body>
<div class="container">
"""

HTML_FOOTER = """
  <div class="footer">
    Morning Briefing — 自動生成 by Claude API &amp; Python<br>
    配信停止はスクリプトを停止してください
  </div>
</div>
</body>
</html>"""

CATEGORY_CLASS = {
    "政治": "cat-politics",
    "経済": "cat-economy",
    "ビジネス": "cat-business",
}


def _build_html(
    sections: list[BriefingSection],
    integrated_insight: str,
    generated_at: datetime,
) -> str:
    """ブリーフィングデータから HTML メール本文を組み立てる。"""
    weekday = WEEKDAY_JP[generated_at.weekday()]
    date_str = generated_at.strftime(f"%Y/%m/%d（{weekday}）")

    html = HTML_HEADER.format()

    # ── ヘッダー
    html += f"""
  <div class="header">
    <h1>📰 Morning Brief</h1>
    <div class="date">{date_str} &nbsp;|&nbsp; {len(sections)} カテゴリ &nbsp;|&nbsp; Claude AI 分析</div>
  </div>
  <div class="body">
"""

    # ── 各カテゴリセクション
    for section in sections:
        cat_class = CATEGORY_CLASS.get(section.category_name, "cat-business")
        pub_str = ""
        if section.article.published:
            pub_str = section.article.published.strftime("%H:%M 配信")

        html += f"""
    <div class="category-section">
      <div class="category-header {cat_class}">■ {section.category_name}</div>
      <div class="article-header">
        <h2><a href="{section.article.url}" target="_blank">{section.article.title}</a></h2>
        <div class="article-meta">
          📡 {section.article.source}
          {f"&nbsp;|&nbsp; 🕐 {pub_str}" if pub_str else ""}
          &nbsp;|&nbsp; 選定理由: {section.selection_reason}
        </div>
      </div>
      {section.html_analysis}
    </div>
"""

    # ── 統合的洞察
    html += f"""
    <div class="insight-box">
      <h2>💡 今日の一言 — 3本を横断した統合的な洞察</h2>
      <p>{integrated_insight}</p>
    </div>
"""

    html += "  </div>"  # .body
    html += HTML_FOOTER

    return html


def _build_plain_text(
    sections: list[BriefingSection],
    integrated_insight: str,
    generated_at: datetime,
) -> str:
    """プレーンテキスト版（HTML が表示できないメールクライアント向け）。"""
    import re
    weekday = WEEKDAY_JP[generated_at.weekday()]
    date_str = generated_at.strftime(f"%Y/%m/%d（{weekday}）")

    lines = [
        "━" * 50,
        f"📰 Morning Brief — {date_str}",
        "━" * 50,
        "",
    ]

    for section in sections:
        lines += [
            f"■ {section.category_name}",
            f"  {section.article.title}",
            f"  {section.article.url}",
            "",
        ]

    lines += [
        "━" * 50,
        f"💡 今日の一言: {integrated_insight}",
        "━" * 50,
    ]

    return "\n".join(lines)


def send_briefing_email(
    gmail_address: str,
    gmail_app_password: str,
    to_email: str,
    sections: list[BriefingSection],
    integrated_insight: str,
    generated_at: datetime,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 587,
    retry_max: int = 3,
    retry_wait: int = 5,
) -> None:
    """
    ブリーフィングメールを送信する。

    Raises:
        Exception: リトライ上限後も送信失敗した場合
    """
    weekday = WEEKDAY_JP[generated_at.weekday()]
    date_str = generated_at.strftime(f"%Y/%m/%d（{weekday}）")
    subject = f"📰 Morning Brief ── {date_str}"

    html_body = _build_html(sections, integrated_insight, generated_at)
    text_body = _build_plain_text(sections, integrated_insight, generated_at)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    last_error: Optional[Exception] = None
    for attempt in range(1, retry_max + 1):
        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(gmail_address, gmail_app_password)
                server.sendmail(gmail_address, to_email, msg.as_bytes())
            logger.info("メール送信成功: %s → %s", subject, to_email)
            return
        except Exception as e:
            last_error = e
            logger.warning("メール送信失敗 (試行 %d/%d): %s", attempt, retry_max, e)
            if attempt < retry_max:
                time.sleep(retry_wait)

    raise RuntimeError(f"メール送信が {retry_max} 回失敗しました: {last_error}") from last_error


def send_error_notification(
    gmail_address: str,
    gmail_app_password: str,
    to_email: str,
    error_message: str,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 587,
) -> None:
    """エラー発生時に通知メールを送る（ベストエフォート）。"""
    now = datetime.now(JST)
    subject = f"⚠️ Morning Brief エラー通知 — {now.strftime('%Y/%m/%d %H:%M')}"

    body = f"""Morning Briefing の実行中にエラーが発生しました。

発生日時: {now.strftime('%Y/%m/%d %H:%M:%S')} JST
エラー内容:
{error_message}

ログファイルをご確認ください。
"""

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = to_email

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(gmail_address, gmail_app_password)
            server.sendmail(gmail_address, to_email, msg.as_bytes())
        logger.info("エラー通知メール送信完了")
    except Exception as e:
        logger.error("エラー通知メールの送信にも失敗: %s", e)
