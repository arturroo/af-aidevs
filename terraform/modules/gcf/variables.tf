variable "project_id" {
  type = string
}

variable "cf_names" {
  description = "Map of Cloud Functions to create"
  type = any
}

variable "gcf_bucket" {
  description = "Bucket to store Cloud Function source code"
  type = string
}
