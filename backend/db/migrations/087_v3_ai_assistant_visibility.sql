-- Keep owner-private AI conversation content out of the sandbox read role.
-- The web login inherits unihub_business_write, while the sandbox login must
-- inherit only unihub_web_read.
REVOKE SELECT ON TABLE ai_assistant_conversations FROM unihub_web_read;
REVOKE SELECT ON TABLE ai_assistant_messages FROM unihub_web_read;
REVOKE SELECT ON TABLE ai_assistant_artifacts FROM unihub_web_read;
GRANT SELECT ON TABLE ai_assistant_conversations TO unihub_business_write;
GRANT SELECT ON TABLE ai_assistant_messages TO unihub_business_write;
GRANT SELECT ON TABLE ai_assistant_artifacts TO unihub_business_write;
