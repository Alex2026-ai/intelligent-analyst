# Alerting policies for Intelligent Analyst — from observability-slo-plan.md
# Apply with: terraform apply -target=module.monitoring

resource "google_monitoring_alert_policy" "high_error_rate" {
  display_name = "IA - High Error Rate"
  combiner     = "OR"

  conditions {
    display_name = "Error rate > 1% for 5 minutes"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/http/error_count\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.01
      duration        = "300s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = [var.pager_channel_id]
  severity              = "CRITICAL" # SEV-2
}

resource "google_monitoring_alert_policy" "high_latency" {
  display_name = "IA - High Latency (p95 > 3s)"
  combiner     = "OR"

  conditions {
    display_name = "p95 latency > 3s for 5 minutes"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/resolution/duration_ms\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = 3000
      duration        = "300s"
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
      }
    }
  }

  notification_channels = [var.slack_channel_id]
  severity              = "WARNING" # SEV-3
}

resource "google_monitoring_alert_policy" "circuit_breaker_open" {
  display_name = "IA - Circuit Breaker Opened"
  combiner     = "OR"

  conditions {
    display_name = "Circuit breaker transition to OPEN"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/circuit_breaker/state_change\" AND metric.labels.to_state=\"open\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_COUNT"
      }
    }
  }

  notification_channels = [var.slack_channel_id]
  severity              = "WARNING" # SEV-3
}

resource "google_monitoring_alert_policy" "evidence_integrity_violation" {
  display_name = "IA - Evidence Integrity Violation"
  combiner     = "OR"

  conditions {
    display_name = "Evidence chain hash verification failure"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/evidence/integrity_check\" AND metric.labels.result=\"fail\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_COUNT"
      }
    }
  }

  notification_channels = [var.pager_channel_id]
  severity              = "CRITICAL" # SEV-2
}

resource "google_monitoring_alert_policy" "review_queue_depth" {
  display_name = "IA - Review Queue Depth > 100"
  combiner     = "OR"

  conditions {
    display_name = "Pending review cases > 100"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/review/queue_depth\""
      comparison      = "COMPARISON_GT"
      threshold_value = 100
      duration        = "300s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = [var.slack_channel_id]
  severity              = "WARNING" # SEV-3
}

resource "google_monitoring_alert_policy" "export_failure_spike" {
  display_name = "IA - Export Failure Rate > 10%"
  combiner     = "OR"

  conditions {
    display_name = "Export failure rate > 10% for 10 minutes"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/export/error_count\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.10
      duration        = "600s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = [var.slack_channel_id]
  severity              = "WARNING" # SEV-3
}

resource "google_monitoring_alert_policy" "startup_failure" {
  display_name = "IA - Startup Probe Failure"
  combiner     = "OR"

  conditions {
    display_name = "Startup probe fails 3 consecutive times"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_LT"
      threshold_value = 1
      duration        = "180s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_FRACTION_TRUE"
      }
    }
  }

  notification_channels = [var.pager_channel_id]
  severity              = "CRITICAL" # SEV-2
}

variable "pager_channel_id" {
  description = "Notification channel ID for paging on-call"
  type        = string
}

variable "slack_channel_id" {
  description = "Notification channel ID for Slack alerts"
  type        = string
}
