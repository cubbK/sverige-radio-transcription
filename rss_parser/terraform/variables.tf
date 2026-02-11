variable "project_id" {
  description = "Google Cloud project ID"
  type        = string
  default     = "dan-learning-0929"
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "europe-west1"
}

variable "bucket_name" {
  description = "GCS bucket name for feeds and assets"
  type        = string
  default     = "sverige-radio-transcription"
}

variable "cloud_tasks_queue_name" {
  description = "Cloud Tasks queue name"
  type        = string
  default     = "podcast-processing"
}

variable "schedule_cron" {
  description = "Cron expression for how often the RSS parser runs"
  type        = string
  default     = "0 */6 * * *" # Every 6 hours
}
