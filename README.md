# zoom-utage-skill

Zoom録画 → UTAGE会員サイトのレッスンページを1コマンドで自動作成するスキル。

- Zoom API で直近1週間の録画から選択（MP4+VTT）
- UTAGE に動画アップロード
- 空レッスンを新規作成
- Gemini がタイトル・扱った内容・チャプターを生成
- チャプタークリックで動画が該当位置にジャンプするレッスンページを自動構築

> ⚠️ UTAGE 非公式の自動化ツールです。Playwright で UTAGE エディタをブラウザ操作しています。利用は自己責任でお願いします。

## セットアップ（3ステップ）

### 1. clone

```bash
git clone https://github.com/coachnaoki/zoom-utage-skill.git
cd zoom-utage-skill
```

### 2. Claude Code に初回セットアップを依頼

`claude` コマンドで Claude Code を起動し、**以下の文章をそのまま貼り付けて送信**してください:

```
このスキルの初回セットアップをして。`.env.example` から `.env` をコピーして、
venv を作って requirements.txt の依存をインストールして、Playwright の Chromium
もインストールして。
```

これで `.venv/` と `.env` が作られ、依存が揃います。

### 3. 必要な API キー・URL を準備

スクリプト実行時に **対話形式で聞かれ、自動で `.env` に保存**されます。DIYで `.env` を編集する必要はありません。

準備するのは以下3つ。取得手順は**X記事（配布元）**を参照してください:

- **Zoom API**（Server-to-Server OAuth）: Account ID / Client ID / Client Secret → X記事 STEP1
- **Gemini API キー**（Google AI Studio）: → X記事 STEP2
- **UTAGE オペレーターアカウント**（メール/パスワード）と3つのURL → X記事 STEP3
  - `UTAGE_LOGIN_URL`（オペレーター画面のログインURL）
  - `UTAGE_COURSE_URL`（レッスンを追加する対象コースのURL）
  - `UTAGE_UPLOAD_FOLDER_URL`（動画アップロード先のメディアフォルダURL）

## 使う

初回実行時、APIキー・UTAGEのログイン情報・3つのURLは対話入力され、自動的に `.env` に保存されます。2回目以降は引数なしでOK。

**Zoom API モード**（直近1週間の録画一覧から選択してアップロード）:

```bash
.venv/bin/python create_lesson.py --zoom
```

**ローカル VTT モード**（Zoom API を使わない）:

```bash
.venv/bin/python create_lesson.py --vtt "/path/to/Recording.transcript.vtt"
```

Claude Code から使う場合は、以下の文章をそのまま貼り付け:

```
zoom-utage-skill で最新のZoom録画をUTAGEレッスンにしてください。
`.venv/bin/python create_lesson.py --zoom` を実行して、
プロンプトが出たら私の代わりに入力してください（私が止めないかぎり続行）。
```

## カスタマイズ（任意）

ターゲット層に合わせて色・文体を調整したい場合、Claude Code に以下のように依頼:

```
このスキルのターゲットは〇〇（例：50代のテニスプレイヤー）です。
docs/04-customize-design.md を読んで、create_lesson.py の
CUSTOMIZE セクション（デザイントークンと LESSON_CONTEXT）を
それに合わせて書き換えてください。
```

## リポジトリ構成

```
.
├── README.md              # これ
├── SKILL.md               # Claude Code 用スキル定義（詳細な使い方）
├── create_lesson.py       # メインスクリプト
├── .env.example           # API 認証情報テンプレート
├── requirements.txt
└── docs/
    └── 04-customize-design.md  # デザイン/文体のカスタマイズ方法
```

## ライセンス

Copyright © 2026 Naoki Kobayashi. All rights reserved.

本スキルの著作権は Naoki に帰属します。個人利用は自由ですが、再配布・販売・二次配布用パブリックリポジトリへのアップロードは禁じます。詳細は `LICENSE` を参照してください。
