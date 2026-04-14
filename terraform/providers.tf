# terraform {
#   required_version = ">= 1.5.0"
# 
#   required_providers {
#     google = {
#       source  = "hashicorp/google"
#       version = "~> 7.0"
#     }
#   }
# 
#   # Backend is configured in backend.tf
# }
# provider "google" {
#   project = var.project_id
#   region  = var.region
# }

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
  backend "gcs" {
    bucket  = "af-terraform-states"
    prefix  = "af-aidevs"
  }
}

provider "google" {
  credentials = file(var.sa_json_google)
  project = var.project_id
  region  = "europe-west6"
  zone    = "europe-west6b"
}

