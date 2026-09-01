"""Google Sheetsからの未処理行取得（フェーズ5）

Googleフォームの回答が蓄積されるSheetsから、単語/イディオムとその原文（学習者が
実際に読んだ文からの転記）の行を取得する。認証はフェーズ2で作成済みのGCP
サービスアカウント（GOOGLE_APPLICATION_CREDENTIALS）を流用する。

前提（ユーザー側の事前準備・未実施）：
- 対象のGoogle Sheetを、サービスアカウントのメールアドレスに「閲覧者」として
  共有しておくこと（Sheets APIは共有されたシートしか読めない）
- GCPプロジェクト（フェーズ2で使った the-dock-222013）側でSheets APIを
  有効化しておくこと（TTS APIとは別に有効化が必要）
- Googleフォームの列構成：①単語/イディオム ②それを含む一文・文節の原文転記
  （内部設計メモ「フェーズ5」参照）。フォーム未作成のため、実際の列順・
  シート名（デフォルトは "Form Responses 1"）は仮定であり要確認・要調整。
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
# 現状はA列=タイムスタンプ、B列=単語/イディオム、C列=原文 と仮定している
# （Googleフォームの標準的な回答シート構成：A列に自動でタイムスタンプが入る）。
DEFAULT_RANGE = "Form Responses 1!A:C"


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
        {"row_number": int, "timestamp": str, "word": str, "sentence": str}
        row_number はシート上の実際の行番号（1始まり）。処理済み管理（sync.py）で
        重複防止のキーとして使う。

    列が3つ揃っていない行（フォーム未回答の項目がある等）はスキップする。
    """
    spreadsheet_id = spreadsheet_id or os.environ.get("VOCAB_SHEET_ID")
    if not spreadsheet_id:
        raise RuntimeError(
            "VOCAB_SHEET_ID が設定されていません。.env を確認してください。"
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
        if len(row) < 3:
            continue
        word = row[1].strip()
        sentence = row[2].strip()
        if not word or not sentence:
            continue
        rows.append(
            {
                "row_number": i,
                "timestamp": row[0],
                "word": word,
                "sentence": sentence,
            }
        )
    return rows
