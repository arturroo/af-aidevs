# Output variables from the root module

output "gcf_urls" {
  description = "The deployed Cloud Function endpoints"
  value       = module.gcf.urls
}

output "cr_urls" {
  description = "The deployed Cloud Run endpoints"
  value       = module.cloud_run.urls
}
