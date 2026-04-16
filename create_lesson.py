"""
Zoom録画(VTT+MP4) → UTAGE会員サイトのレッスンページを自動作成。

配布版：回次採番なし、URL類はすべて CLI 引数から渡す。

使い方:
  # .env に API 認証情報をセットしてから
  .venv/bin/python create_lesson.py \\
    --zoom \\
    --login-url "https://utage-system.com/operator/XXX/login" \\
    --course-url "https://utage-system.com/site/SITE_ID/course/COURSE_ID" \\
    --upload-folder-url "https://utage-system.com/media/video/FOLDER_ID" \\
    [--slides-url "..."] [--yes] [--dry-run]

  # Zoom API を使わず手元の VTT で試す場合
  .venv/bin/python create_lesson.py \\
    --vtt "/path/to/Recording.transcript.vtt" \\
    --login-url ... --course-url ... --upload-folder-url ...

カスタマイズ:
  ターゲット層に合わせたデザイン（フォント・色・間隔）は
  下の CUSTOMIZE セクションを編集する（初回実行前に Claude Code に依頼してOK）。
"""
import argparse, json, os, re, tempfile, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

ENV_PATH = Path(__file__).resolve().parent / '.env'
ENV_EXAMPLE = Path(__file__).resolve().parent / '.env.example'

def _load_env():
    if not ENV_PATH.exists() and ENV_EXAMPLE.exists():
        import shutil
        shutil.copy(ENV_EXAMPLE, ENV_PATH)
        print(f'.env.example → .env にコピーしました')
    load_dotenv(ENV_PATH)

def _save_to_env(key, val):
    lines = ENV_PATH.read_text(encoding='utf-8') if ENV_PATH.exists() else ''
    if f'{key}=' in lines:
        lines = re.sub(rf'^{key}=.*$', f'{key}={val}', lines, flags=re.MULTILINE)
    else:
        lines += f'\n{key}={val}\n'
    ENV_PATH.write_text(lines, encoding='utf-8')
    os.environ[key] = val

def _prompt_key(key, what, where_to_get, hidden=True):
    """
    what: 「これは何の値か」を1行で（例: 'Zoom Server-to-Server OAuth の Account ID'）
    where_to_get: どの記事の何ステップで取れるか（例: 'X記事 STEP1'）
    """
    val = os.environ.get(key, '')
    if val:
        return val
    print('')
    print('━' * 60)
    print(f'  📝 {what} を入力してください')
    print(f'     （参照: {where_to_get}）')
    print('━' * 60)
    while True:
        if hidden:
            import getpass
            val = getpass.getpass(f'  {key} = (入力は表示されません): ').strip()
        else:
            val = input(f'  {key} = ').strip()
        if not val:
            print('  ⚠️ 空です。もう一度入力してください。（中止する場合は Ctrl+C）')
            continue
        _save_to_env(key, val)
        print(f'  ✅ {key} を .env に保存しました（次回からは自動で読み込まれます）')
        return val

def _prompt_url(key, what, example, where_to_get, cli_val=None):
    """
    what: 「これは何のURLか」を1行で（例: 'UTAGE オペレーター画面のログインURL'）
    """
    if cli_val:
        _save_to_env(key, cli_val)
        return cli_val
    val = os.environ.get(key, '')
    if val:
        return val
    print('')
    print('━' * 60)
    print(f'  🔗 {what} を入力してください')
    print(f'     例: {example}')
    print(f'     （参照: {where_to_get}）')
    print('━' * 60)
    while True:
        val = input(f'  URL: ').strip()
        if not val:
            print('  ⚠️ 空です。もう一度入力してください。（中止する場合は Ctrl+C）')
            continue
        if not val.startswith('http'):
            print('  ⚠️ URL形式で入力してください（https://... で始まる）')
            continue
        _save_to_env(key, val)
        print(f'  ✅ {key} を .env に保存しました（次回からは自動で読み込まれます）')
        return val

def setup_env(need_zoom=False):
    _load_env()
    global GEMINI_API_KEY, UTAGE_EMAIL, UTAGE_PASSWORD
    global ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET
    GEMINI_API_KEY = _prompt_key('GEMINI_API_KEY', 'Gemini API キー（タイトル・チャプター生成用）', 'X記事 STEP2')
    UTAGE_EMAIL = _prompt_key('UTAGE_EMAIL', 'UTAGE オペレーターアカウントのメールアドレス', 'X記事 STEP3', hidden=False)
    UTAGE_PASSWORD = _prompt_key('UTAGE_PASSWORD', 'UTAGE オペレーターアカウントのパスワード', 'X記事 STEP3')
    if need_zoom:
        ZOOM_ACCOUNT_ID = _prompt_key('ZOOM_ACCOUNT_ID', 'Zoom Server-to-Server OAuth の Account ID', 'X記事 STEP1')
        ZOOM_CLIENT_ID = _prompt_key('ZOOM_CLIENT_ID', 'Zoom Server-to-Server OAuth の Client ID', 'X記事 STEP1')
        ZOOM_CLIENT_SECRET = _prompt_key('ZOOM_CLIENT_SECRET', 'Zoom Server-to-Server OAuth の Client Secret', 'X記事 STEP1')
    else:
        ZOOM_ACCOUNT_ID = os.environ.get('ZOOM_ACCOUNT_ID', '')
        ZOOM_CLIENT_ID = os.environ.get('ZOOM_CLIENT_ID', '')
        ZOOM_CLIENT_SECRET = os.environ.get('ZOOM_CLIENT_SECRET', '')

_load_env()
UTAGE_EMAIL = os.environ.get('UTAGE_EMAIL', '')
UTAGE_PASSWORD = os.environ.get('UTAGE_PASSWORD', '')
ZOOM_ACCOUNT_ID = os.environ.get('ZOOM_ACCOUNT_ID', '')
ZOOM_CLIENT_ID = os.environ.get('ZOOM_CLIENT_ID', '')
ZOOM_CLIENT_SECRET = os.environ.get('ZOOM_CLIENT_SECRET', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = 'gemini-3.1-flash-lite-preview'


# ========================================================================
# CUSTOMIZE: ここから下はあなたのレッスンのターゲット層に合わせて調整する
# Claude Code に「ターゲット像は〇〇です。create_lesson.py のデザインと
# Gemini プロンプトをそれに合わせて書き換えて」と依頼すれば自動で調整される。
# ========================================================================

# --- デザイントークン ---
FONT = '"Hiragino Kaku Gothic ProN", "Noto Sans JP", "Yu Gothic Medium", Meiryo, sans-serif'
INK = '#0a1a2e'              # 見出し・強調テキスト
INK2 = '#3a4a5a'             # 本文
GRAY_TEXT = '#5a656b'        # キャプション・ラベル
BG_SOFT = '#f5f8fa'          # カード背景（薄色）
BG_ACCENT = 'rgba(30, 74, 122, 0.10)'  # アクセント薄色（スライド包囲など）
BORDER = '#d4dde3'           # 枠線
ACCENT = '#1e4a7a'           # ボタン・バッジ・アクセント
ACCENT_DARK = '#0a2947'      # グラデーション起点（深いネイビー）
ACCENT2 = '#2d6ba5'          # 予備（旧バッジ終点）

# --- レッスンの性格（Gemini プロンプトで使う）---
# 例: 'テニス勉強会' / 'マーケティング実践講座' / '英語コーチング' …
LESSON_CONTEXT = 'オンライン勉強会'

# ========================================================================
# 以下はロジック本体。通常は触らなくて良い。
# ========================================================================


# ---------- VTT ----------
def parse_vtt(vtt_path):
    content = Path(vtt_path).read_text(encoding='utf-8')
    pattern = r"(\d{2}:\d{2}:\d{2})\.\d{3}\s+-->\s+(\d{2}:\d{2}:\d{2})\.\d{3}\s*\n(.+?)(?:\n\n|\Z)"
    matches = re.findall(pattern, content, re.DOTALL)
    lines = []
    last_ts_sec = -30
    last_ts_str = '00:00:00'
    buffer = []
    duration_str = '00:00:00'
    for start, end, text in matches:
        duration_str = end
        clean = re.sub(r'<[^>]+>', '', text).strip()
        clean = re.sub(r'^[A-Za-z\s]+:\s*', '', clean)
        clean = re.sub(r'^[^:]+:\s*', '', clean)
        if not clean:
            continue
        h, m, s = start.split(':')
        total = int(h) * 3600 + int(m) * 60 + int(s)
        if total - last_ts_sec >= 30 and buffer:
            lines.append(f'[{last_ts_str}] {"".join(buffer)}')
            buffer = []
        if not buffer:
            last_ts_str = start
            last_ts_sec = total
        buffer.append(clean)
    if buffer:
        lines.append(f'[{last_ts_str}] {"".join(buffer)}')
    return '\n'.join(lines), duration_str


# ---------- Gemini ----------
def gemini_call(prompt, max_tokens=2500, retries=4):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}'
    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.post(url, json={
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {
                    'temperature': 0.3,
                    'maxOutputTokens': max_tokens,
                    'thinkingConfig': {'thinkingBudget': 0},
                }
            }, timeout=90)
            if resp.status_code in (429, 500, 502, 503):
                wait = 5 * (attempt + 1)
                print(f'  Gemini {resp.status_code}, retry {wait}s ({attempt+1}/{retries})')
                time.sleep(wait)
                continue
            if resp.status_code == 400 and 'API_KEY_INVALID' in resp.text:
                raise SystemExit(
                    'Gemini APIキーが無効です。\n'
                    '  → GEMINI_API_KEY を確認してください。\n'
                    '  → 詳細: X記事 STEP2（Gemini API）'
                )
            if resp.status_code == 404:
                raise SystemExit(
                    f'Geminiモデル "{GEMINI_MODEL}" が見つかりません。\n'
                    '  → モデル名が正しいか確認してください。\n'
                    '  → 詳細: X記事 STEP2（Gemini API）'
                )
            resp.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            last_err = e
            print(f'  exception: {e}')
            time.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError(f'Gemini failed: {last_err}')
    text = resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    return re.sub(r'```[a-z]*\n?', '', text).strip()


def gen_title(transcript):
    prompt = f"""以下は{LESSON_CONTEXT}（Zoom）の文字起こしです。
この回のレッスンのタイトルを作ってください。

ルール:
- 「テーマ名／サブ解説」の形式（20〜35文字）
- 内容の核心がわかる具体的なワード
- 事実ベース。煽らない・盛らない・誇張しない
- 感嘆符（！）は使わない
- 禁止表現: 「壁を破る」「壁を乗り越える」「劇的に」「完全攻略」「激変」「最強」「究極」「秘訣」「秘密」のような煽り語彙
- 淡々と内容を指す名詞中心のタイトルが望ましい（例「動画添削で見直すポジショニングと基本動作」）

文字起こし（冒頭1万文字抜粋）:
{transcript[:10000]}

出力はタイトルだけ。説明や前置きは一切不要。"""
    t = gemini_call(prompt, max_tokens=200)
    return t.splitlines()[0].strip(' "「」')


def gen_contents_list(transcript):
    prompt = f"""以下は{LESSON_CONTEXT}（Zoom）の文字起こしです。
「今回扱った内容」として5〜7項目の箇条書きを作ってください。

ルール:
- 各項目: 短いタイトル（10〜20文字）+ 1文の説明（30〜60文字）
- フォーマット: 「タイトル | 説明」を1行ずつ
- 話題を時系列ではなくトピックベースで整理する
- 余計な装飾なし

文字起こし:
{transcript[:15000]}

出力は箇条書きの行だけ。前置き・後書きは不要。"""
    raw = gemini_call(prompt, max_tokens=1200)
    items = []
    for ln in raw.splitlines():
        ln = ln.strip().lstrip('-・*0123456789. ）)')
        if '|' in ln:
            t, d = ln.split('|', 1)
            items.append((t.strip(), d.strip()))
    return items


def gen_chapters(transcript):
    prompt = f"""以下は{LESSON_CONTEXT}（Zoom）の文字起こしです。タイムスタンプ付きです。

大きな話題の転換点だけでチャプターを作ってください。

厳守ルール:
- チャプター総数は**最大12個まで**。動画が長くても12個を超えない
- 小さな話題の変化は無視し、大きなテーマの切り替わりだけ拾う
- タイトルは具体的（15〜30文字）
- フォーマット: 「HH:MM:SS タイトル」を1行ずつ
- 余計な説明・前置きは一切不要。チャプター行だけ出力

文字起こし:
{transcript}"""
    raw = gemini_call(prompt, max_tokens=1500)
    lines = []
    for ln in raw.splitlines():
        s = ln.strip().lstrip('-*・ ').strip()
        # [HH:MM:SS] タイトル / HH:MM:SS タイトル / **HH:MM:SS** タイトル など許容
        m = re.match(r'^[\[\*]*(\d{1,2}:\d{2}(?::\d{2})?)[\]\*]*[\s　:]+(.+)$', s)
        if m:
            ts = m.group(1)
            # MM:SS を HH:MM:SS に正規化
            if ts.count(':') == 1:
                mm, ss = ts.split(':')
                ts = f'00:{int(mm):02d}:{ss}'
            else:
                hh, mm, ss = ts.split(':')
                ts = f'{int(hh):02d}:{int(mm):02d}:{ss}'
            lines.append(f'{ts} {m.group(2).strip()}')
    return '\n'.join(lines[:12])


# ---------- Zoom API ----------
def zoom_token():
    resp = requests.post(
        'https://zoom.us/oauth/token',
        data={'grant_type': 'account_credentials', 'account_id': ZOOM_ACCOUNT_ID},
        auth=(ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET), timeout=10,
    )
    if not resp.ok:
        raise SystemExit(
            f'Zoom認証に失敗しました（{resp.status_code}）。\n'
            '  → ZOOM_ACCOUNT_ID / ZOOM_CLIENT_ID / ZOOM_CLIENT_SECRET を確認してください。\n'
            '  → 詳細: X記事 STEP1（Zoom API）'
        )
    return resp.json()['access_token']


def zoom_list_recordings(token, days=7):
    from_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%d')
    to_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    resp = requests.get(
        'https://api.zoom.us/v2/users/me/recordings',
        headers={'Authorization': f'Bearer {token}'},
        params={'from': from_date, 'to': to_date, 'page_size': 30}, timeout=10,
    )
    if not resp.ok:
        raise SystemExit(
            f'Zoom録画一覧の取得に失敗しました（{resp.status_code}）。\n'
            '  → Scopesに cloud_recording:read:list_user_recordings:admin が追加されているか確認。\n'
            '  → 詳細: X記事 STEP1（Zoom API）'
        )
    return resp.json().get('meetings', [])


def zoom_download(url, token, dest):
    resp = requests.get(url, headers={'Authorization': f'Bearer {token}'}, stream=True, timeout=600)
    resp.raise_for_status()
    with open(dest, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
            f.write(chunk)
    return dest


def zoom_list_candidates(days=7):
    token = zoom_token()
    meetings = zoom_list_recordings(token, days=days)
    if not meetings:
        return token, []
    meetings.sort(key=lambda m: m.get('start_time', ''), reverse=True)
    candidates = []
    for mt in meetings:
        mp4 = vtt = None
        for rf in mt.get('recording_files', []):
            ft = rf.get('file_type', '').upper()
            if ft == 'MP4' and rf.get('status') == 'completed':
                mp4 = rf
            elif ft == 'TRANSCRIPT' and rf.get('status') == 'completed':
                vtt = rf
        if mp4 and vtt:
            candidates.append({
                'mp4_url': mp4['download_url'],
                'vtt_url': vtt['download_url'],
                'topic': mt.get('topic', 'Zoom Meeting'),
                'start_time': mt.get('start_time', ''),
                'duration': mt.get('duration', 0),
                'size_mb': round(mp4.get('file_size', 0) / 1024 / 1024, 1),
            })
    return token, candidates


def zoom_pick_latest(days=7):
    token, cands = zoom_list_candidates(days=days)
    if not cands:
        return None
    c = cands[0]
    return {'token': token, **c}


def find_media(vtt_path):
    vtt = Path(vtt_path)
    if not vtt.exists():
        raise SystemExit(f'VTT not found: {vtt}')
    prefix = vtt.stem.replace('.transcript', '')
    for p in vtt.parent.glob(f'{prefix}*'):
        if p.suffix.lower() in ('.mp4', '.mov', '.m4v'):
            return p, vtt
    for p in vtt.parent.glob('*.mp4'):
        return p, vtt
    raise SystemExit(f'video file not found next to VTT: {vtt.parent}')


# ---------- UTAGE Playwright ----------
def _login(ctx, login_url):
    page = ctx.new_page()
    try:
        page.goto(login_url, wait_until='networkidle', timeout=15000)
    except Exception:
        raise SystemExit(
            f'UTAGEログインページに接続できません: {login_url}\n'
            '  → --login-url が正しいか確認してください。\n'
            '  → 詳細: X記事 STEP3（UTAGE オペレーター）'
        )
    page.fill('input[name="email"]', UTAGE_EMAIL)
    page.fill('input[name="password"]', UTAGE_PASSWORD)
    page.click('button[type="submit"], input[type="submit"]')
    page.wait_for_load_state('networkidle')
    if 'login' in page.url.lower():
        raise SystemExit(
            'UTAGEログインに失敗しました（メールアドレスまたはパスワードが違います）。\n'
            '  → UTAGE_EMAIL / UTAGE_PASSWORD を確認してください。\n'
            '  → 詳細: X記事 STEP3（UTAGE オペレーター）'
        )
    return page


def create_empty_lesson(page, course_url, title, base):
    page.goto(f'{course_url}/lesson/create', wait_until='networkidle')
    page.wait_for_timeout(2000)
    page.fill('input[name="name"]', title)
    page.evaluate("""() => {
        const r = document.querySelector('input[name="type"][value="html"]');
        if (r) { r.checked = true; r.dispatchEvent(new Event('change', {bubbles:true})); }
    }""")
    page.select_option('select[name="is_published"]', '1')
    page.evaluate("document.getElementById('form').submit()")
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)
    url = page.url
    m = re.search(r'/lesson/([^/?]+)/edit', url)
    if m:
        return url
    page.goto(f'{course_url}/lesson', wait_until='networkidle')
    page.wait_for_timeout(2000)
    body = page.content()
    hrefs = re.findall(r'href="([^"]*/lesson/([^/"]+)/edit)"', body)
    if hrefs:
        return hrefs[0][0] if hrefs[0][0].startswith('http') else base + hrefs[0][0]
    raise RuntimeError(f'lesson URL not found after create: {url}')


def upload_video(page, mp4_path, upload_folder_url):
    page.goto(upload_folder_url, wait_until='networkidle')
    time.sleep(1)
    page.click('button:has-text("新規アップロード")')
    time.sleep(2)
    file_input = page.query_selector('#form-upload input[name="file"]') or \
                 page.query_selector('input[name="file"][type="file"]')
    if not file_input:
        raise RuntimeError('file input not found')
    file_input.set_input_files(str(mp4_path))
    time.sleep(2)
    submit_btn = page.query_selector('#button-video-upload')
    if not submit_btn:
        raise RuntimeError('upload button not found')
    try:
        with page.expect_navigation(timeout=600000):
            submit_btn.click(force=True)
    except Exception:
        time.sleep(15)
    time.sleep(3)
    page.goto(upload_folder_url, wait_until='networkidle')
    time.sleep(2)
    ids = page.eval_on_selector_all(
        '[data-video-id]',
        'els => els.map(e => e.getAttribute("data-video-id"))'
    )
    if not ids:
        ids = re.findall(r'data-video-id="([^"]+)"', page.content())
    if not ids:
        raise RuntimeError('video id not found')
    return ids[0]


# ---------- Element builder ----------
def _common(lesson_id_int, eid, etype, seq):
    type_to_element_id = {
        'section': 1, 'row': 2, 'col': 3,
        'video': 4, 'video-chapter': 5, 'button': 6,
        'text': 7, 'heading': 8, 'image': 9,
    }
    return {
        'id': eid, 'lesson_id': lesson_id_int,
        'page_id': 0, 'news_id': 0,
        'element_id': type_to_element_id.get(etype, 0),
        'seq': seq, 'type': etype,
    }


def build_rich_elements(lesson_id_int, contents_items, video_url, chapters_text, slides_url=None):
    def _normalize_ts(text):
        out = []
        for ln in (text or '').splitlines():
            ln = ln.rstrip()
            m = re.match(r'^(\d{1,2}):(\d{2})(\s+.*)?$', ln.strip())
            if m:
                mm, ss, rest = m.group(1), m.group(2), m.group(3) or ''
                ln = f'00:{int(mm):02d}:{ss}{rest}'
            out.append(ln)
        return '\n'.join(out)
    chapters_text = _normalize_ts(chapters_text)

    sections = []
    sec_seq = 0
    eid = 100

    def section(children):
        nonlocal sec_seq, eid
        col_id, row_id, sec_id = eid, eid + 1, eid + 2
        eid += 3
        col = {**_common(lesson_id_int, col_id, 'col', 0),
               'children': children, 'format': '', 'space': '', 'space_sp': ''}
        row = {**_common(lesson_id_int, row_id, 'row', 0),
               'children': [col], 'format': ''}
        sec = {**_common(lesson_id_int, sec_id, 'section', sec_seq),
               'align': 'center', 'children': [row], 'format': ''}
        sec_seq += 1
        sections.append(sec)

    def text_el(html):
        nonlocal eid
        e = {**_common(lesson_id_int, eid, 'text', 0),
             'text': html, 'children': [],
             'format': '', 'line_height': '', 'br_type': ''}
        eid += 1
        return e

    # セクション見出し用の共通HTML
    def _sec_heading(num, title):
        return (
            f'<div style="display:flex;align-items:center;gap:14px;'
            f'margin:0 0 22px;font-family:{FONT};">'
            f'<span style="font-family:\'SF Mono\',Menlo,monospace;font-size:13px;'
            f'font-weight:700;color:{ACCENT};letter-spacing:0.12em;">{num}</span>'
            f'<span style="font-size:18px;font-weight:700;color:{INK};'
            f'letter-spacing:0.05em;">{title}</span>'
            f'<span style="flex:1;height:1px;background:{BORDER};"></span>'
            f'</div>'
        )

    # 1) 今回扱った内容（深いグラデバッジ + 浮遊感カード）
    if contents_items:
        cards = []
        for i, (t, d) in enumerate(contents_items, 1):
            cards.append(
                f'<div style="display:flex;gap:20px;padding:22px;'
                f'background:#ffffff;border:1px solid {BORDER};border-radius:12px;'
                f'margin-bottom:14px;align-items:flex-start;'
                f'box-shadow:0 2px 8px rgba(30,74,122,0.06);">'
                f'<div style="flex:0 0 auto;width:48px;height:48px;'
                f'background:linear-gradient(135deg,{ACCENT_DARK} 0%,{ACCENT} 100%);'
                f'color:#ffffff;border-radius:10px;'
                f'display:flex;align-items:center;justify-content:center;'
                f'font-weight:800;font-size:18px;'
                f'font-family:\'SF Mono\',Menlo,monospace;letter-spacing:0.02em;'
                f'box-shadow:0 6px 16px rgba(10,41,71,0.35);">'
                f'{i:02d}</div>'
                f'<div style="flex:1;">'
                f'<div style="font-size:17px;font-weight:700;color:{INK};'
                f'letter-spacing:0.03em;margin-bottom:8px;line-height:1.5;">{t}</div>'
                f'<div style="font-size:15px;line-height:1.85;letter-spacing:0.03em;'
                f'color:{INK2};">{d}</div>'
                f'</div></div>'
            )
        section([text_el(
            f'<div style="font-family:{FONT};padding:32px 8px 8px;">'
            + _sec_heading('01', '今回扱った内容')
            + ''.join(cards) + '</div>'
        )])

    # 2) 動画 + チャプター
    video_el = {
        **_common(lesson_id_int, eid, 'video', 0),
        'text': chapters_text, 'video_type': 'app', 'video_url': video_url,
        'has_control': 1, 'time_display_type': 'current_time_duration',
        'relation_elements': '1', 'children': [],
        'design': '', 'countdown_item': '', 'autoplay_type': '',
        'playback_rate_type': '', 'has_fullscreen': '', 'skip_type': '',
        'format': '', 'loop': '',
    }
    eid += 1
    chapter_items = []
    for ln in chapters_text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        parts = ln.split(None, 1)
        if len(parts) == 2 and re.match(r'^\d{2}:\d{2}:\d{2}$', parts[0]):
            ts, body = parts
            chapter_items.append(
                f'<div style="display:flex;gap:14px;align-items:baseline;'
                f'padding:11px 0;border-bottom:1px solid #eef0f3;'
                f'font-size:15.5px;line-height:1.6;color:{INK};letter-spacing:0.02em;">'
                f'<span style="flex:0 0 auto;min-width:78px;'
                f'font-family:\'SF Mono\',Menlo,monospace;font-size:13px;font-weight:700;'
                f'color:{INK};padding:5px 10px;'
                f'background:#ffffff;border:1.5px solid {INK};'
                f'border-radius:4px;letter-spacing:0.02em;text-align:center;">{ts}</span>'
                f'<span style="flex:1;">{body}</span>'
                f'</div>'
            )
        else:
            chapter_items.append(
                f'<p style="margin:0 0 10px 0;font-size:16px;line-height:1.8;color:{INK};">{ln}</p>'
            )
    chapter_html = (
        f'<div style="font-family:{FONT};background:#ffffff;border-radius:12px;'
        f'padding:22px 20px 12px;margin-top:16px;'
        f'border:1px solid {BORDER};border-top:3px solid {ACCENT};">'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">'
        f'<span style="font-size:14px;font-weight:700;color:{INK};'
        f'letter-spacing:0.05em;">動画チャプター</span>'
        f'<span style="font-size:10px;letter-spacing:0.18em;color:{ACCENT};'
        f'font-family:\'SF Mono\',Menlo,monospace;font-weight:700;'
        f'padding:2px 8px;background:rgba(30,74,122,0.10);border-radius:3px;">CHAPTERS</span>'
        f'</div>'
        + ''.join(chapter_items) + '</div>'
    )
    chapter_el = {
        **_common(lesson_id_int, eid, 'video-chapter', 1),
        'text': chapter_html, 'relation_id': 1,
        'children': [], 'line_height': '', 'br_type': '',
    }
    eid += 1
    section([video_el, chapter_el])

    # 3) 資料ブロック（タイトル + 説明 + ボタン）
    if slides_url:
        urls = slides_url if isinstance(slides_url, (list, tuple)) else [slides_url]
        urls = [u for u in urls if u]
        if urls:
            def _label(u):
                ul = u.lower()
                if ul.endswith('.pdf') or '.pdf?' in ul:
                    return '資料PDFを開く'
                if 'docs.google.com/presentation' in ul:
                    return 'スライド資料を開く'
                return '資料を開く'
            btns = ''.join(
                f'<a href="{u}" target="_blank" rel="noopener" '
                f'style="display:block;padding:15px 24px;margin-bottom:10px;'
                f'background:{ACCENT};color:#ffffff;text-decoration:none;'
                f'border-radius:8px;font-size:15px;font-weight:700;'
                f'letter-spacing:0.04em;text-align:center;'
                f'box-shadow:0 6px 18px rgba(30,74,122,0.35);">'
                f'{_label(u)} →</a>'
                for u in urls
            )
            section([text_el(
                f'<div style="font-family:{FONT};margin-top:24px;padding:22px 20px;'
                f'background:{BG_ACCENT};border-left:4px solid {ACCENT};'
                f'border-radius:8px;">'
                f'<div style="color:{INK};font-size:15px;font-weight:700;'
                f'letter-spacing:0.04em;margin-bottom:4px;">本日のスライド資料</div>'
                f'<div style="color:{INK2};font-size:12.5px;letter-spacing:0.06em;'
                f'margin-bottom:14px;">復習用にダウンロードしてご活用ください</div>'
                + btns + '</div>'
            )])

    return sections


# ---------- Save ----------
def save_elements(ctx, edit_url, elements):
    m = re.match(r'(https://[^/]+)/site/([^/]+)/course/([^/]+)/lesson/([^/]+)/edit', edit_url)
    if not m:
        raise ValueError(f'bad edit_url: {edit_url}')
    base, site_id, course_id, lesson_id = m.groups()
    update_url = f'{base}/site/{site_id}/lesson/html/update'
    html_edit_url = f'{base}/site/{site_id}/course/{course_id}/lesson/{lesson_id}/html/edit'

    page = ctx.new_page()
    page.goto(html_edit_url, wait_until='networkidle')
    page.wait_for_timeout(5000)
    token = page.eval_on_selector('input[name="_token"]', 'e => e.value')
    meta = page.evaluate("""() => {
        const app = document.querySelector('#app');
        const proxy = app.__vue_app__._container._vnode.component.proxy;
        return {
            lesson: JSON.parse(JSON.stringify(proxy.lesson || {})),
            pageid: proxy.pageid || '',
            newsid: proxy.newsid || '',
        };
    }""")
    cookies = ctx.cookies()
    page.close()

    s = requests.Session()
    for c in cookies:
        s.cookies.set(c['name'], c['value'], domain=c.get('domain'))

    payload = {
        'site_id': site_id, 'course_id': course_id, 'lesson_id': lesson_id,
        'page_id': meta.get('pageid', ''), 'news_id': meta.get('newsid', ''),
        'elements': elements, 'lesson': meta.get('lesson', {}),
    }
    headers = {
        'X-CSRF-TOKEN': token,
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*',
        'Origin': base,
        'Referer': html_edit_url,
    }
    print(f'  POST {update_url}')
    resp = s.post(update_url, headers=headers,
                  data=json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    print(f'  status: {resp.status_code}, body: {resp.text[:200]}')
    return resp


# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--vtt', help='ローカルの .transcript.vtt パス')
    g.add_argument('--zoom', action='store_true', help='Zoom APIから直近の録画を取得')
    ap.add_argument('--zoom-days', type=int, default=7)
    ap.add_argument('--login-url', default=None, help='UTAGE オペレーターログインURL（未指定時は .env または対話入力）')
    ap.add_argument('--course-url', default=None, help='対象コースの URL（未指定時は .env または対話入力）')
    ap.add_argument('--upload-folder-url', default=None, help='動画アップロード先フォルダの URL（未指定時は .env または対話入力）')
    ap.add_argument('--slides-url', default=None)
    ap.add_argument('--yes', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--skip-upload', action='store_true')
    ap.add_argument('--video-url', default=None, help='既にアップ済みの動画URL')
    args = ap.parse_args()

    if not (args.vtt or args.zoom):
        raise SystemExit('--vtt または --zoom のどちらかを指定してください')

    setup_env(need_zoom=args.zoom)

    args.login_url = _prompt_url(
        'UTAGE_LOGIN_URL', 'UTAGE オペレーター画面のログインURL（オペレーター作成時のメールに記載）',
        'https://utage-system.com/operator/XXXXX/login',
        'X記事 STEP3', args.login_url)
    args.course_url = _prompt_url(
        'UTAGE_COURSE_URL', 'レッスンを追加する対象コースのURL（管理画面でコースを開いたときのURL）',
        'https://utage-system.com/site/SITE_ID/course/COURSE_ID',
        'X記事 STEP3', args.course_url)
    args.upload_folder_url = _prompt_url(
        'UTAGE_UPLOAD_FOLDER_URL', '動画アップロード先のメディアフォルダURL',
        'https://utage-system.com/media/video/FOLDER_ID',
        'X記事 STEP3', args.upload_folder_url)

    if args.slides_url is None:
        print('\n今回のレッスンで配布する資料URLを入力（なければEnter）:')
        print('  例: Google Slides や PDF の公開URL')
        ans = input('  資料URL: ').strip()
        if ans:
            if not ans.startswith('http'):
                print('  URL形式でないためスキップします')
            else:
                args.slides_url = ans
                print(f'  ✅ 「資料を開く」ボタンを追加します')
        else:
            print('  資料ボタンなしで進めます')

    base = f'{urlparse(args.login_url).scheme}://{urlparse(args.login_url).netloc}'

    tmpdir_obj = None
    if args.zoom:
        print(f'[0] Zoom APIから録画取得（直近{args.zoom_days}日）')
        token, cands = zoom_list_candidates(days=args.zoom_days)
        if not cands:
            raise SystemExit(f'直近{args.zoom_days}日にMP4+VTTが揃った録画なし')

        WEEKDAYS = ['月', '火', '水', '木', '金', '土', '日']

        def _fmt_entry(i, c):
            try:
                dt = datetime.fromisoformat(c['start_time'].replace('Z', '+00:00'))
                dt_local = dt.astimezone()
                wk = WEEKDAYS[dt_local.weekday()]
                ts_label = dt_local.strftime(f'%m/%d({wk}) %H:%M')
            except Exception:
                ts_label = c['start_time']
            return (f'  [{i}] {ts_label}  {c["topic"]}\n'
                    f'       {c["duration"]}分 / {c["size_mb"]}MB')

        print('')
        print('━' * 60)
        print(f'  📹 アップロードするZoom録画を選んでください（{len(cands)}件）')
        print('━' * 60)
        show_n = min(len(cands), 10)
        for i, c in enumerate(cands[:show_n], 1):
            print(_fmt_entry(i, c))
        if len(cands) > 10:
            print(f'  （残り{len(cands)-10}件は省略。--zoom-days で期間調整可）')
        print('━' * 60)

        if args.yes:
            idx = 0
            print(f'  --yes 指定のため [1] を自動選択')
        else:
            while True:
                ans = input(f'  番号を入力 [1-{show_n}] (Enter=1, q=中止): ').strip()
                if ans.lower() == 'q':
                    raise SystemExit('中止しました')
                if ans == '':
                    idx = 0
                    break
                if ans.isdigit() and 1 <= int(ans) <= show_n:
                    idx = int(ans) - 1
                    break
                print('  ⚠️ 無効な番号です。もう一度入力してください')
        info = {'token': token, **cands[idx]}
        print(f'  ✅ 選択: {info["topic"]} ({info["start_time"]})')
        tmpdir_obj = tempfile.TemporaryDirectory(prefix='zoom_dl_')
        tmpdir = Path(tmpdir_obj.name)
        safe = re.sub(r'[\\/*?:"<>|]', '_', info['topic'])
        mp4_dest = tmpdir / f'{safe}.mp4'
        vtt_dest = tmpdir / f'{safe}.transcript.vtt'
        print(f'    MP4 DL中 -> {mp4_dest.name}')
        zoom_download(info['mp4_url'], info['token'], mp4_dest)
        print(f'    {mp4_dest.stat().st_size / 1024 / 1024:.1f}MB')
        print(f'    VTT DL中')
        zoom_download(info['vtt_url'], info['token'], vtt_dest)
        args.vtt = str(vtt_dest)

    print('[1] メディア検出')
    mp4_path, vtt_path = find_media(args.vtt)
    print(f'    mp4: {mp4_path}')
    print(f'    vtt: {vtt_path}')

    print('[2] VTT解析')
    transcript, duration = parse_vtt(str(vtt_path))
    print(f'    duration: {duration} / lines: {len(transcript.splitlines())}')

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={'width': 1440, 'height': 900})
        _login(ctx, args.login_url)

        print('[3] Gemini生成')
        title = gen_title(transcript)
        print(f'    title: {title}')
        contents = gen_contents_list(transcript)
        print(f'    contents: {len(contents)}項目')
        chapters = gen_chapters(transcript)
        print(f'    chapters: {len(chapters.splitlines())}行')

        preview = {'title': title, 'contents': contents, 'chapters': chapters}
        Path('/tmp/utage_preview.json').write_text(
            json.dumps(preview, ensure_ascii=False, indent=2), encoding='utf-8')
        print('    preview -> /tmp/utage_preview.json')

        if args.dry_run:
            print('[dry-run] 終了')
            b.close()
            return

        if not args.yes:
            ans = input('\n保存しますか？ [y/N]: ').strip().lower()
            if ans != 'y':
                print('中止'); b.close(); return

        if args.video_url:
            video_url = args.video_url
        elif args.skip_upload:
            raise SystemExit('--skip-upload 時は --video-url も必要')
        else:
            print('[4] 動画アップロード')
            up_page = ctx.new_page()
            video_id = upload_video(up_page, mp4_path, args.upload_folder_url)
            up_page.close()
            video_url = f'https://utage-system.com/video/{video_id}'
            print(f'    video_url: {video_url}')

        print('[5] 新規レッスン作成')
        create_page = ctx.new_page()
        edit_url = create_empty_lesson(create_page, args.course_url, title, base)
        create_page.close()
        print(f'    edit_url: {edit_url}')

        print('[6] lesson_id_int 取得')
        html_edit_url = edit_url.replace('/edit', '/html/edit')
        probe = ctx.new_page()
        probe.goto(html_edit_url, wait_until='networkidle')
        probe.wait_for_timeout(5000)
        lesson_id_int = probe.evaluate("""() => {
            const proxy = document.querySelector('#app').__vue_app__._container._vnode.component.proxy;
            return proxy.lesson.id;
        }""")
        probe.close()
        print(f'    lesson_id_int: {lesson_id_int}')

        print('[7] 要素構築 & 保存')
        elements = build_rich_elements(lesson_id_int, contents, video_url, chapters, args.slides_url)
        resp = save_elements(ctx, edit_url, elements)
        if resp.status_code != 200:
            print('保存失敗'); b.close(); return

        lesson_url = edit_url.replace('/edit', '')
        print(f'\n完了: {lesson_url}')
        b.close()

    _post_run_menu(lesson_url, edit_url, args)


def _post_run_menu(lesson_url, edit_url, args):
    """レッスン作成後のアクション選択メニュー"""
    if args.yes:
        return
    print('')
    print('━' * 60)
    print(f'  ✅ レッスンページ作成完了')
    print(f'     公開URL: {lesson_url}')
    print(f'     編集URL: {edit_url}')
    print('━' * 60)
    print('  次は何をしますか？')
    print('    [1] ブラウザで公開ページを開く')
    print('    [2] ブラウザで編集画面を開く（タイトル・文言の微修正）')
    print('    [3] 続けてもう1本、別のZoom録画でレッスンを作る')
    print('    [4] デザインをカスタマイズする手順を表示（docs/04）')
    print('    [5] 終了')
    print('━' * 60)
    while True:
        ans = input('  番号を入力 [1-5] (Enter=5で終了): ').strip()
        if ans in ('', '5'):
            print('  お疲れさまでした。')
            return
        if ans == '1':
            import webbrowser
            webbrowser.open(lesson_url)
            print(f'  🌐 ブラウザで {lesson_url} を開きました')
            continue
        if ans == '2':
            import webbrowser
            webbrowser.open(edit_url)
            print(f'  🌐 ブラウザで {edit_url} を開きました')
            continue
        if ans == '3':
            print('')
            print('  以下のコマンドで続けてください:')
            print('    .venv/bin/python create_lesson.py --zoom')
            print('  （タスクをもう1本こなしたいなら、このシェルで↑を実行）')
            return
        if ans == '4':
            print('')
            print('  デザインをターゲット層に合わせて調整するには、Claude Code に以下を貼り付け:')
            print('  ─────────────────────────────────────────────────')
            print('  docs/04-customize-design.md を読んで、このスキルのターゲットは')
            print('  〇〇（例: 40代の英語学習者）なので、create_lesson.py の')
            print('  CUSTOMIZE セクションをそれに合わせて書き換えてください。')
            print('  ─────────────────────────────────────────────────')
            continue
        print('  ⚠️ 無効な番号です（1-5 で入力）')


if __name__ == '__main__':
    main()
