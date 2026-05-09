SELECT
  timestamp,
  JSON_VALUE(jsonPayload, "$.resource_name") as resource_name,
  JSON_VALUE(jsonPayload, "$.session_id") as session_id,
  JSON_VALUE(jsonPayload, "$.actor") as actor,
  JSON_VALUE(jsonPayload, "$.content") as content,
  JSON_QUERY(jsonPayload, "$.metadata") as metadata
FROM
  `${project_id}.ai_governance.stdout`
WHERE
  JSON_VALUE(jsonPayload.log_type) = "AUDIT"
