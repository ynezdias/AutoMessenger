# AutoMessenger — Salesforce integration handoff

This is everything needed to connect Salesforce/Text Torrent to the SMS agent.
The AWS side is deployed and live; the local agent machine polls it continuously.

## 1. Inbound: send merchant texts TO the agent

When a merchant texts in, POST the message here:

```
POST https://01o1xporok.execute-api.us-east-2.amazonaws.com/inbound
Content-Type: application/json
X-Auth-Token: <webhook secret — get this privately from Ynez, it is in
               aws/deploy-params.txt on the agent machine. Never commit it.>
```

Body:

```json
{
  "phone": "+15551234567",        // required, E.164 preferred
  "message": "the text they sent", // required
  "merchantFirst": "Sam",          // optional but strongly recommended
  "company": "Acme LLC",           // optional
  "recordId": "a0X..."             // optional Salesforce record id, echoed back
}
```

Responses: `200 {"queued": true}` on success, `401` bad/missing token,
`400` missing phone or message.

Recommended Salesforce implementation: a record-triggered Flow (or Apex trigger)
on Text Torrent's inbound SMS object that makes this HTTP callout on record
create. Details and an example mapping: [salesforce/SETUP.md](salesforce/SETUP.md).

## 2. Outbound: deliver the agent's replies FROM AWS to Text Torrent

Replies land on SQS queue `automessenger-outbound` (us-east-2), where Lambda
`automessenger-outbound` picks them up and calls the Salesforce REST API. Each
message is `{"phone": "...", "message": "...", "recordId": "..."}`.

That Lambda needs Salesforce credentials before it can deliver. Two options,
set via CloudFormation parameters on stack `automessenger` (exact commands in
[salesforce/SETUP.md](salesforce/SETUP.md)):

- **sobject mode**: it creates a record on a Text Torrent outbound-SMS object
  (`SfSObject` + `SfFieldMap` parameters) and Text Torrent's automation sends it.
- **flow mode**: it invokes an autolaunched Flow (`SfFlowApiName`) with inputs
  `phone`, `message`, `recordId`; the Flow calls Text Torrent's send action.

Auth: a Connected App with the client-credentials flow (`SfTokenUrl`,
`SfClientId`, `SfClientSecret`), or a refresh token (`SfGrantType=refresh_token`,
`SfRefreshToken`).

Until this is configured the Lambda fails on purpose with "Salesforce is not
configured yet" and undelivered replies park in `automessenger-outbound-dlq`
after 5 attempts — purge that queue after testing.

## 3. Quick test

```powershell
$h = @{"X-Auth-Token" = "<secret>"}
$b = '{"phone": "+15550001111", "message": "how much can I get?", "merchantFirst": "Test"}'
Invoke-RestMethod -Method Post -Uri "https://01o1xporok.execute-api.us-east-2.amazonaws.com/inbound" -Headers $h -ContentType "application/json" -Body $b
```

Within a minute the agent's reply appears on the outbound queue (visible in the
Lambda's CloudWatch logs `/aws/lambda/automessenger-outbound`).

## 4. Monitoring

- `/aws/lambda/automessenger-inbound` — webhook receipts
- `/aws/lambda/automessenger-outbound` — delivery attempts to Salesforce
- SNS topic `automessenger-escalations` (us-east-2) — human-handoff alerts;
  subscribe your email/phone to it
- Dead letter queues `automessenger-inbound-dlq` / `automessenger-outbound-dlq`
