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

# Create a dedicated Service Account for each Cloud Run service
resource "google_service_account" "sa_cr" {
  for_each     = var.cr_names
  account_id   = "sa-cr-${replace(each.key, "cr-", "")}"
  display_name = "Service Account for ${each.key}"
  project      = var.project_id
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
  
  triggers_replace = {
    zip_name = google_storage_bucket_object.zip[each.key].name
    md5      = data.archive_file.cr_source[each.key].output_md5
  }

  provisioner "local-exec" {
    command = "gcloud builds submit ${try(each.value.source_dir, "${path.module}/../../cloud_run/${each.key}/")} --project ${var.project_id} ${try(each.value.use_pack, true) ? "--pack image=${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}/${each.key}:${data.archive_file.cr_source[each.key].output_md5}" : "--config=${try(each.value.source_dir, "${path.module}/../../cloud_run/${each.key}/")}/cloudbuild.yaml --substitutions=_IMAGE=${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}/${each.key}:${data.archive_file.cr_source[each.key].output_md5},_TOKEN=$(gcloud auth print-access-token)"}"
  }

  depends_on = [google_storage_bucket_object.zip]
}

locals {
  # Project-level roles (e.g. roles/bigquery.jobUser)
  project_iam_list = flatten([
    for svc_name, cfg in var.cr_names : [
      for role in try(cfg.roles, []) : {
        svc  = svc_name
        role = role
      }
    ]
  ])

  # Dataset-level roles (BigQuery)
  dataset_iam_list = flatten([
    for svc_name, cfg in var.cr_names : [
      for dataset, roles in try(cfg.dataset_roles, {}) : [
        for role in roles : {
          svc     = svc_name
          dataset = dataset
          role    = role
        }
      ]
    ]
  ])

  # Bucket-level roles (Cloud Storage)
  bucket_iam_list = flatten([
    for svc_name, cfg in var.cr_names : [
      for bucket, roles in try(cfg.bucket_roles, {}) : [
        for role in roles : {
          svc    = svc_name
          bucket = bucket
          role   = role
        }
      ]
    ]
  ])

  # Service-to-Service roles (Cloud Run Invoker)
  cr_iam_list = flatten([
    for svc_name, cfg in var.cr_names : [
      for target_svc, roles in try(cfg.cr_roles, {}) : [
        for role in roles : {
          svc        = svc_name
          target_svc = target_svc
          role       = role
        }
      ]
    ]
  ])
}

# 1. Project-level IAM Roles
resource "google_project_iam_member" "project_roles" {
  for_each = { for entry in local.project_iam_list : "${entry.svc}-${entry.role}" => entry }

  project = var.project_id
  role    = each.value.role
  member  = "serviceAccount:${google_service_account.sa_cr[each.value.svc].email}"
}

# 2. BigQuery Dataset IAM Roles
resource "google_bigquery_dataset_iam_member" "dataset_roles" {
  for_each = { for entry in local.dataset_iam_list : "${entry.svc}-${entry.dataset}-${entry.role}" => entry }

  project    = var.project_id
  dataset_id = try(var.dataset_ids[each.value.dataset], each.value.dataset)
  role       = each.value.role
  member     = "serviceAccount:${google_service_account.sa_cr[each.value.svc].email}"
}

# 3. Storage Bucket IAM Roles
resource "google_storage_bucket_iam_member" "bucket_roles" {
  for_each = { for entry in local.bucket_iam_list : "${entry.svc}-${entry.bucket}-${entry.role}" => entry }

  bucket = try(var.bucket_names[each.value.bucket], each.value.bucket)
  role   = each.value.role
  member = "serviceAccount:${google_service_account.sa_cr[each.value.svc].email}"
}

# 4. Cloud Run Service-to-Service IAM Roles
resource "google_cloud_run_v2_service_iam_member" "cr_invokers" {
  for_each = { for entry in local.cr_iam_list : "${entry.svc}-${entry.target_svc}-${entry.role}" => entry }

  project  = var.project_id
  location = var.region
  name     = each.value.target_svc
  role     = each.value.role
  member   = "serviceAccount:${google_service_account.sa_cr[each.value.svc].email}"

  # The target service must exist before we can grant invoker roles on it
  depends_on = [google_cloud_run_v2_service.cr]
}

# 5. Wait for IAM propagation (GCP IAM is eventually consistent)
resource "time_sleep" "wait_for_iam" {
  create_duration = "20s"

  depends_on = [
    google_project_iam_member.project_roles,
    google_bigquery_dataset_iam_member.dataset_roles,
    google_storage_bucket_iam_member.bucket_roles
  ]
}

# Create Cloud Run v2 Service
resource "google_cloud_run_v2_service" "cr" {
  for_each = var.cr_names
  
  name     = try(each.value["name"], each.key)
  location = var.region
  project  = var.project_id

  template {
    service_account = google_service_account.sa_cr[each.key].email
    annotations = {
      "run.googleapis.com/cpu-throttling" = tostring(try(each.value.cpu_throttling, true))
    }
    
    containers {
      # Points to the image built by Cloud Build, uniquely tagged with source code MD5
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}/${each.key}:${data.archive_file.cr_source[each.key].output_md5}"
      
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
      
      dynamic "volume_mounts" {
        for_each = try(each.value.gcs_volumes, {})
        content {
          name       = volume_mounts.key
          mount_path = volume_mounts.value.mount_path
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
    
    dynamic "volumes" {
      for_each = try(each.value.gcs_volumes, {})
      content {
        name = volumes.key
        gcs {
          bucket    = try(var.bucket_names[volumes.value.bucket], volumes.value.bucket)
          read_only = try(volumes.value.read_only, false)
        }
      }
    }
    
    session_affinity = try(each.value.session_affinity, false)
    max_instance_request_concurrency = try(each.value.concurrency, 80)
    
    scaling {
      max_instance_count = try(each.value.max_instances, 1)
      min_instance_count = try(each.value.min_instances, 0)
    }

  }

  # Ensure build completes AND IAM roles (that affect startup) are active before deploying/updating
  # We wait for time_sleep.wait_for_iam to give IAM roles time to propagate
  depends_on = [
    terraform_data.build_image,
    time_sleep.wait_for_iam
  ]

  lifecycle {
    ignore_changes = [
      invoker_iam_disabled,
      client,
      client_version
    ]
  }
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
