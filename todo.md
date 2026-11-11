# TODO — hakusan-tui

設計書: `docs/slurm.md` / 記録: `work_history.md`

## Phase 0 — 土台

- [x] CLAUDE.md / todo.md / work_history.md 作成
- [x] `pyproject.toml`（uv, Textual, pytest, ruff）
- [x] CLI（`--demo` `--readonly` `--profile` `--diagnose` `--version`）
- [x] データモデル（Job / JobStep / Node / Partition / GpuAllocation / CommandResult / Capability）
- [x] 日本語化（状態・待機理由・ノード状態）
- [x] 安全な非同期コマンドランナー（argv配列、timeout、出力上限）
- [x] デモアダプター + デモデータ
- [x] Textual 9タブ骨格、ヘッダー/フッター、1〜9キー
- [x] Docker上のSlurmテストクラスタ（slurmdbd込み、偽GPU GRES）

## Phase 1 — 読み取り（P0）

- [x] Slurmパーサー（squeue/sinfo JSON + 区切りテキストのフォールバック、scontrol -o、sacct -P）
- [x] Capability Detection（`--json` 可否、spart/module/sacct/PBS有無）
- [x] リフレッシュ・キャッシュ（TTL、単一フライト、失敗時に直前スナップショット保持）
- [x] 概要タブ
- [x] 自分のジョブタブ（フィルタ、詳細）
- [x] キュータブ（パーティション別集計、待機理由説明）
- [x] GPUタブ（割当集計、重複排除、分割GPU別表示、実使用率は未取得表示）
- [x] ノードタブ（ノード一覧 / パーティション / spart原文）

## Phase 2 — ジョブライフサイクル（P0）

- [x] scancel（所有者再検査、二段階確認、readonly/demo無効）
- [x] 投入フォーム + テンプレート + スクリプト生成 + 検証 + プレビュー
- [x] 保存（上書き禁止）→ `sbatch --parsable`
- [x] 履歴タブ（sacct、ステップ階層、MaxRSS未確定）
- [x] ログ末尾表示（1MiB上限、ANSI/制御文字除去）

## Phase 3 — 残機能（P1/P2）

- [x] ツール: Module一覧（`bash -lc` 定型コマンド）
- [x] ツール: 対話ジョブ（`App.suspend()` + salloc）
- [x] ツール: ステージング説明 + テンプレート
- [x] ツール: PBS互換の検出と案内（qstat/pbsnodes 読み取りのみ。qalter/qhold/qrls/qrerun は案内のみ・未実装）
- [x] ツール: 環境診断
- [x] ヘルプタブ（ガイド、用語、資料ページ対応）

## Phase 4 — 検証・仕上げ

- [x] Docker Slurmで結合テスト（sbatch → squeue → sacct → ログ → scancel）
- [x] README / docs/usage.md / docs/hakusan-site.md / docs/development.md
- [x] `uv run pytest` / `uv run ruff check .` 成功
- [ ] HAKUSAN実機確認（要実機・未実施。項目は docs/hakusan-site.md）

## 汎用化（v0.2.0）

- [x] パーティション・ノードの種別を名前でなく GRES / TRES で判定（`adapters/classify.py`）
- [x] HAKUSAN 以外の GPU 型は Slurm の type 名で集計
- [x] README に「他の Slurm クラスタで使う」を追加

## 残課題・将来拡張

- [ ] PBS変更系（qalter/qhold/qrls/qrerun）の所有者確認＋二段階確認つき実行
- [ ] GPU実機メトリクス（sacct の gres/gpuutil 等、サイト設定次第）
- [ ] 英語UI切替（i18n）
- [ ] SSHリモートモード
- [ ] サイト固有の説明文・テンプレート（`$JOBDIR` など）を `--profile` で切替
