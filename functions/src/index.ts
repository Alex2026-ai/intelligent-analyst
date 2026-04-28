/**
 * Firebase Cloud Functions for Intelligent Analyst
 *
 * Entry point that exports all cloud functions.
 */

import * as admin from "firebase-admin";

// Initialize Firebase Admin SDK
admin.initializeApp();

// Export cloud functions
export { onLeadCreate } from "./onLeadCreate";
