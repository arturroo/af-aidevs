SELECT
  timestamp,
  jsonPayload.resource_name as resource_name,
  jsonPayload.session_id as session_id,
  jsonPayload.actor as actor,
  jsonPayload.content as content,
  jsonPayload.metadata as metadata
FROM
  `${project_id}.ai_governance.run_googleapis_com_stdout`
WHERE
  jsonPayload.log_type = "AUDIT"
