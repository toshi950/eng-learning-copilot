"""Google Sheetsからの未処理対話ログ取得（フェーズ6）

Gemini Live等（既存の音声会話サービス。会話エンジンの自作はしない方針。
内部設計メモ「フェーズ6」参照）で行った英会話の書き起こし全文を、
専用のGoogleフォーム（フェーズ5の単語帳用フォームとは別）で貼り付けてもらい、
そのSheetsから未処理の対話ログを取得する。フェーズ5の vocab/sheets.py と
同じ認証・構成方針だが、シート自体は別（CONVERSATION_SHEET_ID）。

前提（ユーザー側の事前準備・未実施）：
- フェーズ5用とは別のGoogleフォームを作成し、書き起こし全文を貼り付けられる
  長文回答欄を用意する
- そのSheetを GOOGLE_APPLICATION_CREDENTIALS のサービスアカウントに
  「閲覧者」共有する（フェーズ5と同じサービスアカウントを流用してよい）
- Googleフォームの列構成：①タイムスタンプ（自動） ②対話全文（貼り付け）
  フォーム未作成のため、実際の列順は仮定であり要確認・要調整。
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# TODO: フォーム作成後に実際のシート名・列順を確認して調整すること。
# 現状はA列=タイムスタンプ、B列=対話全文 と仮定している。
DEFAULT_RANGE = "Form Responses 1!A:B"


def _get_service():
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS が設定されていません。.env を確認してください。"
        )
    credentials = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=credentials)


def fetch_rows(
    *, spreadsheet_id: Optional[str] = None, range_: str = DEFAULT_RANGE
) -> list[dict]:
    """Sheetsの全行を取得し、辞書のリストとして返す（ヘッダー行は除く）。

    戻り値の各要素:
        {"row_number": int, "timestamp": str, "transcript": str}
        row_number はシート上の実際の行番号（1始まり）。処理済み管理（sync.py）で
        重複防止のキーとして使う。

    対話全文が空の行はスキップする。
    """
    spreadsheet_id = spreadsheet_id or os.environ.get("CONVERSATION_SHEET_ID")
    if not spreadsheet_id:
        raise RuntimeError(
            "CONVERSATION_SHEET_ID が設定されていません。.env を確認してください。"
        )

    service = _get_service()
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_)
        .execute()
    )
    values = result.get("values", [])
    if not values:
        return []

    rows = []
    for i, row in enumerate(values[1:], start=2):  # 1行目はヘッダー、シート上は2行目から
        if len(row) < 2:
            continue
        transcript = row[1].strip()
        if not transcript:
            continue
        rows.append(
            {
                "row_number": i,
                "timestamp": row[0],
                "transcript": transcript,
            }
        )
    return rows
