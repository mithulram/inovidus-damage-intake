// Webhook credential (header token) from a secret – never stored in git.
import { writeFileSync } from "node:fs";
const token = process.env.INTAKE_WEBHOOK_TOKEN;
if (!token) { console.error("INTAKE_WEBHOOK_TOKEN missing – refusing to start an open webhook"); process.exit(1); }
writeFileSync(process.argv[2], JSON.stringify([{ id: "intakeWebhookTk1", name: "Intake Webhook Token", type: "httpHeaderAuth",
  data: { name: "X-Webhook-Token", value: token } }]));
