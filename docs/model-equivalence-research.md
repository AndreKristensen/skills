# Role-equivalent Claude and OpenAI models for routing

_Checked 2026-10-10 against current first-party documentation._

## Conclusion

For a three-tier routing plugin, the closest current role mapping is:

| Claude tier | Closest OpenAI role | Routing interpretation |
| --- | --- | --- |
| Claude Haiku 5.5 | GPT-6 Luna (`gpt-6-luna`) | Cheapest, fastest tier for focused, high-volume work |
| Claude Sonnet 5.5 | GPT-6.1 Sol (`gpt-6.1-sol`) | Balanced daily driver for strong work at lower cost than the top tier |
| Claude Opus 5.5 | GPT-6 Astra (`gpt-6-astra`) | Highest-quality tier for demanding reasoning, coding, and agent work |

This is **role equivalence, not benchmark equivalence**. The vendors define similar product slots, but model behavior, tool use, tokenization, effective latency, and quality vary by workload. The plugin should treat these pairs as default routing buckets, then validate them with its own coding and agent evals. OpenAI explicitly recommends comparing models on the same tasks, and Anthropic says effort labels do not represent the same amount of thinking even across Claude models. Cross-vendor effort labels are therefore even less comparable. [OpenAI model selection](https://developers.openai.com/api/docs/guides/model-selection) [Anthropic effort guidance](https://platform.claude.com/docs/en/build-with-claude/effort)

## Comparison

| Route | Intended workload and quality tier | Latency | Standard API price per 1M tokens, input / output | Reasoning controls | Context | Coding and agent fit |
| --- | --- | --- | --- | --- | --- | --- |
| **Haiku 5.5 -> GPT-6 Luna** | Haiku is for high-volume, latency-sensitive classification, extraction, routing, real-time experiences, focused coding, and subagents. Luna is OpenAI's most efficient model for focused, high-volume tasks. | Anthropic calls Haiku its fastest current model. OpenAI calls Luna its fastest and most cost-effective GPT-6 option. No shared first-party latency metric supports a direct speed ranking. | Haiku: **$0.10 / $0.50** through 100K prompt tokens, then **$0.50 / $2.50**. Luna: **$0.10 / $0.50** for short context; OpenAI applies higher long-context rates above 272K input tokens. | Haiku: `low`, `medium` default, `high`, `xhigh`, `max`; adaptive thinking, with thinking optionally disabled at `high` or below. Luna: `none`, `low`, `medium` default, `high`, `xhigh`, `max`; also supports standard and pro reasoning modes. | Haiku: 1M. Luna: 1.05M. Both allow 128K maximum output. | Both support tool use and computer use. Haiku is positioned for simple coding, repetitive automation, and cost-efficient subagents. Luna supports OpenAI hosted tools, including shell, patching, skills, computer use, MCP, and tool search. |
| **Sonnet 5.5 -> GPT-6.1 Sol** | Sonnet combines speed and intelligence for well-scoped everyday tasks, bug fixing, polished work products, and long-running implementation. Sol offers near-Astra performance for complex work at lower cost. | Anthropic labels Sonnet "fast" and says it generates output over 30% faster than Sonnet 5. OpenAI positions Sol between Luna and Astra on speed, cost, and intelligence, but publishes no directly comparable latency number. | Sonnet: **$2 / $10**. Sol: **$2 / $10** for short context, with higher rates above 272K input tokens. | Sonnet: `low`, `medium`, `high` default, `xhigh`, `max`; adaptive thinking, or `between_tools` at `high` and below. Sol: `low`, `medium` default, `high`, `xhigh`, `max`, plus standard and pro modes. | Sonnet: 1M. Sol: 1.05M. Both allow 128K maximum output. | Sonnet targets everyday coding, bug fixes, multi-file work, and agents where speed matters. Sol targets complex coding, computer use, and professional work, with Responses API tool calling and multi-agent support. |
| **Opus 5.5 -> GPT-6 Astra** | Opus is for long-running agentic coding and knowledge work. Astra is OpenAI's most capable model for the most demanding reasoning, coding, and professional work. | Anthropic labels Opus "moderate" latency. OpenAI places Astra at the highest-intelligence end rather than the low-latency end. Direct vendor-neutral latency is not documented. | Opus: **$4 / $20**. Astra: **$10 / $50** for short context, with higher rates above 272K input tokens. | Opus: `low`, `medium` default, `high`, `xhigh`, `max`; adaptive thinking is always on. Astra: `low`, `medium`, `high`, `xhigh`, `max`, plus standard and pro modes. | Opus: 1M. Astra: 1.05M. Both allow 128K maximum output. | Both are intended for the hardest coding and long-horizon agent work. Opus is Anthropic's default for most workloads and long-running coding; Astra is OpenAI's flagship for multi-step work across code, browsers, and professional software. |

Sources for the table: [Anthropic models overview](https://platform.claude.com/docs/en/models/overview), [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing), [Anthropic effort controls](https://platform.claude.com/docs/en/build-with-claude/effort), [Claude Haiku 5.5](https://www.anthropic.com/claude/haiku), [Claude Sonnet 5.5 announcement](https://www.anthropic.com/claude-sonnet-5-5), [OpenAI models](https://developers.openai.com/api/docs/models), [OpenAI GPT-6 guide](https://developers.openai.com/api/docs/guides/latest-model), [OpenAI reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), and [GPT-6 Luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna).

## Router recommendation

Use the three pairs above as semantic aliases, but do not hard-code the vendor-neutral labels as capability guarantees. Route by workload first:

- **Fast:** short, bounded, high-volume tasks; extraction; classification; routing; small edits; repetitive computer use; subagents.
- **Balanced:** normal coding, bug fixing, document creation, and tool-heavy tasks with clear scope.
- **Deep:** ambiguous architecture, difficult debugging, consequential analysis, and long-running autonomous work.

Expose effort separately from model tier. Start at each model's documented default, then tune with task-level evals. Pricing alone can mislead because reasoning effort and task length change output-token use, Anthropic and OpenAI use different tokenizers, and both vendors apply special long-context pricing rules. OpenAI also offers processing tiers, while Anthropic offers a premium fast mode for Opus 5.5. Those options affect latency and price without changing the base role mapping.

## Scope and caveats

- Prices are first-party standard API list prices in USD as documented on 2026-10-10. Cache, batch, fast, regional, cloud-provider, and tool-call charges are omitted except where a long-context threshold materially affects comparison.
- "Fastest," "balanced," and "most capable" are each vendor's product positioning, not results from a common test harness.
- No first-party source establishes one-to-one quality parity for these pairs. Anthropic publishes some cross-vendor benchmark results, but those are configuration-specific and do not justify a general equivalence claim.
- Production routing should use representative evals that measure completed-task quality, wall-clock latency, total cost per task, tool-call reliability, and failure recovery.
