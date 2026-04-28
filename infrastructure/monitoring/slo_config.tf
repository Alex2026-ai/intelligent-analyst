# SLO definitions from observability-slo-plan.md

resource "google_monitoring_slo" "availability" {
  service      = google_monitoring_custom_service.ia_api.service_id
  display_name = "IA API Availability"
  goal         = 0.999 # 99.9%

  rolling_period_days = 30

  request_based_sli {
    good_total_ratio {
      good_service_filter = "metric.type=\"custom.googleapis.com/http/request_count\" AND metric.labels.status_class!=\"5xx\""
      total_service_filter = "metric.type=\"custom.googleapis.com/http/request_count\""
    }
  }
}

resource "google_monitoring_slo" "latency_p95" {
  service      = google_monitoring_custom_service.ia_api.service_id
  display_name = "IA API Latency (p95 < 3s)"
  goal         = 0.95

  rolling_period_days = 30

  request_based_sli {
    distribution_cut {
      distribution_filter = "metric.type=\"custom.googleapis.com/http/request_duration_ms\""
      range {
        max = 3000
      }
    }
  }
}

resource "google_monitoring_slo" "export_success" {
  service      = google_monitoring_custom_service.ia_api.service_id
  display_name = "IA Export Success Rate"
  goal         = 0.99 # 99%

  rolling_period_days = 30

  request_based_sli {
    good_total_ratio {
      good_service_filter  = "metric.type=\"custom.googleapis.com/export/count\" AND metric.labels.status=\"complete\""
      total_service_filter = "metric.type=\"custom.googleapis.com/export/count\""
    }
  }
}

resource "google_monitoring_custom_service" "ia_api" {
  display_name = "Intelligent Analyst API"
  service_id   = "ia-api"
}
