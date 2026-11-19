// Point the committed workflow at the hosted API and give it the service token (no secrets in git).
import { readFileSync, writeFileSync } from "node:fs";
const [src, dst] = process.argv.slice(2);
const wf = JSON.parse(readFileSync(src, "utf8"));
const prep = wf.nodes.find((n) => n.name.startsWith("E-Mail vorbereiten"));
for (const a of prep.parameters.assignments.assignments) {
  if (a.name === "api_url") a.value = process.env.INTAKE_API_URL;
  if (a.name === "api_token") a.value = process.env.INTAKE_SERVICE_TOKEN || "";
}
writeFileSync(dst, JSON.stringify(wf));
console.log("workflow configured for", process.env.INTAKE_API_URL);
