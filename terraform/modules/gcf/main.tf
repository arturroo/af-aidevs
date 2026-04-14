# Cloud Functions Gen2 Module
# Aligned with Google Best Practices for af-aidevs

data "archive_file" "gcf_source" {
  for_each    = var.cf_names
  type        = "zip"
  # Support both absolute/relative paths from root or the default legacy path
  source_dir  = try(each.value.source_dir, "${path.module}/../../cloud_functions/${each.key}/")
  output_path = "${path.module}/../../.zips/${each.key}.zip"
  excludes    = [".git", ".venv", "__pycache__", ".pytest_cache", ".zips", ".gemini", "node_modules"]
}

# Add source code zip to the Cloud Function's bucket
resource "google_storage_bucket_object" "zip" {
  for_each     = var.cf_names
  source       = data.archive_file.gcf_source[each.key].output_path
  content_type = "application/zip"
  name         = "gcf-${each.key}-${data.archive_file.gcf_source[each.key].output_md5}.zip"
  bucket       = var.gcf_bucket
}

# Create the Gen2 Cloud function
resource "google_cloudfunctions2_function" "cf" {
  for_each = var.cf_names

  name        = try(each.value["name"], each.key)
  project     = var.project_id
  location    = try(each.value["region"], "europe-west6")
  description = try(each.value["description"], "Cloud-function Gen2 ${each.key}")

  build_config {
    runtime     = try(each.value["runtime"], "python312")
    entry_point = try(each.value["entry_point"], "main")
    source {
      storage_source {
        bucket = var.gcf_bucket
        object = google_storage_bucket_object.zip[each.key].name
      }
    }
  }

  service_config {
    max_instance_count = try(each.value["max_instances"], 5)
    min_instance_count = try(each.value["min_instances"], 0)
    available_memory   = try(each.value["memory"], "256Mi")
    timeout_seconds    = try(each.value["timeout"], 60)
    environment_variables = merge(
      try(each.value["env"], {})
    )
    ingress_settings = try(each.value["ingress"], "ALLOW_ALL")

    dynamic "secret_environment_variables" {
      for_each = try(each.value.secrets, {})
      content {
        key        = secret_environment_variables.key
        project_id = var.project_id
        secret     = secret_environment_variables.value
        version    = "latest"
      }
    }

    dynamic "secret_volumes" {
      for_each = try(each.value.secret_volumes, {})
      content {
        mount_path = secret_volumes.value
        project_id = var.project_id
        secret     = secret_volumes.key
      }
    }
  }

  dynamic "event_trigger" {
    for_each = try(each.value.trigger_type, "http") == "pubsub" ? [1] : []
    content {
      trigger_region = try(each.value["region"], "europe-west6")
      event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
      pubsub_topic   = "projects/${var.project_id}/topics/ps-${replace(each.key, "cf-", "")}"
      retry_policy   = "RETRY_POLICY_RETRY"
    }
  }
}

# Access Control (Restricted by default)
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  for_each = { for k, v in var.cf_names : k => v if try(v.public, false) }
  
  project  = var.project_id
  location = google_cloudfunctions2_function.cf[each.key].location
  name     = google_cloudfunctions2_function.cf[each.key].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
