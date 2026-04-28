# Dashboard definitions from observability-slo-plan.md

resource "google_monitoring_dashboard" "operations" {
  dashboard_json = jsonencode({
    displayName = "IA - Operations"
    gridLayout = {
      widgets = [
        {
          title = "Request Rate by Endpoint"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/http/request_count\""
                  aggregation = {
                    alignmentPeriod  = "60s"
                    perSeriesAligner = "ALIGN_RATE"
                    groupByFields    = ["metric.labels.endpoint"]
                  }
                }
              }
            }]
          }
        },
        {
          title = "Error Rate by Code"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/http/error_count\""
                  aggregation = {
                    alignmentPeriod  = "60s"
                    perSeriesAligner = "ALIGN_RATE"
                    groupByFields    = ["metric.labels.error_code"]
                  }
                }
              }
            }]
          }
        },
        {
          title = "Latency Percentiles"
          xyChart = {
            dataSets = [
              {
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"custom.googleapis.com/http/request_duration_ms\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_PERCENTILE_50"
                    }
                  }
                }
              },
              {
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"custom.googleapis.com/http/request_duration_ms\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_PERCENTILE_95"
                    }
                  }
                }
              },
              {
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"custom.googleapis.com/http/request_duration_ms\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_PERCENTILE_99"
                    }
                  }
                }
              }
            ]
          }
        },
        {
          title = "Circuit Breaker States"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/circuit_breaker/state_change\""
                  aggregation = {
                    alignmentPeriod  = "60s"
                    perSeriesAligner = "ALIGN_COUNT"
                    groupByFields    = ["metric.labels.breaker", "metric.labels.to_state"]
                  }
                }
              }
            }]
          }
        }
      ]
    }
  })
}
