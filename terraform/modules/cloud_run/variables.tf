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

variable "dataset_ids" {
  description = "Map of dataset names to their IDs"
  type        = map(string)
  default     = {}
}

variable "bucket_names" {
  description = "Map of bucket aliases to their actual names"
  type        = map(string)
  default     = {}
}
