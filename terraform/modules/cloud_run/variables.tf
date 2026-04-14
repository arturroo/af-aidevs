variable "project_id" {
  type = string
}

variable "cr_names" {
  description = "Map of Cloud Run services to create"
  type = any
}

variable "source_bucket" {
  description = "Bucket to store source code zips"
  type = string
}

variable "region" {
  type    = string
  default = "europe-west6"
}
