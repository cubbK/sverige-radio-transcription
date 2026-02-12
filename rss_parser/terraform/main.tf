terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ------------------------------------------------------------------
# Enable required APIs
# ------------------------------------------------------------------
resource "google_project_service" "apis" {
  for_each = toset([
    "cloudtasks.googleapis.com",
    "cloudfunctions.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudscheduler.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "artifactregistry.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# ------------------------------------------------------------------
# GCS bucket for feeds JSON and MP3 storage
# ------------------------------------------------------------------
resource "google_storage_bucket" "feeds" {
  name          = var.bucket_name
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions         = 5
      days_since_noncurrent_time = 30
    }
  }
}

# ------------------------------------------------------------------
# Service account for the RSS parser (Cloud Function / Cloud Run)
# ------------------------------------------------------------------
resource "google_service_account" "rss_parser" {
  account_id   = "rss-parser-sa"
  display_name = "RSS Parser Service Account"
}

# GCS access for the RSS parser
resource "google_storage_bucket_iam_member" "rss_parser_gcs" {
  bucket = google_storage_bucket.feeds.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.rss_parser.email}"
}

# Cloud Tasks enqueue permission for the RSS parser
resource "google_project_iam_member" "rss_parser_tasks_enqueuer" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.rss_parser.email}"
}

# Allow rss-parser-sa to "act as" itself when creating OIDC-authenticated Cloud Tasks
resource "google_service_account_iam_member" "rss_parser_act_as_self" {
  service_account_id = google_service_account.rss_parser.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.rss_parser.email}"
}

# Cloud Tasks Admin — needed to create the queue
resource "google_project_iam_member" "rss_parser_tasks_admin" {
  project = var.project_id
  role    = "roles/cloudtasks.admin"
  member  = "serviceAccount:${google_service_account.rss_parser.email}"
}

# ------------------------------------------------------------------
# Service account for the episode processor (target of Cloud Tasks)
# ------------------------------------------------------------------
resource "google_service_account" "episode_processor" {
  account_id   = "episode-processor-sa"
  display_name = "Episode Processor Service Account"
}

# GCS access for the episode processor
resource "google_storage_bucket_iam_member" "episode_processor_gcs" {
  bucket = google_storage_bucket.feeds.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.episode_processor.email}"
}

# ------------------------------------------------------------------
# Cloud Tasks queue for podcast episode processing
# ------------------------------------------------------------------
resource "google_cloud_tasks_queue" "podcast_processing" {
  name     = var.cloud_tasks_queue_name
  location = var.region

  rate_limits {
    max_dispatches_per_second = 5
    max_concurrent_dispatches = 3
  }

  retry_config {
    max_attempts       = 5
    min_backoff        = "10s"
    max_backoff        = "300s"
    max_doublings      = 3
    max_retry_duration = "3600s"
  }

  depends_on = [google_project_service.apis]
}

# ------------------------------------------------------------------
# Cloud Build service account permissions (needed for Cloud Functions v2)
# In newer projects, Cloud Functions v2 uses the Compute Engine default SA for builds.
# ------------------------------------------------------------------
data "google_project" "current" {}

locals {
  build_sa = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "cloudbuild_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${local.build_sa}"
}

resource "google_project_iam_member" "cloudbuild_artifacts" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${local.build_sa}"
}

resource "google_project_iam_member" "cloudbuild_storage" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${local.build_sa}"
}

resource "google_project_iam_member" "cloudbuild_builder" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.builder"
  member  = "serviceAccount:${local.build_sa}"
}

# ------------------------------------------------------------------
# Cloud Function: RSS Parser (runs on a schedule)
# ------------------------------------------------------------------

# Zip the source code for the RSS parser function
data "archive_file" "rss_parser_source" {
  type        = "zip"
  source_dir  = "${path.module}/.."
  output_path = "${path.module}/tmp/rss_parser_source.zip"

  excludes = [
    "terraform",
    "episode_processor",
    ".venv",
    ".vscode",
    "downloaded_mp3s",
    "__pycache__",
    "uv.lock",
    ".gitignore",
    ".python-version",
  ]
}

resource "google_storage_bucket_object" "rss_parser_source" {
  name   = "cloud-functions/rss-parser-${data.archive_file.rss_parser_source.output_md5}.zip"
  bucket = google_storage_bucket.feeds.name
  source = data.archive_file.rss_parser_source.output_path
}

resource "google_cloudfunctions2_function" "rss_parser" {
  name     = "rss-parser"
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "rss_parser_entry"
    source {
      storage_source {
        bucket = google_storage_bucket.feeds.name
        object = google_storage_bucket_object.rss_parser_source.name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "256Mi"
    timeout_seconds       = 300
    service_account_email = google_service_account.rss_parser.email

    environment_variables = {
      GCP_PROJECT_ID               = var.project_id
      CLOUD_TASKS_QUEUE            = var.cloud_tasks_queue_name
      CLOUD_TASKS_LOCATION         = var.region
      EPISODE_PROCESSOR_URL        = google_cloud_run_v2_service.episode_processor.uri
      GOOGLE_CLOUD_SERVICE_ACCOUNT = google_service_account.rss_parser.email
    }
  }

  depends_on = [
    google_project_service.apis,
    google_project_iam_member.cloudbuild_logs,
    google_project_iam_member.cloudbuild_artifacts,
    google_project_iam_member.cloudbuild_storage,
    google_project_iam_member.cloudbuild_builder,
  ]
}

# ------------------------------------------------------------------
# Artifact Registry for the episode processor container image
# ------------------------------------------------------------------
resource "google_artifact_registry_repository" "episode_processor" {
  location      = var.region
  repository_id = "episode-processor"
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}

# ------------------------------------------------------------------
# Cloud Run: Episode Processor (Whisper transcription with GPU)
# ------------------------------------------------------------------
# Build & push the image BEFORE running terraform apply:
#   cd episode_processor && ./build.sh
resource "google_cloud_run_v2_service" "episode_processor" {
  name                = "episode-processor"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = false

  template {
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.episode_processor.repository_id}/episode-processor:latest"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu              = "4"
          memory           = "16Gi"
          "nvidia.com/gpu" = "1"
        }
      }

      env {
        name  = "GCS_BUCKET"
        value = var.bucket_name
      }
      env {
        name  = "WHISPER_MODEL_SIZE"
        value = "large-v3"
      }
      env {
        name  = "WHISPER_DEVICE"
        value = "cuda"
      }
      env {
        name  = "WHISPER_COMPUTE_TYPE"
        value = "float16"
      }
    }

    node_selector {
      accelerator = "nvidia-l4"
    }

    gpu_zonal_redundancy_disabled = true

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    timeout         = "900s"
    service_account = google_service_account.episode_processor.email
  }

  depends_on = [
    google_project_service.apis,
    google_artifact_registry_repository.episode_processor,
  ]
}

# Allow Cloud Tasks to invoke the episode processor
resource "google_cloud_run_service_iam_member" "episode_processor_invoker" {
  location = var.region
  service  = google_cloud_run_v2_service.episode_processor.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.rss_parser.email}"
}

# ------------------------------------------------------------------
# Cloud Scheduler: Trigger the RSS parser periodically
# ------------------------------------------------------------------
resource "google_cloud_scheduler_job" "rss_parser_schedule" {
  name      = "rss-parser-schedule"
  region    = var.region
  schedule  = var.schedule_cron
  time_zone = "Europe/Stockholm"

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.rss_parser.url

    oidc_token {
      service_account_email = google_service_account.rss_parser.email
    }
  }

  depends_on = [google_project_service.apis]
}
