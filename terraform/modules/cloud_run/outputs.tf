output "urls" {
  description = "The URIs of the deployed Cloud Run services"
  value       = { for k, v in google_cloud_run_v2_service.cr : k => v.uri }
}

output "service_accounts" {
  description = "The Service Accounts created for the Cloud Run services"
  value       = { for k, v in google_service_account.sa_cr : k => v.email }
}
