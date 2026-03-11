terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }

  # Backend is configured in backend.tf
}

provider "google" {
  project = var.project_id
  region  = var.region
}
