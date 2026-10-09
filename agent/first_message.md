# First message (greeting)

VaniAgent's **Fixed greeting** field allows **150 characters** and is pre-recorded (no variables).
Every version below fits, and each discloses that the caller is talking to an AI and that the call
is recorded (needed before personal data is collected; DPDP Act 2023 notice principle [Likely]:
confirm wording with a lawyer). Use the Fixed greeting only; leave Variable greeting empty
(inbound callers have no {contact_name}).

## Recommended (English, asks the routing question, 132 chars)

> Namaste! You've reached Aangan Studio's AI assistant. This call is recorded. Are you calling about a new project or an existing one?

## Bilingual invite (125 chars)

> Namaste! Aangan Studio's AI assistant here, and this call is recorded. Hindi ya English, jo aapko theek lage. How can I help?

## Hindi (114 chars)

> नमस्ते! आंगन स्टूडियो की AI असिस्टेंट बोल रही हूँ, यह कॉल रिकॉर्ड हो रही है। नया प्रोजेक्ट है या चल रहा प्रोजेक्ट?

Notes
- The bot switches to Hindi the moment the caller speaks Hindi (prompt: LANGUAGE), so the English
  greeting works for Hindi callers too.
- Ends with the routing question (new vs existing), so the first answer tells the bot whether to
  qualify or escalate.
- No price, no promise, no names.
