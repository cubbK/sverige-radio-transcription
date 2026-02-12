output "rss_parser_function_url" {
  description = "URL of the RSS parser Cloud Function"
  value       = google_cloudfunctions2_function.rss_parser.url
}

output "episode_processor_service_url" {
  description = "URL of the episode processor Cloud Run service"
  value       = google_cloud_run_v2_service.episode_processor.uri
}

output "cloud_tasks_queue" {
  description = "Cloud Tasks queue path"
  value       = google_cloud_tasks_queue.podcast_processing.id
}

output "feeds_bucket" {
  description = "GCS bucket name"
  value       = google_storage_bucket.feeds.name
}

output "rss_parser_service_account" {
  description = "RSS parser service account email"
  value       = google_service_account.rss_parser.email
}
