# zoom-utage-skill

Zoom録画 → UTAGE会員サイトのレッスンページを1コマンドで自動作成するスキル。

- Zoom API で直近の録画を取得（MP4+VTT）
- UTAGE に動画アップロード
- 空レッスンを新規作成
- Gemini がタイトル・扱った内容・チャプターを生成
- チャプタークリックで動画が該当位置にジャンプするレッスンページを自動構築

> ⚠️ UTAGE 非公式の自動化ツールです。Playwright で UTAGE エディタをブラウザ操作しています。利用は自己責任でお願いします。

## 3ステップセットアップ

### 1. clone

```bash
git clone https://github.com/coachnaoki/zoom-utage-skill.git
cd zoom-utage-skill
```

### 2. Claude Code にセットアップを頼む

```bash
claude
```

Claude Code に次のように話しかける:

> このスキルの初回セットアップをして。`.env` を `.env.example` からコピーして、venv を作って依存をインストールして、Playwright の Chromium もインストールして。

これで `.venv/` と `.env` が作られ、依存が揃う。

### 3. API 認証情報を `.env` に書く

以下3つの API 認証を取って `.env` に書き込む。詳細手順は `docs/` の各ファイルを参照:

- **Zoom API**（Server-to-Server OAuth）: `docs/01-zoom-api.md`
- **Gemini API**（Google AI Studio）: `docs/02-gemini-api.md`
- **UTAGE オペレーターアカウント**（サブ運営用）: `docs/03-utage-operator.md`

### 4. ターゲット層に合わせて色・文体を調整（任意）

Claude Code に話しかける:

> `docs/04-customize-design.md` を読んで、このスキルのターゲット像は〇〇（例：50代のテニスプレイヤー）なので、`create_lesson.py` の CUSTOMIZE セクションをそれに合わせて書き換えて。

## 使う

Zoom API モード（直近の録画を自動取得）:

```bash
.venv/bin/python create_lesson.py --zoom --yes \
  --login-url "https://your-site.com/operator/XXX/login" \
  --course-url "https://your-site.com/site/SITE_ID/course/COURSE_ID" \
  --upload-folder-url "https://your-site.com/media/video/FOLDER_ID"
```

ローカル VTT モード（Zoom API を使わない）:

```bash
.venv/bin/python create_lesson.py \
  --vtt "/path/to/Recording.transcript.vtt" --yes \
  --login-url "..." --course-url "..." --upload-folder-url "..."
```

詳細は `SKILL.md` を参照。

## リポジトリ構成

```
.
├── README.md              # これ
├── SKILL.md               # Claude Code 用スキル定義（詳細な使い方）
├── create_lesson.py       # メインスクリプト
├── .env.example           # API 認証情報テンプレート
├── requirements.txt
└── docs/
    ├── 01-zoom-api.md          # Zoom Server-to-Server OAuth 取得手順
    ├── 02-gemini-api.md        # Gemini API Key 取得手順
    ├── 03-utage-operator.md    # UTAGE オペレーター設定手順
    └── 04-customize-design.md  # デザイン/文体のカスタマイズ方法
```

## ライセンス

Copyright © 2026 Naoki Kobayashi. All rights reserved.

本スキルの著作権は Naoki に帰属します。個人利用は自由ですが、再配布・販売・二次配布用パブリックリポジトリへのアップロードは禁じます。詳細は `LICENSE` を参照してください。
