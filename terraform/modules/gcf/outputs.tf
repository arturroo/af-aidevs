output "urls" {
  description = "The URIs of the deployed Cloud Functions"
  value       = { for k, v in google_cloudfunctions2_function.cf : k => v.service_config[0].uri }
}
