# Code Review Skills

Found via `npx skills find code-review`. These can be installed to enhance agent code review capabilities.

## Top recommendations

| Skill | Installs | What it does | Install command |
|---|---|---|---|
| **`obra/superpowers@requesting-code-review`** | 176.3K | Guidelines for requesting effective code reviews from human reviewers | `npx skills add obra/superpowers@requesting-code-review -g -y` |
| **`mattpocock/skills@code-review`** | 158K | General code review best practices and patterns | `npx skills add mattpocock/skills@code-review -g -y` |
| **`obra/superpowers@receiving-code-review`** | 146.2K | How to process and respond to code review feedback | `npx skills add obra/superpowers@receiving-code-review -g -y` |
| **`wshobson/agents@code-review-excellence`** | 25.3K | Advanced code review excellence patterns | `npx skills add wshobson/agents@code-review-excellence -g -y` |
| **`github/awesome-copilot@sql-code-review`** | 12K | SQL-specific code review | `npx skills add github/awesome-copilot@sql-code-review -g -y` |
| **`github/awesome-copilot@postgresql-code-review`** | 11.3K | PostgreSQL-specific code review | `npx skills add github/awesome-copilot@postgresql-code-review -g -y` |

## Recommendation

For this codebase (Python + TypeScript monorepo with PostgreSQL), the most useful skill is **`mattpocock/skills@code-review`** (general purpose, high installs). For SQL/DB-specific review, `github/awesome-copilot@postgresql-code-review` is also relevant.

To install a skill globally:
```sh
npx skills add <owner/repo@skill> -g -y
```
