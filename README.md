# zoom-utage-skill

Zoom録画 → UTAGE会員サイトのレッスンページを1コマンドで自動作成するスキル。

- Zoom API で直近の録画から選択（MP4+VTT）
- UTAGE に動画アップロード
- Gemini がタイトル・扱った内容・チャプターを生成
- チャプタークリックで動画が該当位置にジャンプするレッスンページを自動構築

> ⚠️ UTAGE 非公式の自動化ツールです。Playwright で UTAGE エディタをブラウザ操作しています。利用は自己責任でお願いします。

## セットアップ

### 1. ターミナルを開いてダウンロード

Mac: 「ターミナル」アプリを開く（Spotlight で「ターミナル」と検索）
Windows: 「PowerShell」を開く（スタートメニューで検索）

以下を1行ずつ貼り付けて Enter:

```bash
git clone https://github.com/coachnaoki/zoom-utage-skill.git
cd zoom-utage-skill
claude
```

### 2. Claude Code に初回セットアップを依頼

Claude Code が起動したら、以下をそのまま貼り付けて送信:

```
このスキルの初回セットアップをして。`.env.example` から `.env` をコピーして、
venv を作って requirements.txt の依存をインストールして、Playwright の Chromium
もインストールして。
```

### 3. API キー・URL を準備

以下の認証情報を事前に取得してください。取得手順は **X記事（配布元）** を参照:

| 認証情報 | 取得元 | X記事 |
|---|---|---|
| Gemini API キー | [Google AI Studio](https://aistudio.google.com) | STEP1 |
| Zoom Account ID / Client ID / Client Secret | [Zoom Marketplace](https://marketplace.zoom.us) | STEP2 |
| UTAGE オペレーターのメール・パスワード・3つのURL | UTAGE管理画面 | STEP3 |

スクリプト初回実行時に対話形式で聞かれ、自動で `.env` に保存されます。

### 4. レッスンを作成

Claude Code に以下のように話しかけるだけ:

```
Zoom録画をUTAGEのレッスンにして
```

直近7日の録画一覧が表示され、番号で選択 → アップロード → レッスンページ作成まで自動で進みます。

## カスタマイズ

ターゲット層に合わせて色・フォント・Gemini プロンプトを調整できます。Claude Code に以下のように依頼:

```
このスキルのターゲットは〇〇（例：50代のテニスプレイヤー）です。
docs/04-customize-design.md を読んで、create_lesson.py の
CUSTOMIZE セクションをそれに合わせて書き換えてください。
```

## ライセンス

Copyright © 2026 Naoki Kobayashi. All rights reserved.

個人利用は自由ですが、再配布・販売・二次配布用パブリックリポジトリへのアップロードは禁じます。詳細は `LICENSE` を参照してください。
