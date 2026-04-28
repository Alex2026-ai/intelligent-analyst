/**
 * onLeadCreate.ts
 *
 * Firebase Cloud Function triggered when a new lead is created in Firestore.
 * Sends email notification to enterprise@intelligentanalyst.com
 *
 * Setup:
 * 1. Create SendGrid API key at https://app.sendgrid.com/settings/api_keys
 * 2. Verify sender at https://app.sendgrid.com/settings/sender_auth
 * 3. Store secret: firebase functions:secrets:set SENDGRID_API_KEY
 */

import { onDocumentCreated } from "firebase-functions/v2/firestore";
import { logger } from "firebase-functions";
import * as admin from "firebase-admin";
import sgMail from "@sendgrid/mail";

// Feature flag - set to true when SendGrid is configured
const EMAIL_ENABLED = false;

// Email configuration - explicit addresses (not placeholders)
const TO_EMAIL = "enterprise@intelligentanalyst.com";
const FROM_EMAIL = "noreply@intelligentanalyst.com";

interface LeadData {
  firstName: string;
  lastName: string;
  email: string;
  company: string;
  title?: string;
  useCase: string;
  message?: string;
  source: string;
  status: string;
  createdAt: admin.firestore.Timestamp;
  userAgent?: string;
  referrer?: string;
}

/**
 * Formats lead data into an HTML email body
 */
function formatEmailHtml(leadId: string, data: LeadData): string {
  const createdAt = data.createdAt?.toDate?.()
    ? data.createdAt.toDate().toISOString()
    : new Date().toISOString();

  return `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }
    .container { max-width: 600px; margin: 0 auto; background: #1e293b; border: 1px solid #334155; padding: 24px; }
    .header { border-bottom: 1px solid #334155; padding-bottom: 16px; margin-bottom: 16px; }
    .lead-id { font-family: monospace; color: #22d3ee; font-size: 14px; }
    .field { margin-bottom: 12px; }
    .label { color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }
    .value { color: #f1f5f9; font-size: 16px; }
    .message { background: #0f172a; padding: 16px; border: 1px solid #334155; margin-top: 16px; }
    .footer { margin-top: 24px; padding-top: 16px; border-top: 1px solid #334155; font-size: 12px; color: #64748b; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="lead-id">LEAD ID: ${leadId}</div>
      <div style="color: #94a3b8; font-size: 12px; margin-top: 4px;">Created: ${createdAt}</div>
    </div>

    <div class="field">
      <div class="label">Name</div>
      <div class="value">${escapeHtml(data.firstName)} ${escapeHtml(data.lastName)}</div>
    </div>

    <div class="field">
      <div class="label">Email</div>
      <div class="value"><a href="mailto:${escapeHtml(data.email)}" style="color: #22d3ee;">${escapeHtml(data.email)}</a></div>
    </div>

    <div class="field">
      <div class="label">Company</div>
      <div class="value">${escapeHtml(data.company)}</div>
    </div>

    ${data.title ? `
    <div class="field">
      <div class="label">Title</div>
      <div class="value">${escapeHtml(data.title)}</div>
    </div>
    ` : ""}

    <div class="field">
      <div class="label">Use Case</div>
      <div class="value">${escapeHtml(data.useCase)}</div>
    </div>

    <div class="field">
      <div class="label">Source</div>
      <div class="value">${escapeHtml(data.source)}</div>
    </div>

    ${data.message ? `
    <div class="message">
      <div class="label" style="margin-bottom: 8px;">Message</div>
      <div style="white-space: pre-wrap;">${escapeHtml(data.message)}</div>
    </div>
    ` : ""}

    <div class="footer">
      <div>User Agent: ${escapeHtml(data.userAgent || "N/A")}</div>
      <div>Referrer: ${escapeHtml(data.referrer || "Direct")}</div>
    </div>
  </div>
</body>
</html>
  `.trim();
}

/**
 * Escapes HTML special characters
 */
function escapeHtml(text: string): string {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Cloud Function: onLeadCreate
 * Triggered when a new document is created in the 'leads' collection
 *
 * Uses Firebase Functions v2 with Secret Manager for API key
 */
export const onLeadCreate = onDocumentCreated(
  {
    document: "leads/{leadId}",
    region: "us-central1",
  },
  async (event) => {
    const snapshot = event.data;
    if (!snapshot) {
      logger.warn("No data in event");
      return;
    }

    const leadId = event.params.leadId;
    const data = snapshot.data() as LeadData;

    logger.info(`New lead created: ${leadId}`, {
      company: data.company,
      source: data.source,
      email: data.email,
      timestamp: new Date().toISOString(),
    });

    // Feature flag check - email notifications intentionally disabled
    if (!EMAIL_ENABLED) {
      logger.info("Email notifications disabled by configuration.", {
        leadId,
        source: data.source,
        company: data.company,
      });
      return;
    }

    // Check if SendGrid is configured via environment variable
    // Set via: firebase functions:secrets:set SENDGRID_API_KEY
    const apiKey = process.env.SENDGRID_API_KEY;
    if (!apiKey) {
      logger.warn("SendGrid API key not configured.", { leadId });
      return;
    }

    // Initialize SendGrid with the API key
    sgMail.setApiKey(apiKey);

    const subject = `[IA] New Lead: ${data.company} — ${data.source}`;

    const msg = {
      to: TO_EMAIL,
      from: FROM_EMAIL,
      subject,
      html: formatEmailHtml(leadId, data),
      text: `
New Lead Received

Lead ID: ${leadId}
Name: ${data.firstName} ${data.lastName}
Email: ${data.email}
Company: ${data.company}
Title: ${data.title || "N/A"}
Use Case: ${data.useCase}
Source: ${data.source}
Message: ${data.message || "N/A"}
      `.trim(),
    };

    try {
      await sgMail.send(msg);
      logger.info(`Email sent for lead: ${leadId}`);

      // Update lead document to mark notification sent
      await snapshot.ref.update({
        notificationSent: true,
        notificationSentAt: admin.firestore.FieldValue.serverTimestamp(),
      });
    } catch (error) {
      logger.error(`Failed to send email for lead: ${leadId}`, error);
      // Don't throw - we don't want to retry failed emails indefinitely
    }
  }
);
