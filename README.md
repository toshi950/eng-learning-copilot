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

### 長文読解教材の生成 / Reading Material Generation

🇯🇵 英語の長文を渡すと、スラッシュリーディング（意味・構文のまとまりごとの分割）と、
チャンクごとの構文解説・直訳をまとめたMarkdown教材を自動生成する。

🇬🇧 Given an English passage, automatically generates a Markdown study sheet with
slash-reading (chunked by meaning and syntax) and a chunk-by-chunk grammar
explanation / literal translation table.

> 💡 当初は記事の背景知識（用語解説等）も同時生成する設計だったが、実際の記事で
> 試した結果、Web検索を伴わないLLM単体では学習データのカットオフ以降に起きた
> 事実を誤判定するケースが見つかったため撤回。背景知識生成は、Web検索と組み
> 合わせる後続フェーズで改めて実装する予定。
>
> Originally the design also generated background knowledge (e.g. terminology)
> for each article, but testing on a real article surfaced cases where the
> model — without web search — misjudged facts that occurred after its
> training cutoff. This was rolled back; background knowledge generation will
> be revisited in a later phase that incorporates web search.

## 進捗 (Status)
- [x] 長文読解教材の生成 / Reading material generation
- [ ] （以降のステップは実装が進み次第、README更新で追記 / further steps will be
  added here as they are implemented）
