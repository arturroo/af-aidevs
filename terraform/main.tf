# Core infrastructure orchestration
# Call your modules here, e.g.:

# module "cloud_function_lesson_1" {
#   source = "./modules/example_module"
#   project_id = var.project_id
#   region     = var.region
#   function_name = "lesson-01-func"
# }


# Artur Fejklowicz 2026-04-15
# __author__ = "Artur Fejklowicz"
# __copyright__ = "Copyright 2026, The AF AIDevs4 Project"
# __credits__ = ["Artur Fejklowicz"]
# __license__ = "GPLv3"
# __version__ = "1.0.0"
# __maintainer__ = "Artur Fejklowicz"
# __status__ = "Production"

module "gstorage" {
    source = "./modules/gstorage"
    project_id = var.project_id
    buckets = var.buckets
    gs_notifications = var.gs_notifications
}

module "pubsub" {
    source = "./modules/pubsub"
    project_id = var.project_id
    topics = var.topics
    subscriptions = var.subscriptions
}

module "iam" {
    source = "./modules/iam"
    project_id = var.project_id
    bindings = var.bindings
}

module "gcf" {
    source = "./modules/gcf"
    project_id = var.project_id
    cf_names = var.cf_names
    gcf_bucket = module.gstorage.gcf_bucket

    depends_on = [
        module.gstorage,
        module.pubsub
    ]
}

module "cloud_run" {
    source = "./modules/cloud_run"
    project_id = var.project_id
    cr_names = var.cr_names
    source_bucket = module.gstorage.gcf_bucket # Reusing the same bucket for source zips

    depends_on = [
        module.gstorage
    ]
}


resource "google_bigquery_dataset" "dataset" {
    for_each    = var.datasets
    project     = var.project_id
    dataset_id  = each.key
    description = try(each.value["description"], null)
    location    = try(each.value["location"], "europe-west6")
    delete_contents_on_destroy  = try(each.value["delete_contents_on_destroy"], false)
    default_table_expiration_ms = try(each.value["default_table_expiration_ms"], null)
    max_time_travel_hours = try(each.value["max_time_travel_hours"], 168)
}

resource "google_bigquery_table" "internal_table" {
    for_each    = var.internal_tables
    project     = var.project_id
    dataset_id  = try(each.value["dataset_id"], null)
    table_id    = try(each.value["table_id"], each.key)
    description = try(each.value["description"], null)
    clustering  = try(each.value["clustering"], null)
    schema      = file(each.value["schema"])
    deletion_protection  = try(each.value["deletion_protection"], null)

    dynamic "time_partitioning" {
        for_each = try(each.value["time_partitioning"], null) != null ? [each.value["time_partitioning"]] : []
        content {
            type            = time_partitioning.value["type"]
            expiration_ms   = time_partitioning.value["expiration_ms"]
            field           = time_partitioning.value["field"]
            require_partition_filter    = time_partitioning.value["require_partition_filter"]
        }
    }

    dynamic "range_partitioning" {
        for_each = try(each.value["range_partitioning"], null) != null ? [each.value["range_partitioning"]] : []
        content {
            field = range_partitioning.value["field"]
            range {
                start       = range_partitioning.value["range"]["start"]
                end         = range_partitioning.value["range"]["end"]
                interval    = range_partitioning.value["range"]["interval"]
            }

        }
    }

    depends_on = [google_bigquery_dataset.dataset]
}


resource "google_bigquery_table" "external_table" {
    for_each    = var.external_tables
    project     = var.project_id
    dataset_id  = try(each.value["dataset_id"], null)
    table_id    = each.key
    description = try(each.value["description"], null)
    deletion_protection  = try(each.value["deletion_protection"], null)

    external_data_configuration {
        autodetect              = try(each.value["external_data_configuration"]["autodetect"], true)
        compression             = try(each.value["external_data_configuration"]["compression"], "NONE")
        ignore_unknown_values   = try(each.value["external_data_configuration"]["ignore_unknown_values"], false)
        max_bad_records         = try(each.value["external_data_configuration"]["max_bad_records"], 0)
        schema                  = try(each.value["external_data_configuration"]["schema"], null) != null ? file(each.value["external_data_configuration"]["schema"]) : null
        source_format           = try(each.value["external_data_configuration"]["source_format"], "CSV")
        source_uris             = try(each.value["external_data_configuration"]["source_uris"], [])

        dynamic "csv_options" {
            for_each = try(each.value["external_data_configuration"]["csv_options"], null) != null ? [each.value["external_data_configuration"]["csv_options"]] : []
            content {
                quote               = try(csv_options.value["quote"], "")
                allow_jagged_rows   = try(csv_options.value["allow_jagged_rows"], false)
                encoding            = try(csv_options.value["encoding"], "UTF-8") # The supported values are UTF-8 or ISO-8859-1
                field_delimiter     = try(csv_options.value["field_delimiter"], ",")
                skip_leading_rows   = try(csv_options.value["skip_leading_rows"], 0)
            }
        }

        dynamic "hive_partitioning_options" {
            for_each = try(each.value["external_data_configuration"]["hive_partitioning_options"], null) != null ? [each.value["external_data_configuration"]["hive_partitioning_options"]] : []
            content {
                mode                        = try(hive_partitioning_options.value["mode"], "AUTO")
                require_partition_filter    = try(hive_partitioning_options.value["require_partition_filter"], false)
                source_uri_prefix           = try(hive_partitioning_options.value["source_uri_prefix"], null)
            }
        }

        dynamic "google_sheets_options" {
            for_each = try(each.value["external_data_configuration"]["google_sheets_options"], null) != null ? [each.value["external_data_configuration"]["google_sheets_options"]] : []
            content {
                range = try(google_sheets_options.value["range"], null)
                skip_leading_rows = try(google_sheets_options.value["skip_leading_rows"], 0)
            }
        }
    }
    depends_on = [google_bigquery_dataset.dataset]
}


resource "google_bigquery_table" "view" {
    for_each    = var.views
    project     = var.project_id
    dataset_id  = try(each.value["dataset_id"], null)
    table_id    = each.key
    description = try(each.value["description"], null)
    deletion_protection  = try(each.value["deletion_protection"], null)

    view {
        query = templatefile(each.value["query_file"], {project_id = var.project_id})
        use_legacy_sql = try(each.value["use_legacy_sql"], false)
    }
    depends_on = [google_bigquery_dataset.dataset]
}

resource "google_bigquery_table" "dependent_view" {
    for_each    = var.dependent_views
    project     = var.project_id
    dataset_id  = try(each.value["dataset_id"], null)
    table_id    = each.key
    description = try(each.value["description"], null)
    deletion_protection  = try(each.value["deletion_protection"], null)

    view {
        query = templatefile(each.value["query_file"], {project_id = var.project_id})
        use_legacy_sql = try(each.value["use_legacy_sql"], false)
    }
    depends_on = [
        google_bigquery_dataset.dataset,
        google_bigquery_table.view
    ]
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
  member  = "serviceAccount:${module.cloud_run.service_accounts[each.value.svc]}"
  depends_on = [module.cloud_run]
}

# 2. BigQuery Dataset IAM Roles
resource "google_bigquery_dataset_iam_member" "dataset_roles" {
  for_each = { for entry in local.dataset_iam_list : "${entry.svc}-${entry.dataset}-${entry.role}" => entry }

  project    = var.project_id
  dataset_id = each.value.dataset
  role       = each.value.role
  member     = "serviceAccount:${module.cloud_run.service_accounts[each.value.svc]}"
  depends_on = [module.cloud_run, google_bigquery_dataset.dataset]
}

# 3. Storage Bucket IAM Roles
resource "google_storage_bucket_iam_member" "bucket_roles" {
  for_each = { for entry in local.bucket_iam_list : "${entry.svc}-${entry.bucket}-${entry.role}" => entry }

  bucket = module.gstorage.bucket_names[each.value.bucket]
  role   = each.value.role
  member = "serviceAccount:${module.cloud_run.service_accounts[each.value.svc]}"
  depends_on = [module.cloud_run, module.gstorage]
}

# 4. Cloud Run Service-to-Service IAM Roles
resource "google_cloud_run_v2_service_iam_member" "cr_invokers" {
  for_each = { for entry in local.cr_iam_list : "${entry.svc}-${entry.target_svc}-${entry.role}" => entry }

  project  = var.project_id
  location = "europe-west6"
  name     = each.value.target_svc
  role     = each.value.role
  member   = "serviceAccount:${module.cloud_run.service_accounts[each.value.svc]}"
  depends_on = [module.cloud_run]
}

# 5. Global Audit Log Sink (The "Google Way")
resource "google_logging_project_sink" "audit_sink" {
  name        = "sk-ai-governance-audit"
  destination = "bigquery.googleapis.com/projects/${var.project_id}/datasets/ai_governance"
  filter      = "jsonPayload.log_type=\"AUDIT\""

  unique_writer_identity = true

  bigquery_options {
    use_partitioned_tables = true
  }
}

# 6. IAM for the Log Sink to write to BigQuery
resource "google_bigquery_dataset_iam_member" "sink_bq_editor" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.dataset["ai_governance"].dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = google_logging_project_sink.audit_sink.writer_identity
  
  depends_on = [google_bigquery_dataset.dataset]
}

