# AutoMessenger

SMS agent ("Walter") for business funding outreach. A free local LLM (Ollama,
llama3.1:8b) runs on this computer and answers merchant texts; AWS bridges it to
Salesforce, where Text Torrent actually sends and receives the SMS.

## Architecture

```
merchant texts in
      |
Text Torrent (Salesforce)
      |  record-triggered Flow, HTTP POST + X-Auth-Token
      v
API Gateway -> inbound Lambda -> SQS automessenger-inbound
                                        |
                                        |  long-polled by this computer
                                        v
                            local agent server (server/)
                    Ollama (llama3.1:8b) + persona prompt +
                    deterministic guardrails + DynamoDB history
                                        |
                                        v
              SQS automessenger-outbound -> outbound Lambda
                                        |
                                        |  Salesforce REST (client credentials)
                                        v
                     Text Torrent record/flow -> SMS goes out
```

Escalations (call requests, compliance flags, frustrated or hesitant merchants,
sent-statements) never get an auto-reply; they publish to the SNS topic
`automessenger-escalations` so a human takes over.

## What runs where

| Piece | Location | Purpose |
| --- | --- | --- |
| `prompts/walter_system.txt` | local | The full Walter persona + classification rules |
| `server/` | this computer | Poll SQS, run Ollama, guardrails, save history, queue replies |
| `aws/template.yaml` | AWS us-east-2, stack `automessenger` | API Gateway, 2 Lambdas, 2 SQS queues + DLQs, DynamoDB, SNS, worker IAM user |
| `salesforce/SETUP.md` | Salesforce | Text Torrent wiring instructions (the remaining manual step) |

## Running it

```powershell
.\run.ps1          # starts Ollama if needed, then the worker loop
```

Local test without touching AWS or Salesforce (talk to Walter in the console):

```powershell
python -m server.main --chat
```

Guardrail unit tests: `python -m server.tests.test_guardrails`

## Configuration

`server/.env` is already filled with the deployed stack's queue URLs, table,
topic, and scoped IAM credentials. **You must set `UPLOAD_LINK`** to your real
secure statement-upload page before going live — until then the agent has no
link to give merchants.

The webhook secret Salesforce must send is in `aws/deploy-params.txt`
(gitignored, keep it private). Webhook URL:
`https://01o1xporok.execute-api.us-east-2.amazonaws.com/inbound`

## Remaining setup (Salesforce side)

Follow [salesforce/SETUP.md](salesforce/SETUP.md):
1. Inbound: record-triggered Flow on Text Torrent's incoming SMS object that
   POSTs to the webhook URL with the `X-Auth-Token` header.
2. Outbound: a Connected App with the client-credentials flow, then redeploy the
   stack parameters with your consumer key/secret and Text Torrent's outbound
   object or send-flow name.
3. Subscribe your phone/email to escalations:
   `aws sns subscribe --topic-arn arn:aws:sns:us-east-2:870730509769:automessenger-escalations --protocol email --notification-endpoint you@example.com`

## Safety and compliance notes

- Hard opt-out keywords (STOP, UNSUBSCRIBE, etc.) are honored in code before the
  model ever sees the text, and stopped numbers are never messaged again.
- Guardrails deterministically block numbers/rates/amounts, links other than the
  upload link, emojis, banned words, and dashes; a reply that cannot be cleaned
  is escalated to a human instead of sent.
- Automated/AI-assisted texting is regulated (TCPA consent rules; some states
  require disclosing that a bot is texting). Have your compliance counsel review
  the persona and your consent records before going live.
- The Lambda logs (`/aws/lambda/automessenger-inbound`, `-outbound`) and the
  local worker console are the two places to look when a message goes missing;
  undeliverable messages park in the `-dlq` queues.
