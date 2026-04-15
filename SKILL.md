---
name: zoom-utage
description: >
  Zoom録画からUTAGE会員サイトのレッスンページを全自動で作成する。
  Zoom APIで直近の録画を取得 → UTAGEに動画アップロード → 新規レッスン作成
  → VTTからGeminiでタイトル・扱った内容・チャプター生成 → HTML保存。
  チャプタークリックで動画が該当位置にジャンプ。
argument-hint: "[--zoom / --vtt path] [URLs]"
---

# zoom-utage スキル（配布版）

Zoom録画 → UTAGE会員サイトのレッスンページを1コマンドで自動作成するスキル。

> ⚠️ これは UTAGE 非公式の自動化ツールです。ブラウザ操作（Playwright）で UTAGE のエディタを叩いています。利用は自己責任でお願いします。

## 何が自動化されるか

```
入力: Zoom APIの直近録画 or ローカルVTTパス
  ↓
[0] Zoom APIからMP4+VTT自動DL（--zoom 時）
[1] VTT解析 → 30秒ごと整形
[2] Gemini: タイトル / 扱った内容 / チャプター生成
[3] 承認プロンプト（--yes でスキップ）
[4] UTAGEに動画アップロード（~数分 / 250MB）
[5] 空レッスン新規作成（type=html, 公開）
[6] リッチ要素を保存:
    1. 今回扱った内容（番号バッジ付きカード）
    2. 動画 + チャプター（クリックで該当位置にジャンプ）
    3. 資料ボタン（--slides-url 指定時）
```

## 初回セットアップ

1. リポジトリを clone する
   ```bash
   git clone https://github.com/coachnaoki/zoom-utage-skill.git
   cd zoom-utage-skill
   ```

2. Claude Code を起動する
   ```bash
   claude
   ```

3. セットアップをお願いする
   > このスキルの初回セットアップをして。`.env` を作って、venv を作って、依存をインストールして、Playwright の Chromium もインストールして。

4. API 認証情報を取得する
   - Zoom API: `docs/01-zoom-api.md`
   - Gemini API: `docs/02-gemini-api.md`
   - UTAGE オペレーター: `docs/03-utage-operator.md`

5. 取得した値を `.env` に書く（ファイルを開いて手で書いてもいいし、Claude Code に貼り付けて書いてもらってもOK）

6. ターゲット層に合わせて色・フォント・Gemini プロンプトを調整する
   > `docs/04-customize-design.md` を読んで、ターゲット像は〇〇（例：50代のテニスプレイヤー）なので、`create_lesson.py` の CUSTOMIZE セクションをそれに合わせて書き換えて。

## 使い方

### A. Zoom APIモード（推奨・全自動）

```bash
.venv/bin/python create_lesson.py --zoom --zoom-days 7 --yes \
  --login-url "https://your-site.com/operator/XXX/login" \
  --course-url "https://your-site.com/site/SITE_ID/course/COURSE_ID" \
  --upload-folder-url "https://your-site.com/media/video/FOLDER_ID"
```

直近7日の Zoom 録画で MP4+VTT が揃った最新のものを取って自動処理。

### B. ローカルVTTモード

Zoom API から取れない・手元に既に VTT がある場合:

```bash
.venv/bin/python create_lesson.py \
  --vtt "/path/to/GMT20260413-110040_Recording.transcript.vtt" \
  --login-url ... --course-url ... --upload-folder-url ... --yes
```

同じディレクトリの `.mp4` を自動検出する。

### オプション

| フラグ | 用途 |
|---|---|
| `--slides-url URL` | 「資料を開く」ボタンを追加（複数回指定可の想定：現状1つだけ） |
| `--dry-run` | Gemini生成のみ。UTAGE には触らない |
| `--yes` | 確認プロンプトをスキップ |
| `--skip-upload --video-url URL` | 動画アップロード済みの時に URL を使い回す |

## 失敗リカバリ

### ケース1: アップロード成功後にレッスン作成で失敗
ログの `video_url: https://utage-system.com/video/XXX` を拾って:

```bash
.venv/bin/python create_lesson.py --zoom \
  --skip-upload --video-url "https://utage-system.com/video/XXX" \
  --login-url ... --course-url ... --upload-folder-url ... --yes
```

### ケース2: Zoom APIから録画が取れない
Zoom の保持期間（通常30日）を過ぎたら手動DLしてBモードへ。

## チャプター精度について（重要）

Gemini が出すチャプターは**時刻ズレが発生しやすい**。`--dry-run` で preview.json を確認してから本番実行を推奨。
よくあるズレ:
- 転換点の数分ズレ（Geminiは概算で出す）
- 話題転換と実際の発言開始時刻のズレ

## カスタマイズ

`create_lesson.py` 上部の `CUSTOMIZE` セクション:

- **デザイントークン**: FONT / INK / BG_SOFT / BORDER / ACCENT 等
- **LESSON_CONTEXT**: Gemini プロンプトで使う文脈（例 `'テニス勉強会'`）

Claude Code に「ターゲットは〇〇。デザインとプロンプトを調整して」と頼めば自動で書き換えてくれる。詳細は `docs/04-customize-design.md`。

## 技術メモ

### UTAGE 保存API

`POST /site/{site}/lesson/html/update` に JSON を POST:

```json
{
  "site_id": "...",
  "course_id": "...",
  "lesson_id": "...",
  "page_id": "",
  "news_id": "",
  "elements": [ /* section > row > col > [...] */ ],
  "lesson": { /* Vue proxy から取得 */ }
}
```

`page_id`, `news_id`, `lesson` の3つを省略すると500。

### element_id マッピング

| type | element_id |
|---|---|
| section | 1 |
| row | 2 |
| col | 3 |
| video | 4 |
| video-chapter | 5 |
| button | 6 |
| text | 7 |
| heading | 8 |
| image | 9 |

### video と video-chapter の紐付け

```json
video:         { "id": N,   "relation_elements": "1", ... }
video-chapter: { "id": N+1, "relation_id": 1, ... }
```

`relation_id` が `relation_elements` の値と一致することで、チャプタークリック時に動画がシークする。
