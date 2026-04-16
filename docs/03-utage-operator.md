# UTAGE オペレーターアカウント設定手順

このスキルは UTAGE にブラウザでログインしてエディタを操作する。メインアカウントを使うと、自動化中にメインのブラウザセッションからログアウトされてしまうので、**オペレーター（サブ）アカウント**を作って専用に使うのがおすすめ。

## 前提

- UTAGE の管理アカウントを持っていること
- 自分の UTAGE が独自ドメインか `https://xxx.utage-system.com/` のサブドメインか把握していること

## オペレーターアカウント作成

1. UTAGE 管理画面にログイン
2. サイト設定 → オペレーター管理 → 新規追加
3. メール/パスワードを設定
4. 権限を付与（少なくとも以下が必要）:
   - レッスン編集
   - メディア（動画）管理
   - 対象コースへのアクセス

## ログインURL の控え

オペレーター用のログインURLは以下の形式:

```
https://utage-system.com/operator/<RANDOM_HASH>/login
```

`<RANDOM_HASH>` 部分はサイトごとに固有。管理画面のオペレーター管理で確認できる。独自ドメインを設定している場合は `https://あなたのドメイン/operator/<RANDOM_HASH>/login` になる。

## `.env` に書く

```
UTAGE_EMAIL=<オペレーターのメール>
UTAGE_PASSWORD=<オペレーターのパスワード>
```

## UTAGE の3つのURL

初回実行時に対話入力される。入力すると `.env` に自動保存され、2回目以降は自動的に使われる。事前に `.env` へ書いておいてもOK、CLI 引数で上書きすることも可能。

| .env キー / CLI 引数 | 例 | 取り方 |
|---|---|---|
| `UTAGE_LOGIN_URL` / `--login-url` | `https://utage-system.com/operator/XXX/login` | オペレーター管理画面から |
| `UTAGE_COURSE_URL` / `--course-url` | `https://utage-system.com/site/SITE_ID/course/COURSE_ID` | 対象コースの編集画面 URL から `/lesson` より前の部分 |
| `UTAGE_UPLOAD_FOLDER_URL` / `--upload-folder-url` | `https://utage-system.com/media/video/FOLDER_ID` | メディア管理の動画フォルダを開いた時のURL |

## 動作確認

```bash
.venv/bin/python -c "
from playwright.sync_api import sync_playwright
import os
from dotenv import load_dotenv
load_dotenv()
LOGIN_URL='https://utage-system.com/operator/XXX/login'  # ← 書き換える
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto(LOGIN_URL)
    pg.fill('input[name=email]', os.environ['UTAGE_EMAIL'])
    pg.fill('input[name=password]', os.environ['UTAGE_PASSWORD'])
    pg.click('button[type=submit]')
    pg.wait_for_load_state('networkidle')
    print('login ok?', 'login' not in pg.url)
    b.close()
"
```

`login ok? True` が返ればOK。

## 注意

- メインアカウントでブラウザ利用中に自動化を流すと、UTAGE 側のセッション仕様によってメインがログアウトされるため、必ずオペレーターアカウントを使うこと
- パスワードは強めに設定し、`.env` は絶対に Git にコミットしない（`.gitignore` に入っている）
