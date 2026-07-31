# Salesforce + Text Torrent wiring

Two connections are needed: **inbound** (Text Torrent message → AWS webhook) and
**outbound** (AWS → Salesforce so Text Torrent sends the reply).

## 1. Find your Text Torrent objects

In Setup → Object Manager, search "Text Torrent" (or the package namespace shown in
Setup → Installed Packages). Note the API names of:

- the **incoming SMS object/record** Text Torrent creates when a merchant texts in
- the **outgoing SMS object or send action** Text Torrent watches to deliver a text

Text Torrent installs differ, so these exact API names are what you plug into the
config below. Their support/docs page lists them if the Object Manager is unclear.

## 2. Inbound: record-triggered Flow → AWS webhook

1. Setup → Flows → New Flow → **Record-Triggered Flow** on the Text Torrent
   *incoming* SMS object, trigger = "when a record is created", optimized for Actions.
2. Add an **HTTP Callout** action (Setup → Named Credentials first):
   - Named Credential URL: the `WebhookUrl` output from the CloudFormation stack
     (e.g. `https://xxxx.execute-api.us-east-2.amazonaws.com/inbound`)
   - Method: POST, header `X-Auth-Token` = the webhook secret you deployed with
     (stored in `aws/deploy-params.txt` after deployment)
   - JSON body mapped from the record:
     ```json
     {
       "phone": "{!$Record.FromPhone__c}",
       "message": "{!$Record.Body__c}",
       "merchantFirst": "{!$Record.Contact__r.FirstName}",
       "company": "{!$Record.Contact__r.Account.Name}",
       "recordId": "{!$Record.Id}"
     }
     ```
     (swap the field API names for your Text Torrent install's actual fields)
3. Activate the flow.

If you prefer Apex, an equivalent trigger + queueable callout works the same way:
POST that JSON to the webhook URL with the `X-Auth-Token` header.

## 3. Outbound: Connected App for the sender Lambda

1. Setup → App Manager → **New Connected App**:
   - Enable OAuth Settings, callback URL can be `https://login.salesforce.com`
   - OAuth scopes: "Manage user data via APIs (api)"
   - Enable **Client Credentials Flow** and assign a run-as integration user that
     has permission to create Text Torrent outbound records / run the send flow.
2. Copy the **Consumer Key** and **Consumer Secret**.
3. Update the stack so the sender Lambda can log in (one command, run from `aws/`):
   ```powershell
   aws cloudformation deploy --stack-name automessenger --template-file packaged.yaml `
     --capabilities CAPABILITY_NAMED_IAM `
     --parameter-overrides `
       SfTokenUrl=https://YOURDOMAIN.my.salesforce.com/services/oauth2/token `
       SfClientId=YOUR_CONSUMER_KEY `
       SfClientSecret=YOUR_CONSUMER_SECRET `
       SfMode=sobject `
       SfSObject=TextTorrent_Outbound_SMS_Object_API_Name `
       SfFieldMap='{"Phone_Field__c": "{phone}", "Message_Field__c": "{message}"}'
   ```
   - `SfMode=sobject`: the Lambda creates a record on `SfSObject` with
     `SfFieldMap` (placeholders `{phone}`, `{message}`, `{recordId}`), and Text
     Torrent's own automation sends it.
   - `SfMode=flow`: the Lambda invokes an autolaunched flow
     (`SfFlowApiName=Your_Flow_API_Name`) with inputs `phone`, `message`,
     `recordId`; build that flow around Text Torrent's send action.

## 4. Test end to end

1. Text your Text Torrent number from a real phone.
2. Watch the local server console: it should log the inbound, the model's action,
   and the queued outbound.
3. The reply should arrive back on the phone via Text Torrent.
4. CloudWatch → Log groups `/aws/lambda/automessenger-inbound` and
   `/aws/lambda/automessenger-outbound` show the AWS side of each hop.
