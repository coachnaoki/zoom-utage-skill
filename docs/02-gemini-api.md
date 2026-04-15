# Gemini API Key 取得手順

`GEMINI_API_KEY` を取ってくる手順。

## 手順

1. [Google AI Studio](https://aistudio.google.com/) にログイン
2. 左メニューの **Get API key** をクリック
3. **Create API key** → プロジェクトを選ぶ（なければ新規作成）
4. 発行された API Key をコピー

## `.env` に書く

```
GEMINI_API_KEY=<コピーした key>
```

## 動作確認

```bash
.venv/bin/python -c "
import os, requests
from dotenv import load_dotenv
load_dotenv()
r = requests.post(
    f'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent?key={os.environ[\"GEMINI_API_KEY\"]}',
    json={'contents':[{'parts':[{'text':'hello'}]}]})
print(r.status_code, r.json().get('candidates', [{}])[0])
"
```

`200` が返ればOK。

## モデルとコスト

このスキルは `gemini-3.1-flash-lite-preview` を使っている。

- 1本のレッスン作成で `gen_title` `gen_contents_list` `gen_chapters` の3回呼び出し
- トークン消費は文字起こし量次第。2時間のセミナー（VTT 50KB 程度）で概ね月額 $0.1 〜 $0.5 程度に収まる規模

無料枠（2025年時点で1日15リクエスト程度）でも十分回る。
