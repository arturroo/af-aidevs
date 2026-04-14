# Cloud Run v2 Module
# Aligned with Google Best Practices for af-aidevs

resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = "cr-images"
  description   = "Docker repository for Cloud Run services"
  format        = "DOCKER"
  project       = var.project_id
  
  # Ensure deletion doesn't fail if images exist (Artur: adjust if you want strict cleanup)
  cleanup_policies {
    id     = "delete-old-images"
    action = "DELETE"
    condition {
      tag_state    = "ANY"
      older_than   = "2592000s" # 30 days
    }
  }
}

data "archive_file" "cr_source" {
  for_each    = var.cr_names
  type        = "zip"
  source_dir  = try(each.value.source_dir, "${path.module}/../../cloud_run/${each.key}/")
  output_path = "${path.module}/../../.zips/${each.key}-cr.zip"
  excludes    = [".git", ".venv", "__pycache__", ".pytest_cache", ".zips", ".gemini", "node_modules"]
}

resource "google_storage_bucket_object" "zip" {
  for_each     = var.cr_names
  source       = data.archive_file.cr_source[each.key].output_path
  content_type = "application/zip"
  name         = "cr-${each.key}-${data.archive_file.cr_source[each.key].output_md5}.zip"
  bucket       = var.source_bucket
}

# Build and Push image using Cloud Build
# Using terraform_data to trigger build on source change
resource "terraform_data" "build_image" {
  for_each = var.cr_names
  
  input = {
    zip_name = google_storage_bucket_object.zip[each.key].name
    md5      = data.archive_file.cr_source[each.key].output_md5
  }

  provisioner "local-exec" {
    command = "gcloud builds submit --project ${var.project_id} --tag ${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}/${each.key}:latest gs://${var.source_bucket}/${google_storage_bucket_object.zip[each.key].name}"
  }

  depends_on = [google_storage_bucket_object.zip]
}

# Create Cloud Run v2 Service
resource "google_cloud_run_v2_service" "cr" {
  for_each = var.cr_names
  
  name     = try(each.value["name"], each.key)
  location = var.region
  project  = var.project_id

  template {
    containers {
      # Points to the image built by Cloud Build
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}/${each.key}:latest"
      
      dynamic "env" {
        for_each = try(each.value.env, {})
        content {
          name  = env.key
          value = env.value
        }
      }
      
      dynamic "env" {
        for_each = try(each.value.secrets, {})
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
      
      dynamic "volume_mounts" {
        for_each = try(each.value.secret_volumes, {})
        content {
          name       = volume_mounts.key
          mount_path = volume_mounts.value
        }
      }
      
      resources {
        limits = {
          cpu    = try(each.value.cpu, "1")
          memory = try(each.value.memory, "512Mi")
        }
      }
    }

    dynamic "volumes" {
      for_each = try(each.value.secret_volumes, {})
      content {
        name = volumes.key
        secret {
          secret = volumes.key
          items {
            version = "latest"
            path    = "secret" # Default filename within the mount path
          }
        }
      }
    }
    
    max_instance_request_concurrency = try(each.value.concurrency, 80)
    
    scaling {
      max_instance_count = try(each.value.max_instances, 5)
      min_instance_count = try(each.value.min_instances, 0)
    }
  }

  # Ensure build completes before deploying/updating
  depends_on = [terraform_data.build_image]
}

# Access Control (Restricted by default)
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  for_each = { for k, v in var.cr_names : k => v if try(v.public, false) }
  
  project  = var.project_id
  location = google_cloud_run_v2_service.cr[each.key].location
  name     = google_cloud_run_v2_service.cr[each.key].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
