variable "project_id" {
    default = ""
}   

variable "sa_json_google" {
    type = string
    sensitive = true
}

variable "gsheet_id" {
    type = string
    sensitive = true
}

variable "buckets" {
    description = "Google Storage buckets"
    default = {
        # "example-bucket" = {
        #     location      = "europe-west6"
        #     storage_class = "STANDARD"
        #     versioning    = true
        #     force_destroy = false
        # }
        "gcf" = {}

    }
}

variable "gs_notifications" {
    description = "Google Storage Notifications"
    default = {
        # "revolut" = {
        #     bucket = "banks"
        #     object_name_prefix = "raw/revolut/_SUCCESS"
        #     topic = "ps-i1-predict"
        # }
    }
}

variable "datasets" {
    description = "BigQuery Datasets"
    default = {
        # "banks" = {
        #     description = "Raw data from banks"
        #     max_time_travel_hours = 168
        # }
        "s01e03" = {
            description = "Dataset for S01E03 tasks"
        }
    }
}

variable "internal_tables" {
    description = "BigQuery internal tables"
    default = {
        # "revolut" = {
        #     description = "Revolut transactions internal table with transaction ID and one feature first_started"
        #     dataset_id = "banks"
        #     clustering = ["type", "state"]
        #     schema = "bq-schemas/banks.revolut.json"
        #     range_partitioning = {
        #         field = "month"
        #         range = {
        #             start = 201801
        #             end = 203801
        #             interval = 1
        #         }
        #     }
        #     
        # }
        "audit" = {
            description = "Audit logs for S01E03 proxy agent and MCP server"
            dataset_id = "s01e03"
            schema = "bq-schemas/s01e03.audit.json"
        }
    }
}

variable "external_tables" {
    description = "BigQuery external tables"
    default = {
        # "revolut_raw" = {
        #     description = "Revolut transactions"
        #     dataset_id = "banks"
        #     external_data_configuration = {
        #         autodetect  = false
        #         schema      = "bq-schemas/banks.revolut_raw.json"
        #         source_uris = [
        #             "gs://af-finanzen-banks/raw/revolut/*",
        #         ]
        #         csv_options = {
        #             quote               = "\""
        #             skip_leading_rows   = 1
        #         }
        #         hive_partitioning_options = {
        #             # 2023-07-02
        #             # Error: googleapi: Error 400: Field amount has type parameters, but it is not allowed in external table., invalid
        #             # because this field is financial data: type Numeric (Decimal) with precision and scale
        #             # mode = "CUSTOM"
        #             # source_uri_prefix = "gs://af-finanzen-banks/revolut/{account:String}/{month:String}"
        #             # 2023-07-02
        #             # In this case Schema from JSON file is respected but without parameters.
        #             # So the column amount is Numeric but without scale and precision parameters
        #             source_uri_prefix = "gs://af-finanzen-banks/raw/revolut/"
        #         }
        #     }
        # }
    }
}

variable "views" {
    description = "BigQuery views"
    default = {
        # "revolut_v" = {
        #     description = "Revolut transactions unique description indicator first_started"
        #     dataset_id = "banks"
        #     query_file = "bq-views/banks.revolut_v.sql"
        # }
    }
}

variable "dependent_views" {
    description = "BigQuery views that depend on other views"
    default = {
        # "postfinance_v" = {
        #     description = "PostFinance transactions with virtual TID and regex text splitting"
        #     dataset_id = "banks"
        #     query_file = "bq-views/banks.postfinance_v.sql"
        # }
    }
}

variable "topics" {
    description = "PubSub Topics"
    default = {
        # "ps-transform-csv" = {
        #     labels = {
        #         "publisher" = "gs"
        #     }
        # }
    }
}

variable "subscriptions" {
    description = "PubSub Subscriptions"
    default = {
        # "ps-transform-csv-sub-gcf" = {
        #     topic = "ps-transform-csv"
        # }
    }
}

variable "bindings" {
  default = {
      # "gs--ps-transform-csv" = {
      #     topic = "ps-transform-csv"
      # }
  }
}

variable "cf_names" {
    description = "Google Cloud Functions (Gen2 only). Supports: source_dir, entry_point, memory, env, public, trigger_type"
    default = {
        # "cf-s01e03-task" = {
        #     source_dir   = "./lessons/s01e03-projektowanie-api/task/gcp/cf-xy"
        #     entry_point  = "main"
        #     memory       = "256Mi"
        #     public       = true
        #     env          = {
        #         LOG_LEVEL = "DEBUG"
        #     }
        #     secrets      = {
        #         OPENAI_API_KEY = "openai-api-key" # Secret name in Secret Manager
        #     }
        #     secret_volumes = {
        #         "my-secret-file" = "/etc/secrets/config"
        #     }
        #     trigger_type = "http" # or "pubsub"
        # }
    }
}

variable "cr_names" {
    description = "Google Cloud Run services (v2 only). Supports: source_dir, memory, cpu, env, public, max_instances"
    default = {
        # "cr-s01e03-agent" = {
        #     source_dir    = "./lessons/s01e03-projektowanie-api/task/gcp/cr-xy"
        #     cpu           = "1"
        #     memory        = "512Mi"
        #     public        = true
        #     max_instances = 3
        #     env           = {
        #         AGENT_NAME = "Joi"
        #     }
        #     secrets       = {
        #         ANTHROPIC_API_KEY = "anthropic-key"
        #     }
        #     secret_volumes = {
        #         "service-account-key" = "/var/secrets/sa-key"
        #     }
        # }
        "cr-s01e03-mcp-server" = {
            source_dir   = "../lessons/s01e03-projektowanie-api-dla-efektywnej-pracy-z-modelem/task/cr-s01e03-mcp-server"
            cpu           = "1"
            memory       = "512Mi"
            public       = true # it should be private and in agent should use google.auth.transport.requests library to generate OIDC token for Cloud Run authentication
            cpu_throttling = true
            max_instances = 1
            env          = {
                LOG_LEVEL = "DEBUG"
                BQ_AUDIT_TABLE = "af-aidevs.s01e03.audit"
            }
            secrets      = {
                AIDEVS_API_KEY = "AIDEVS_API_KEY"
                AIDEVS_API_PACKAGES = "AIDEVS_API_PACKAGES"
            }
        }
        "cr-s01e03-agent" = {
            source_dir    = "../lessons/s01e03-projektowanie-api-dla-efektywnej-pracy-z-modelem/task/cr-s01e03-proxy-agent"
            cpu           = "1"
            memory        = "512Mi"
            public        = false
            cpu_throttling = true
            max_instances = 1
            env           = {
                BACKEND = "langchain"
                BQ_AUDIT_TABLE = "af-aidevs.s01e03.audit"
                LANGSMITH_TRACING = "true"
                LANGSMITH_ENDPOINT = "https://eu.api.smith.langchain.com"
                GOOGLE_CLOUD_LOCATION = "global"
                MCP_SERVER_URL = "https://cr-s01e03-mcp-server-qsvqxjqyrq-oa.a.run.app"
            }
            secrets       = {
                LANGSMITH_API_KEY = "LANGSMITH_API_KEY"
                LANGSMITH_PROJECT = "LANGSMITH_PROJECT"
            }
        }
    }
}

