# Poirot 使用ガイド

> Poirotのインストール、設定、操作の完全ガイド。
>
> **言語：** [English](../USAGE.md) · [简体中文](USAGE.zh-CN.md) · [日本語](USAGE.ja.md)

---

## 目次

- [要件](#要件)
- [インストール](#インストール)
- [設定](#設定)
- [起動モード](#起動モード)
- [コマンド](#コマンド)
- [Skillシステム](#skillシステム)
- [Sandbox](#sandbox)
- [MCPツール](#mcpツール)
- [モデル・プロバイダー切替](#モデルプロバイダー切替)
- [TUIガイド](#tuiガイド)
- [トラブルシューティング](#トラブルシューティング)
- [FAQ](#faq)

---

## 要件

| 項目 | 要件 |
|------|------|
| Python | 3.12+ |
| OS | Windows / Linux / macOS |
| LLM API Key | DeepSeek（デフォルト）/ OpenAI / Qwen のいずれか一つ |
| Docker | Docker Sandboxモードのみ |
| Node.js | MCP stdioサーバー（freeweb-mcp等）のみ |

---

## インストール

### 1. クローン

```bash
git clone <repo-url>
cd Poirot
```

### 2. 仮想環境

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

> condaも可：`conda create -n poirot python=3.12 && conda activate poirot`

### 3. インストール

```bash
# 基本 + 開発ツール（pytest）
pip install -e ".[dev]"

# Docker Sandbox対応
pip install -e ".[docker]"
```

### 4. 設定

```bash
cp .env.example .env
```

`.env`を編集 — 少なくとも一つのAPI Keyを入力：

```env
DEEPSEEK_API_KEY=sk-your-key-here
```

### 5. 確認

```bash
poirot
```

PoirotのASCIIロゴとウェルカム画面が表示されれば成功。

---

## 設定

プロジェクトルートの`.env`ファイルで設定します。`.env.example`が完全なテンプレートです。

### LLMプロバイダー

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `DEEPSEEK_API_KEY` | DeepSeek APIキー（デフォルト、フォールバック尾部） | — |
| `DEEPSEEK_BASE_URL` | DeepSeekエンドポイント | `https://api.deepseek.com` |
| `OPENAI_API_KEY` | OpenAI APIキー | — |
| `OPENAI_BASE_URL` | OpenAIエンドポイント（プロキシ用） | 公式デフォルト |
| `QWEN_API_KEY` | Qwen APIキー | — |
| `QWEN_BASE_URL` | Qwenエンドポイント | `https://dashscope.aliyuncs.com/compatible-mode/v1` |

> 少なくとも一つのプロバイダーを設定してください。DeepSeekをフォールバックとして設定を推奨します。

### Sandbox

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `POIROT_SANDBOX_USE` | Sandboxプロバイダーパス（空=無効） | 空 |
| `POIROT_SANDBOX_IMAGE` | Dockerイメージ名 | `all-in-one-sandbox:latest` |
| `POIROT_SANDBOX_PORT` | コンテナ開始ポート | `18000` |
| `POIROT_SANDBOX_EXECUTOR` | Docker実行環境（`local` / `wsl`） | `local` |
| `POIROT_SANDBOX_WSL_DISTRO` | WSLディストロ名 | `Ubuntu` |
| `POIROT_SANDBOX_WSL_USER` | WSLユーザー | デフォルトユーザー |
| `POIROT_SANDBOX_CONTAINER_PREFIX` | コンテナ名プレフィックス | `poirot-sandbox` |
| `POIROT_SANDBOX_IDLE_TIMEOUT` | アイドル破棄タイムアウト秒（0=破棄しない） | `600` |
| `POIROT_SANDBOX_REPLICAS` | ウォームプールサイズ（0=事前作成しない） | `3` |

**Local Sandbox（ホストプロセス）:**
```env
POIROT_SANDBOX_USE=poirot.backend.agents.sandbox.local.local_sandbox_provider:LocalSandboxProvider
```

**Docker Sandbox（コンテナ分離）:**
```env
POIROT_SANDBOX_USE=poirot.backend.agents.sandbox.docker.docker_sandbox_provider:DockerSandboxProvider
```

> Dockerモード：最初にイメージをプル — `docker pull all-in-one-sandbox:latest`
>
> Windows + WSL2：`POIROT_SANDBOX_EXECUTOR=wsl`を設定

### MCP

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `POIROT_MCP_ENABLED` | MCPマスタースイッチ | `false` |
| `POIROT_MCP_CONFIG_PATH` | MCP設定ファイルパス | `.poirot/mcp_servers.yaml` |
| `POIROT_MCP_CORE_TOOLS` | コアツール（カンマ区切り、起動時にロード） | `web_search,browse_page` |

### Skill

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `POIROT_SKILL_ENABLED` | Skillモジュールマスタースイッチ | `false` |
| `POIROT_SKILL_DB_PATH` | Skill SQLiteパス | `.poirot/skills.db` |
| `POIROT_SKILL_DIRS` | Skillスキャンディレクトリ | `skills/` |
| `POIROT_SKILL_INCLUDE_BUILTIN` | builtinコアSkillをロード | `true` |
| `POIROT_SKILL_MAX_INJECT` | 1ターンの最大注入Skill数 | `3` |
| `POIROT_SKILL_QUALITY_THRESHOLD` | 品質フィルター閾値 | `0.3` |
| `POIROT_SKILL_MIN_SELECTIONS` | 品質フィルター適用最小選択回数 | `5` |

**Skill進化（Layer 2）:**

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `POIROT_SKILL_EVOLVE_ENABLED` | 進化スイッチ | `false` |
| `POIROT_SKILL_EVOLVE_THRESHOLD` | 進化トリガー閾値 | `0.3` |
| `POIROT_SKILL_EVOLVE_MIN_SELECTIONS` | 進化最小選択回数 | `5` |
| `POIROT_SKILL_EVOLVE_COOLDOWN_TURNS` | 進化クールダウンターン数 | `10` |
| `POIROT_SKILL_EVOLVE_MUTATE_BUDGET` | 変異トークン予算 | `20` |
| `POIROT_SKILL_EVOLVE_MAX_STEPS` | 最大進化ステップ数 | `5` |

**Skill評価（Layer 3）:**

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `POIROT_SKILL_EVAL_ENABLED` | 評価スイッチ | `false` |
| `POIROT_SKILL_EVAL_JUDGMENT_ENABLED` | 実行判定 | `true` |
| `POIROT_SKILL_EVAL_TASK_JUDGE_ENABLED` | タスク品質スコアリング | `true` |
| `POIROT_SKILL_EVAL_CONTRACT_CHECK` | レスポンス契約チェック | `true` |
| `POIROT_SKILL_EVAL_ASYNC` | 非同期eval | `true` |
| `POIROT_SKILL_EVAL_SKIP_NO_SKILL` | Skill未注入時にevalスキップ | `true` |
| `POIROT_SKILL_EVAL_RUNTIME_WINDOW` | RuntimeTrackerウィンドウ | `20` |
| `POIROT_SKILL_EVAL_DEGRADATION_DELTA` | 劣化判定delta | `0.15` |

---

## 起動モード

### 1. TUIフルスクリーン（デフォルト）

```bash
poirot
```

| キー | アクション |
|------|-----------|
| `Ctrl+P` | コマンドパレット |
| `Ctrl+N` | MCPパネル |
| `Ctrl+L` | 画面クリア |
| `Ctrl+C` | 終了 |
| `Enter` | 送信 |
| `Shift+ドラッグ` | コピー選択 |

### 2. CLIスクロール

```bash
poirot cli
```

### 3. 単発リサーチ（非対話）

```bash
poirot run "2026年のAIエージェントフレームワーク動向を分析"
poirot run "質問" --thread-id my-thread --run-id my-run
poirot run "簡単な質問" --no-expert
poirot run "質問" --no-artifact
```

---

## コマンド

### 基本

| コマンド | 説明 |
|---------|------|
| `/help` | 全コマンド表示 |
| `/clear` | 画面クリア |
| `/exit` `/quit` | 終了 |
| `/expand` | 前ラウンドのThought + ツール結果を展開 |
| `/thinking on\|off` | Thought折りたたみ表示切替 |

### モード

| コマンド | 説明 |
|---------|------|
| `/expert` | expertモード（ディープリサーチ）に切替 |
| `/default` | defaultモード（ライト会話）に切替 |
| `/report [topic]` | 現在のスレッドからレポート生成 |

### モデル・ツール

| コマンド | 説明 |
|---------|------|
| `/model` | 現在のモデル表示 |
| `/model <provider>` | プロバイダー切替 |
| `/model <provider> <model>` | プロバイダー + モデル指定切替 |
| `/tools` | 利用可能ツール一覧 |
| `/thread` | スレッド情報表示 |

### Skill

| コマンド | 説明 |
|---------|------|
| `/skill` `/skill list` | アクティブSkill一覧 |
| `/skill search <query>` | builtin Skill検索 |
| `/skill <name>` | Skill強制使用（override） |
| `/skill off` | overrideクリア |
| `/skill enable/disable <name>` | Skill有効化/無効化 |
| `/skill install <path> [name]` | 外部Skillインストール |
| `/skill evolve <name>` | 手動進化トリガー |
| `/skill capture <pattern> <name>` | 新規Skillキャプチャ |
| `/skill history <name>` | Skillバージョン履歴 |
| `/skill health [name]` | Skillヘルスレポート（Layer 3） |
| `/skill eval-history <name>` | SkillJudgment履歴（Layer 3） |

### MCP

| コマンド | 説明 |
|---------|------|
| `/mcp` `/mcp list` | MCPサーバー・ツール一覧 |
| `/mcp reload` | MCP設定リロード |

---

## Skillシステム

Skillは**リサーチプロセス知識バンドル**です — promptレベル注入であり、実行可能な関数ではありません。「情報源の検証方法」はSkill、「Web検索の実行」はツールです。

### 三層アーキテクチャ

**Layer 1（ベース）:**
- `SQLiteSkillStore` — ストレージ + バージョンDAG + 4カウンター
- `SkillSelector` — 品質フィルター + LLMハイブリッド選択
- `SkillInjectionMiddleware` — `before_model`注入
- `SkillMetricsMiddleware` — `wrap_tool_call`適用マーキング + `after_agent`アトリビューション

**Layer 2（進化）:**
- `MetricMonitor` — effective_rateが閾値未満でトリガー
- `IVEFocuser` — 5問診断 + 偏差エビデンス
- `LLMMutator` — LLMによるSkillテキスト変異
- `ScoreDeltaGate` — 変異前後スコアゲート
- `GitRatchet` — ラチェット：劣化時にロールバック

**Layer 3（評価）:**
- `SkillJudgmentAnalyzer` — per-skill per-task LLM判定
- `TaskQualityJudge` — 4次元スコアリング（accuracy 0.50 / completeness 0.35 / efficiency 0.05 / depth 0.10）
- `ResponseContractChecker` — 契約対応ルールチェック
- `RuntimeTracker` — applied_rateトレンド + `degraded_skills()`ロールバックシグナル

### Skill有効化

```env
POIROT_SKILL_ENABLED=true
```

BuiltinコアSkillは起動時に自動ロード。ユーザーSkillは`skills/`ディレクトリに配置。

### Skillファイル形式

```markdown
---
name: source-verification
description: 情報源の信頼性を検証
allowed_tools:
  - web_search
  - browse_page
---

# Source Verification Skill

## 使用タイミング
情報源の信頼性を検証する必要がある時...

## 方法
1. ソースの権威性を確認
2. 複数ソースで交差検証
3. ...
```

### Builtin Skills

Poirotは5カテゴリ36個のbuiltin Skillを同梱：

| カテゴリ | 数 | 例 |
|---------|-----|-----|
| core | 12 | deep-research, source-verification, plan, spike, skill-creator, test-driven-development |
| research | 11 | arxiv, osint-investigation, systematic-literature-review, research-paper-writing |
| software-development | 7 | github-code-review, github-pr-workflow, node-inspect-debugger, python-debugpy |
| creative | 3 | architecture-diagram, chart-visualization, frontend-design |
| productivity | 2 | code-documentation, ppt-generation |

> Coreカテゴリは自動ロード。その他は`/skill search <query>`で発見。

---

## Sandbox

### Local Sandbox

```env
POIROT_SANDBOX_USE=poirot.backend.agents.sandbox.local.local_sandbox_provider:LocalSandboxProvider
```

### Docker Sandbox

```env
POIROT_SANDBOX_USE=poirot.backend.agents.sandbox.docker.docker_sandbox_provider:DockerSandboxProvider
POIROT_SANDBOX_IMAGE=all-in-one-sandbox:latest
```

```bash
docker pull all-in-one-sandbox:latest
```

### Windows + WSL2

```env
POIROT_SANDBOX_EXECUTOR=wsl
POIROT_SANDBOX_WSL_DISTRO=Ubuntu
```

---

## MCPツール

```env
POIROT_MCP_ENABLED=true
```

設定ファイル`.poirot/mcp_servers.yaml`：

```yaml
servers:
  freeweb:
    transport: stdio
    command: npx
    args: ["-y", "freeweb-mcp@latest"]
    enabled: true
    timeout: 300
    tools:
      include: []
      exclude: ["search_and_browse"]

fallback_chains:
  web_search:
    - freeweb:web_search
    - builtin:ddg_search

core_tools:
  - web_search
  - browse_page
```

変更後`/mcp reload`でリロード。

---

## モデル・プロバイダー切替

### ルーティングチェーン

```
researcher: [openai, qwen] → deepseek（フォールバック尾部）
reporter:   [openai, qwen] → deepseek（フォールバック尾部）
```

### 起動時指定

```bash
poirot --provider openai
poirot --provider qwen --model qwen-max
```

### 実行時切替

```
/model                    # 現在のモデル表示
/model openai             # 切替
/model openai gpt-4.1     # 切替 + モデル指定
```

### 対応プロバイダー

| プロバイダー | デフォルトモデル | ウィンドウ |
|------------|----------------|-----------|
| deepseek | deepseek-v4-flash | 200K |
| openai | gpt-4.1-mini | — |
| qwen | qwen-plus | — |

---

## TUIガイド

- **ウェルカム画面**：中央ロゴ + 入力ボックス、最初の入力で会話画面に切替
- **会話画面**：左側会話エリア + 下部入力ボックス + ステータスバー、ワイド画面では右側情報パネル
- **Thought折りたたみ**：`+ Thought: 120ms`、`/expand`で全文展開、`/thinking off`で非表示
- **コピー**：`Shift`を押しながらドラッグで選択

---

## トラブルシューティング

### `api_key is empty for provider: deepseek`

`.env`のAPI Keyが空です。少なくとも一つのプロバイダーを設定してください。

### Skillモジュールがロードされない

1. `POIROT_SKILL_ENABLED=true`
2. `skills/`ディレクトリが存在
3. プロジェクトルートから起動

### MCPツールが表示されない

1. `POIROT_MCP_ENABLED=true`
2. server `enabled: true`
3. `command`が実行可能
4. `/mcp list`で状態確認、`/mcp reload`で再試行

### Docker Sandbox起動失敗

1. Dockerデーモンが実行中
2. イメージがプル済み
3. Windows + WSL2：`POIROT_SANDBOX_EXECUTOR=wsl`

---

## FAQ

**Q: DeepSeekを使わなければなりませんか？**

A: いいえ。DeepSeekはデフォルトかつフォールバック尾部です。OpenAIやQwenのみでも使用可能ですが、DeepSeekをフォールバックとして設定を推奨します。

**Q: SkillとMCPツールの違いは？**

A: Skillは「リサーチプロセス知識」（know how）— prompt注入、実行不可。MCPツールは「外部能力」（do something）— function call、実行可能。

**Q: Skill進化はSkillファイルを変更しますか？**

A: はい。Layer 2有効時、`LLMMutator`がSkillテキストを変異し新バージョンを作成します。`GitRatchet`が劣化時にロールバックします。`/skill history <name>`で履歴確認。

**Q: 高度な機能を全て無効にしてシンプルな会話をするには？**

A:
```env
POIROT_SKILL_ENABLED=false
POIROT_MCP_ENABLED=false
POIROT_SANDBOX_USE=
```
その後`/default`でライトモードに。

**Q: 独自Skillの書き方は？**

A: `skills/`下にサブディレクトリを作成し、`SKILL.md`（frontmatter + 本文）を配置。再起動または`/skill list`で確認。

**Q: テストの実行方法は？**

A:
```bash
python -m pytest poirot/backend/tests/ -q
python -m pytest poirot/backend/tests/v1/unit/skill/ -q
```

---

<div align="center">

<sub>質問はIssueへ。</sub>

</div>
