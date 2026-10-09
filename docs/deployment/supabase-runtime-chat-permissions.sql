-- Repair for tables created by management migrations under postgres rather than
-- the existing server-only voice_app database login used by Render's API.
-- Clerk authorization and organization scope remain enforced by the API.
-- No grants or policies are added for anon/authenticated or other client roles.
-- Applied to voice-ai-production after explicit approval on 2026-10-04.
BEGIN;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.runtime_assignments TO voice_app;
CREATE POLICY voice_api_server_access ON public.runtime_assignments FOR ALL TO voice_app USING (true) WITH CHECK (true);
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.runtime_tool_attempts TO voice_app;
CREATE POLICY voice_api_server_access ON public.runtime_tool_attempts FOR ALL TO voice_app USING (true) WITH CHECK (true);
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.chat_conversations TO voice_app;
CREATE POLICY voice_api_server_access ON public.chat_conversations FOR ALL TO voice_app USING (true) WITH CHECK (true);
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.chat_executions TO voice_app;
CREATE POLICY voice_api_server_access ON public.chat_executions FOR ALL TO voice_app USING (true) WITH CHECK (true);
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.chat_messages TO voice_app;
CREATE POLICY voice_api_server_access ON public.chat_messages FOR ALL TO voice_app USING (true) WITH CHECK (true);
COMMIT;
