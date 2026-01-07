# AI Updates Monitor

An AWS-based system that monitors AI/ML news, updates, and releases from 55 curated sources and sends email notifications when new content is detected.

## Features

- **55 Sources** across major AI/ML organizations:
  - OpenAI, Anthropic, Google/DeepMind, Microsoft, Meta, AWS, Apple, NVIDIA
  - xAI, Mistral, Cohere, Hugging Face, LangChain, LlamaIndex, and more
  
- **5 Adapter Types**:
  - RSS/Atom feeds (most reliable)
  - GitHub Releases
  - HTML article lists
  - HTML changelogs

- **Smart Deduplication**: Fingerprint-based change detection ensures no duplicate alerts

- **Cost Efficient**: 
  - No VPC (avoids NAT costs)
  - On-demand DynamoDB billing
  - Minimal CloudWatch logging (7-day retention)

## Architecture

```
EventBridge (every 2 hours)
         │
         ▼
    Lambda Function (Python 3.12, 512MB, 120s)
    ┌─────────────────────────────────────┐
    │  1. Load sources.yaml               │
    │  2. Fetch sources (10 concurrent)   │
    │  3. Parse with adapters             │
    │  4. Compute fingerprints            │
    │  5. Compare with DynamoDB state     │
    │  6. Send digest via SNS if changes  │
    └─────────────────────────────────────┘
         │                    │
         ▼                    ▼
    DynamoDB              SNS Topic
   (state)              (email digest)
```

## Prerequisites

- AWS Account with appropriate permissions
- AWS CLI configured (`aws configure`)
- Node.js 18+ (for CDK CLI)
- Python 3.12+
- Docker (for Lambda bundling)

## Quick Start

### 1. Create Python virtual environment

```bash
cd cdk
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Bootstrap CDK (first time only)

```bash
npx cdk bootstrap
```

### 3. Deploy

```bash
npx cdk deploy --parameters NotificationEmail=your-email@example.com
```

**Important**: After deployment, check your email and confirm the SNS subscription!

### 4. Test manually

```bash
# Invoke Lambda function manually
aws lambda invoke \
  --function-name ai-updates-monitor \
  --payload '{}' \
  response.json

# Check the response
cat response.json
```

## Project Structure

```
news_updates/
├── cdk/
│   ├── app.py                    # CDK app entry point
│   ├── cdk.json                  # CDK configuration
│   ├── requirements.txt          # CDK dependencies
│   └── stacks/
│       └── ai_updates_stack.py   # Infrastructure definition
├── lambda/
│   ├── handler.py                # Lambda entry point
│   ├── requirements.txt          # Lambda dependencies
│   ├── adapters/
│   │   ├── rss.py                # RSS feed adapter
│   │   ├── atom.py               # Atom feed adapter
│   │   ├── github_releases.py    # GitHub releases adapter
│   │   ├── html_articles.py      # HTML articles adapter
│   │   └── html_changelog.py     # HTML changelog adapter
│   ├── services/
│   │   ├── fetcher.py            # HTTP client with caching
│   │   ├── fingerprint.py        # Hash computation
│   │   ├── state.py              # DynamoDB operations
│   │   └── notifier.py           # SNS notifications
│   └── config/
│       └── sources.yaml          # Source definitions
├── ai-updates-monitor-aws.md     # Design document
├── source_list.txt               # Original source list
└── README.md                     # This file
```

## Configuration

### Schedule

The monitor runs every **2 hours** by default. To change:

Edit `cdk/stacks/ai_updates_stack.py`:
```python
schedule=events.Schedule.rate(Duration.hours(2))  # Change to desired interval
```

### Adding Sources

Edit `lambda/config/sources.yaml`:

```yaml
- id: unique_source_id
  org: Organization Name
  name: Human-readable Name
  adapter: rss | atom | github_releases_atom | html_articles | html_changelog
  url: https://example.com/feed
  max_items: 10
  selectors:  # Required for html_articles and html_changelog
    container: "main"
    item: "article"
    title: "h2"
    link: "a"
    date: "time"
```

### Adapter Types

| Adapter | Use Case | Required Selectors |
|---------|----------|-------------------|
| `rss` | RSS 2.0 feeds | None |
| `atom` | Atom feeds | None |
| `github_releases_atom` | GitHub releases | None |
| `html_articles` | Blog/news pages | container, item, title |
| `html_changelog` | Changelog pages | container, entry, version |

## Operations

### View Logs

```bash
aws logs tail /aws/lambda/ai-updates-monitor --follow
```

### Check State Table

```bash
aws dynamodb scan --table-name ai_updates_state --max-items 10
```

### Force Re-scan (clear state)

```bash
# Delete all items to force re-scan of all sources
aws dynamodb scan --table-name ai_updates_state --projection-expression "source_id" | \
  jq -r '.Items[].source_id.S' | \
  xargs -I {} aws dynamodb delete-item --table-name ai_updates_state --key '{"source_id":{"S":"{}"}}'
```

### Update Sources Only

After editing `sources.yaml`:

```bash
cd cdk
npx cdk deploy
```

## Costs (Estimated)

| Resource | Estimated Monthly Cost |
|----------|----------------------|
| Lambda | ~$0.10 (360 invocations/month × 120s) |
| DynamoDB | ~$0.25 (on-demand, 55 items) |
| SNS | Free tier (1000 emails) |
| CloudWatch | ~$0.50 (minimal logs, 7-day retention) |
| **Total** | **< $1/month** |

## Troubleshooting

### No emails received

1. Check SNS subscription is confirmed
2. Check spam folder
3. Verify Lambda executed: `aws logs tail /aws/lambda/ai-updates-monitor`

### Lambda timeout

Increase timeout in `cdk/stacks/ai_updates_stack.py`:
```python
timeout=Duration.seconds(180)  # Increase from 120
```

### HTML adapter not extracting items

1. Website may have changed structure
2. Update selectors in `sources.yaml`
3. Test locally with: `python lambda/handler.py`

### Rate limited by source

The fetcher uses:
- Polite User-Agent
- 10 concurrent connections max
- 20-second timeout
- Conditional GET (ETag/Last-Modified)

If still rate limited, reduce `concurrency` in `lambda/handler.py`.

## Local Development

### Test locally

```bash
cd lambda
pip install -r requirements.txt

# Set environment variables
export STATE_TABLE_NAME=ai_updates_state
export SNS_TOPIC_ARN=arn:aws:sns:us-east-1:123456789:ai-updates-notifications
export LOG_LEVEL=DEBUG

# Run
python handler.py
```

### Test single adapter

```python
from adapters import get_adapter
import requests

adapter = get_adapter("rss")
response = requests.get("https://developers.openai.com/changelog/rss.xml")
items = adapter.extract(response.text, {"id": "test", "url": response.url})
print(items)
```

## Cleanup

```bash
cd cdk
npx cdk destroy
```

Note: DynamoDB table has `RETAIN` policy and won't be deleted automatically. Delete manually if needed:
```bash
aws dynamodb delete-table --table-name ai_updates_state
```

## License

MIT
