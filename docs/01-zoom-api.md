# Zoom API（Server-to-Server OAuth）取得手順

`.env` に必要な3つの値を取ってくる手順。

## 前提

- Zoom アカウントの管理者権限が必要
- クラウド録画が有効になっていること
- VTT（文字起こし）も自動生成されるよう、録画設定で「音声の自動文字起こし」を ON にしておく

## 手順

1. [Zoom App Marketplace](https://marketplace.zoom.us/) にログイン
2. 右上の **Develop** → **Build App**
3. アプリタイプは **Server-to-Server OAuth** を選択
4. アプリ名を入力（例: `UTage Auto Import`）→ Create
5. 「Information」タブで会社名・アプリ連絡先などを埋める

### Scopes（権限）

「Scopes」タブで以下を追加:

- `cloud_recording:read:list_user_recordings:admin`
- `cloud_recording:read:recording:admin`
- `user:read:user:admin`

### Activation

「Activation」タブで **Activate your app** をクリック。

### 認証情報の控え

「App Credentials」タブから以下を `.env` にコピー:

```
ZOOM_ACCOUNT_ID=<Account ID>
ZOOM_CLIENT_ID=<Client ID>
ZOOM_CLIENT_SECRET=<Client Secret>
```

## 動作確認

```bash
.venv/bin/python -c "
import os, requests
from dotenv import load_dotenv
load_dotenv()
r = requests.post('https://zoom.us/oauth/token',
    data={'grant_type':'account_credentials','account_id':os.environ['ZOOM_ACCOUNT_ID']},
    auth=(os.environ['ZOOM_CLIENT_ID'], os.environ['ZOOM_CLIENT_SECRET']))
print(r.status_code, r.json().get('access_token','')[:20]+'...')
"
```

`200` とトークン頭が表示されればOK。

## よくあるエラー

- `4700 - Invalid access token`: Scopes が足りない。上の3つ全部を追加したか確認
- `300 - App has not been activated`: Activation タブで Activate していない
- 録画が取得できない: 録画の「完了」に時間がかかる。会議終了から30分〜数時間待つ
