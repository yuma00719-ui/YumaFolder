# 📰 Morning Briefing System

毎朝7時に日本語ニュース（政治・経済・ビジネス）を自動取得・分析し、  
詳細なブリーフィングメールを自分宛に配信するシステムです。

## 機能

- **NHK / Yahoo!ニュース** から RSS で最新記事を自動取得
- **Claude Opus 4.6 (Adaptive Thinking)** による深い分析
  - 5〜8行の要約 + 時系列の文脈
  - 構造分析（なぜ今？誰が得する？シナリオ分岐）
  - ビジネスパーソンへの学び（戦略示唆・思考フレームワーク）
  - 模擬ディスカッション（賛否両論 + 第三の視点）
- **HTML メール** で美しいフォーマットで配信
- **Windows タスクスケジューラ** で毎朝7時に自動実行

---

## セットアップ

### 1. Python パッケージのインストール

```bash
cd morning_briefing
pip install -r requirements.txt
```

### 2. 環境変数の設定

```bash
cp .env.example .env
# .env をテキストエディタで開き、各値を入力
```

`.env` に設定する値:

| 変数名 | 説明 |
|--------|------|
| `ANTHROPIC_API_KEY` | [Anthropic Console](https://console.anthropic.com/) で取得 |
| `GMAIL_ADDRESS` | 送信元の Gmail アドレス |
| `GMAIL_APP_PASSWORD` | Gmail の [アプリパスワード](https://myaccount.google.com/apppasswords)（2段階認証必須） |
| `TO_EMAIL` | 配信先メールアドレス（自分のアドレス） |

> **Gmail App Password の取得方法**: Google アカウント → セキュリティ → 2段階認証を有効化 → アプリパスワード → 「その他」で名前を付けて生成

### 3. 動作確認

```bash
# ニュース取得テスト（メール送信なし）
python main.py --test-news

# テストメール送信（ダミーデータ）
python main.py --test-email

# 本番実行
python main.py
```

### 4. Windows タスクスケジューラへの登録

`setup_task_scheduler.bat` を **右クリック → 管理者として実行**

毎朝 07:00 に自動実行されます。

---

## ファイル構成

```
morning_briefing/
├── main.py                      # エントリポイント
├── config.yaml                  # 設定（ニュースソース・Claude設定など）
├── .env.example                 # 環境変数テンプレート（.env にコピーして使用）
├── requirements.txt             # Python 依存パッケージ
├── run_briefing.bat             # Windows タスクスケジューラ用実行バッチ
├── setup_task_scheduler.bat     # タスクスケジューラ登録スクリプト
├── modules/
│   ├── news_fetcher.py          # RSS ニュース取得モジュール
│   ├── analyzer.py              # Claude API 分析モジュール
│   └── email_sender.py          # Gmail SMTP 送信モジュール
└── logs/
    ├── briefing_YYYYMMDD.log    # 日次実行ログ（自動生成）
    └── bat_runner.log           # バッチ実行ログ（自動生成）
```

---

## カスタマイズ

### ニュースソースの変更

`config.yaml` の `news_sources` セクションを編集します。  
RSS フィードの URL を追加・変更できます。

### 配信時刻の変更

`setup_task_scheduler.bat` の `/ST 07:00` を任意の時刻に変更してから再実行してください。

### Claude モデルの変更

`config.yaml` の `claude.model` を変更します（例: `claude-sonnet-4-6`）。

---

## トラブルシューティング

| 症状 | 確認事項 |
|------|----------|
| メールが届かない | Gmail の送信制限・迷惑メールフォルダ・App Password の有効性を確認 |
| ニュースが取得できない | ネットワーク接続・RSS URL の有効性を `--test-news` で確認 |
| API エラー | `ANTHROPIC_API_KEY` の有効性・残高を確認 |
| タスクが実行されない | タスクスケジューラで「最終実行結果」を確認、ログファイルを参照 |

エラー発生時は **エラー通知メール** が自動送信されます。  
詳細は `logs/briefing_YYYYMMDD.log` を参照してください。
