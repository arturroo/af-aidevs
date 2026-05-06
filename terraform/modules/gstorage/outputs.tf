output "gcf_bucket" {
  value = google_storage_bucket.bucket["gcf"].name
}

output "bucket_names" {
  value = { for k, v in google_storage_bucket.bucket : k => v.name }
}