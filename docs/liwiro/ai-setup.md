# AI Setup and Usage

Configure the AI providers used by Verse from **AI Setup** (`/ai-setup`). A Liwiro super admin can save credentials, choose models, change the shared usage level, and test connections. Other signed-in users can view configuration status.

## Set up a provider

1. Open AI Setup and choose the default provider for new conversations.
2. Enter an API key in that provider's card. A saved key is never returned to the browser; leave its field blank to keep it.
3. Review the model ID. **Use suggested model** fills in the current Liwiro recommendation; you can enter another model available to your account.
4. Leave **AI usage level** on **Medium** for a balanced starting point.
5. Choose **Test connection** to test the draft without saving, or **Save AI Configuration** to save and then test every configured provider.

Tests make real generation requests and can incur provider usage. Saving and testing are separate: a failed connection test does not undo the saved configuration. To remove a key, choose **Remove saved key on save**, then save.

## Models

Defaults verified against provider documentation on 2026-09-30:

| Provider | Default model | API |
| --- | --- | --- |
| OpenAI | `gpt-6-luna` | Responses |
| Google Gemini | `gemini-3.8-flash` | generateContent |
| Anthropic Claude | `claude-sonnet-5-5` | Messages |

These defaults favor routine work and cost efficiency. Existing explicit model choices are preserved. Model availability depends on your provider account. A successful connection test confirms that the selected key and model can answer a small request; it does not measure quality on your workload.

## Choose a usage level

| Level | Use it for | Tradeoff |
| --- | --- | --- |
| Low | Quick questions, summaries, small edits | Favors speed and lower token use |
| Medium (default) | Service design, debugging, everyday analysis | Balances reasoning and usage |
| High | Difficult problems and detailed reviews | Allows more reasoning; may cost more and take longer |

The setting is shared across Verse provider requests, including tests. Supported OpenAI reasoning models receive `reasoning.effort`; the recommended Gemini model receives `thinkingConfig.thinkingLevel`; supported Claude models receive `output_config.effort`.

Liwiro reserves at least 4,096, 8,192, or 16,384 output tokens at Low, Medium, or High respectively on supported models. Larger task-specific limits are preserved. These are maximum response allowances, not a promise that every request will consume that amount. Reasoning may use part of the allowance. Older or custom models may not accept effort controls; Liwiro sends them only for recognized compatible model families.

Usage level is not a spending cap. Input length, model pricing, repeated requests, specialist collaboration, and proactive reviews also affect usage. Configure collaboration and specialist activity separately in **Settings → Verse**.

## Environment configuration

AI Setup persists settings in `liwiro/backend/.env.local`. You can also configure the backend through environment files:

```env
AI_PROVIDER=openai
AI_USAGE_LEVEL=medium
OPENAI_MODEL=gpt-6-luna
GOOGLE_MODEL=gemini-3.8-flash
ANTHROPIC_MODEL=claude-sonnet-5-5
```

Set `OPENAI_API_KEY`, `GOOGLE_API_KEY`, and/or `ANTHROPIC_API_KEY` locally. Keep real keys out of source control, service examples, and frontend environment variables. Changes saved through AI Setup refresh the provider runtime. A conversation retains its chosen provider and model; use the chat provider controls when changing an existing thread.

## Troubleshooting

- **Setup required:** add a key for the default provider or choose a configured provider.
- **401:** replace the rejected API key.
- **403:** check account permissions, model access, and any regional restrictions.
- **429:** check provider quota and rate limits; repeated retries may not resolve exhausted quota.
- **Timeout or network error:** check outbound connectivity from the Liwiro server.
- **Truncated or empty response:** narrow the task or increase the usage level. Retrying may consume additional tokens.
- **Unsupported parameter or model:** use the suggested model, or verify the custom model's capabilities with the provider.

## API reference

- `GET /platform/ai/config`: authenticated status, model IDs, recommendations, and usage level; no keys.
- `PUT /platform/ai/config`: super-admin update with `defaultProvider`, `usageLevel`, and/or a `providers` object.
- `POST /platform/ai/config/test`: super-admin probe with `provider` and optional draft `model`, `apiKey`, and `usageLevel`; does not save the draft.

## Provider sources

- [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [Gemini 3.8 Flash migration guidance](https://ai.google.dev/gemini-api/docs/latest-model)
- [Claude Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)
- [Claude effort control](https://platform.claude.com/docs/en/build-with-claude/effort)
