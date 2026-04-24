output "urls" {
  description = "The URIs of the deployed Cloud Run services"
  value       = { for k, v in google_cloud_run_v2_service.cr : k => v.uri }
}
