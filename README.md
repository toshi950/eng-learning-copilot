# English Learning Automation (working title)

## 課題 (Problem)
🇯🇵 多くの英語学習アプリは、音声知覚のトレーニングや定型表現（チャンク）を瞬時に
引き出す練習には強みがあるが、実務ドメインの一次情報を教材として、聴解・読解
能力そのものを底上げする領域までは踏み込めていない。自分の専門分野の海外一次
情報を教材として活用し、聴解・読解力を鍛える個人プロジェクト。

🇬🇧 Many English-learning apps excel at auditory-perception drills or rapid
retrieval of fixed expressions, but stop short of directly building listening/
reading comprehension using real-world material from one's own professional
domain. A personal project to train listening/reading using first-hand news
in my professional field.

## 実装済み機能 (Implemented)

### 1. 長文読解教材の生成 / Reading Material Generation

🇯🇵 英語の長文を渡すと、スラッシュリーディング（意味・構文のまとまりごとの分割）と、
チャンクごとの構文解説・直訳をまとめたMarkdown教材を自動生成する。

🇬🇧 Given an English passage, automatically generates a Markdown study sheet with
slash-reading (chunked by meaning and syntax) and a chunk-by-chunk grammar
explanation / literal translation table.

> 💡 当初は記事の背景知識（用語解説等）も同時生成する設計だったが、実際の記事で
> 試した結果、Web検索を伴わないLLM単体では学習データのカットオフ以降に起きた
> 事実を誤判定するケースが見つかったため撤回。背景知識生成は、Web検索と組み
> 合わせる後続フェーズ（下記3）へ移した。
>
> Originally the design also generated background knowledge (e.g. terminology)
> for each article, but testing on a real article surfaced cases where the
> model — without web search — misjudged facts that occurred after its
> training cutoff. This was rolled back and moved to the sourcing phase
> below, where facts can be grounded via search.

### 2. 音声化 / Text-to-Speech

🇯🇵 教材の英文を読み上げ音声（MP3）として出力する。長文ナレーション向けの
高品質ボイスを採用し、通勤中のリスニング教材として使えるようにしている。

🇬🇧 Renders the English passage as an MP3 using a voice designed for long-form
narration, so the material doubles as listening practice.

### 3. 専門分野の情報収集 / Domain-Specific Sourcing

🇯🇵 会計監査・内部統制・データ分析といった自分の専門分野に関するRSSフィードから
記事候補を集め、その中から読む価値のある英語記事を選定して、音読・リスニング用の
抜粋を出典情報つきで取得する。

🇬🇧 Collects article candidates from RSS feeds covering my professional domain
(auditing, internal control, data analytics), selects one worth reading, and
retrieves an excerpt with its source metadata.

> 💡 当初はLLMに探索的なWeb検索をさせていたが、検索結果が文脈に累積して
> 再処理されるため、実行コストが検索回数に対して急激に増える構造だった。
> 実測したうえで「記事を見つける工程」をRSS側に移し、LLMには選定と取得だけを
> 任せる2段構成に作り替えて、1回あたりのコストを約1/4に削減した。
>
> The first version let the model search its way to a topic, but search
> results accumulate in context and get reprocessed, so cost grew sharply
> with the number of searches. After measuring this, discovery was moved to
> RSS and the model was left with only selection and retrieval — cutting the
> per-run cost to roughly a quarter.

### 4. 自動化フロー統合 / Pipeline Integration

🇯🇵 上記1〜3を1コマンドで実行し、記事の選定から読解教材・音声の生成までを
まとめて行う。出力はノート1本と音声1本の組で、ノート内に音声が埋め込まれるため、
そのまま「読む・聴く」教材として開ける。

🇬🇧 Runs the three phases above as a single command, producing one note and one
audio file per run. The audio is embedded in the note, so a run yields a
ready-to-use reading + listening set.

### 5. 未知語の単語帳自動化 / Vocabulary Deck Automation

🇯🇵 読解教材を読んでいて出会った未知語やイディオムを、スマホからGoogleフォームに
単語とその原文（実際に読んだ一文）を入力するだけで、AnkiのSRSカードとして
自動生成する。カードは原文の空所補充（cloze）＋英語定義を中心に構成し、
日本語訳は補助的に添えるだけにとどめている。

🇬🇧 Captures unfamiliar words and idioms encountered while reading the study
material: type the word and the original sentence it appeared in into a
Google Form from a phone, and it's automatically turned into an Anki
spaced-repetition card. Cards center on a cloze-deletion sentence plus an
English definition, with the Japanese translation kept as a secondary aid.

> 💡 当初は二重符号化（dual coding）の観点から、単語ごとに関連画像を添付する
> 設計だった。しかし公開画像API（Openverse）で実際に専門分野の抽象語彙を
> 検索したところ、意味的に無関係な画像しかヒットせず実用に耐えないと判明。
> 画像案を撤回し、代わりに「原文からの空所補充＋英語定義」という、翻訳に
> 頼らず英語のまま意味処理させる構成に変更した。
>
> The design originally attached a related image to each card, based on
> dual-coding theory. But searching a public image API (Openverse) for
> abstract domain-specific vocabulary returned only semantically unrelated
> results, so the image idea was dropped in favor of a cloze sentence plus
> an English definition — encouraging meaning-processing in English rather
> than relying on translation.

### 6. 会話フィードバックの拡張 / Conversation Feedback Extension

🇯🇵 Gemini Live等の既存の音声対話サービスで行った英会話の書き起こしを貼り付けると、
学習者自身の発話にあった不自然な表現・文法ミスだけを抽出し、フェーズ5と同じ
Ankiカードとして自動生成する。対話相手側の表現は対象外とし、自分の誤りだけに
焦点を当てている。

🇬🇧 Paste the transcript of an English conversation from an existing voice-chat
service (e.g. Gemini Live), and it extracts only the unnatural phrasing or
grammar mistakes in the learner's own speech, turning them into the same
Anki cards as Phase 5. The other party's phrasing is excluded — the focus
stays on the learner's own errors.

> 💡 当初は会話エンジン自体（リアルタイム音声対話・書き起こし）をNext.js＋
> OpenAI Realtime APIで自作する設計だった。しかし「安定した既存の音声対話
> サービス（Gemini Live）をそのまま会話エンジンとして使い、自作するのは
> 対話後の書き起こしから改善フレーズを抽出するバックエンド処理だけに絞れば
> よいのでは」という気づきから設計を全面転換。会話エンジンという最も難しく
> 運用コストのかかる部分の自作を避け、実際に差別化価値のある処理（自分の
> 誤りの検出・訂正）に開発を集中させた。
>
> The original design called for building the conversation engine itself
> (real-time voice chat and transcription) from scratch with Next.js and the
> OpenAI Realtime API. That was scrapped in favor of using an existing,
> stable voice-chat service (Gemini Live) as the conversation engine as-is,
> narrowing the actual build to just the backend that extracts improvement
> phrases from the transcript afterward — avoiding the hardest, most
> costly-to-operate part (the conversation engine) and concentrating effort
> on the part that actually differentiates the tool (detecting and
> correcting one's own mistakes).

## 技術スタック (Tech stack)

Python / Anthropic Claude API / Google Cloud Text-to-Speech / RSS (feedparser) /
Google Sheets API / Anki (AnkiConnect)

## 進捗 (Status)
- [x] 長文読解教材の生成 / Reading material generation
- [x] 音声化 / Text-to-speech
- [x] 専門分野の情報収集 / Domain-specific sourcing
- [x] 自動化フロー統合 / Pipeline integration
- [x] 未知語の単語帳自動化 / Vocabulary deck automation
- [x] 会話フィードバックの拡張 / Conversation feedback extension
